"""
ADIZ 圖片座標抽取 ETL 主流程
批次處理、可中斷續跑、版本區分
"""
import logging
import uuid
from pathlib import Path
from typing import Any

from config import (
    DEFAULT_IMAGES_DIR,
    PIPELINE_VERSION,
    CONFIDENCE_MANUAL_REVIEW,
)
from adiz.image_loader import load_image, compute_file_hash
from adiz.red_box_detector import detect_red_polygons
from adiz.coordinate_converter import (
    pixel_to_geo,
    to_wkt_polygon,
    to_wkt_point,
    polygon_centroid,
)
from adiz.ocr_extractor import extract_table_from_image
from adiz import db

logger = logging.getLogger(__name__)


def collect_image_paths(images_dir: Path) -> list[tuple[str, Path]]:
    """
    收集待處理圖片
    回傳: [(source_id, path), ...]
    source_id = article_id/filename
    """
    from config import SUPPORTED_RASTER_FORMATS, SUPPORTED_SVG

    supported = SUPPORTED_RASTER_FORMATS | SUPPORTED_SVG
    results = []
    for article_dir in sorted(images_dir.iterdir()):
        if not article_dir.is_dir():
            continue
        article_id = article_dir.name
        for f in sorted(article_dir.iterdir()):
            if f.suffix.lower() in supported:
                source_id = f"{article_id}/{f.name}"
                results.append((source_id, f))
    return results


def associate_detections_with_events(
    detections: list[dict],
    table_events: list[dict],
) -> list[tuple[dict, dict | None]]:
    """
    關聯紅框與表格事件
    優先用編號（①②③）一對一對應
    回傳: [(detection, event|None), ...]
    """
    paired = []
    used_events = set()

    for i, det in enumerate(detections):
        # 嘗試依索引對應
        ev = None
        if i < len(table_events):
            ev = table_events[i]
            used_events.add(i)
        paired.append((det, ev))

    # 未配對的表格事件也建立（無幾何）
    for j, ev in enumerate(table_events):
        if j not in used_events:
            paired.append(({"pixel_vertices": [], "confidence": 0.5, "is_small": True}, ev))

    return paired


def process_single_image(
    source_id: str,
    file_path: Path,
    conn,
) -> dict[str, Any]:
    """
    處理單張圖片
    回傳: {success, error_message, detections_count, events_count, low_confidence}
    """
    article_id = source_id.split("/")[0]
    filename = "/".join(source_id.split("/")[1:])

    # 1. 載入圖片
    img, load_err = load_image(file_path)
    if load_err or img is None:
        return {"success": False, "error_message": load_err or "載入失敗", "detections_count": 0, "events_count": 0, "low_confidence": False}

    h, w = img.shape[:2]
    file_hash = compute_file_hash(file_path)

    # 2. 確保 raw_images 存在
    raw_id = db.ensure_raw_image(
        conn, source_id, article_id, str(file_path), file_hash=file_hash
    )

    try:
        db.update_raw_image_status(conn, raw_id, "processing")
    except Exception as e:
        logger.warning("更新狀態失敗: %s", e)

    # 3. 紅框偵測
    polygons = detect_red_polygons(img)
    if not polygons:
        # 無紅框時仍嘗試 OCR
        polygons = [{"pixel_vertices": [], "area": 0, "confidence": 0.3, "is_small": True}]

    # 4. OCR 表格
    ocr_raw_text, table_events = extract_table_from_image(img)

    # 5. 關聯
    paired = associate_detections_with_events(polygons, table_events)

    det_count = 0
    ev_count = 0
    low_conf = False

    for idx, (det, ev) in enumerate(paired):
        if not det.get("pixel_vertices") and not ev:
            continue

        pixel_verts = det.get("pixel_vertices", [])
        geo_wkt = None
        geo_confidence = 0.5
        geo_error = None

        if len(pixel_verts) >= 3:
            geo_verts, geo_confidence, geo_error = pixel_to_geo(pixel_verts, w, h)
            geo_wkt = to_wkt_polygon(geo_verts)
        else:
            geo_wkt = "POLYGON((120 24, 120.01 24, 120.01 24.01, 120 24))"  # 預設小區塊

        det_confidence = det.get("confidence", 0.5) * geo_confidence
        if det_confidence < CONFIDENCE_MANUAL_REVIEW:
            low_conf = True

        try:
            det_id = db.insert_detection(
                conn,
                raw_image_id=raw_id,
                detection_index=idx,
                pixel_vertices=pixel_verts,
                geo_wkt=geo_wkt,
                ocr_raw_text=ocr_raw_text if idx == 0 else None,
                confidence_score=det_confidence,
                error_message=geo_error,
            )
        except Exception as e:
            logger.error("插入 detection 失敗: %s", e)
            continue

        det_count += 1

        # 事件
        if ev:
            if len(pixel_verts) >= 3:
                geo_verts, _, _ = pixel_to_geo(pixel_verts, w, h)
                lon, lat = polygon_centroid(geo_verts)
                pt_wkt = to_wkt_point(lon, lat)
            else:
                lon, lat = 120.0, 24.0
                pt_wkt = "POINT(120 24)"

            ev_source_id = f"{source_id}-ev{idx}"
            db.insert_event(
                conn,
                detection_id=det_id,
                raw_image_id=raw_id,
                item_number=ev.get("item_number"),
                event_time=ev.get("event_time"),
                aircraft_type=ev.get("aircraft_type"),
                sorties=ev.get("sorties"),
                remarks=ev.get("remarks"),
                geometry_wkt=pt_wkt,
                confidence_score=det_confidence,
                source_id=ev_source_id,
            )
            ev_count += 1

    db.update_raw_image_status(conn, raw_id, "done", pipeline_version=PIPELINE_VERSION)
    return {
        "success": True,
        "error_message": None,
        "detections_count": det_count,
        "events_count": ev_count,
        "low_confidence": low_conf,
    }


def run_pipeline(
    images_dir: Path | None = None,
    resume: bool = True,
    max_images: int | None = None,
) -> dict[str, Any]:
    """
    執行批次管線
    resume: 是否跳過已處理
    """
    images_dir = images_dir or DEFAULT_IMAGES_DIR
    if not images_dir.exists():
        return {"error": f"圖片目錄不存在: {images_dir}", "total": 0, "success": 0, "failed": 0, "low_confidence": 0}

    paths = collect_image_paths(images_dir)
    if max_images:
        paths = paths[:max_images]

    if not paths:
        return {"run_id": "", "total": 0, "success": 0, "failed": 0, "low_confidence": 0, "error_summary": {}}

    run_id = str(uuid.uuid4())[:8]
    logger.info("管線開始 run_id=%s version=%s 共 %d 張圖", run_id, PIPELINE_VERSION, len(paths))

    success_count = 0
    failed_count = 0
    low_conf_count = 0
    error_summary = {}

    with db.get_connection() as conn:
        for source_id, path in paths:
            if resume:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id FROM raw_images WHERE source_id = %s AND processing_status = 'done'",
                        (source_id,),
                    )
                    if cur.fetchone():
                        logger.debug("略過已處理: %s", source_id)
                        success_count += 1
                        continue

            try:
                result = process_single_image(source_id, path, conn)
                if result["success"]:
                    success_count += 1
                    if result.get("low_confidence"):
                        low_conf_count += 1
                else:
                    failed_count += 1
                    err = result.get("error_message", "unknown")
                    error_summary[err] = error_summary.get(err, 0) + 1
            except Exception as e:
                failed_count += 1
                error_summary[str(e)[:80]] = error_summary.get(str(e)[:80], 0) + 1
                logger.exception("處理失敗 %s: %s", source_id, e)

        db.record_pipeline_run(
            conn, run_id, len(paths), success_count, failed_count, low_conf_count, error_summary
        )

    report = {
        "run_id": run_id,
        "total": len(paths),
        "success": success_count,
        "failed": failed_count,
        "low_confidence": low_conf_count,
        "error_summary": error_summary,
    }
    logger.info("管線完成 %s", report)
    return report
