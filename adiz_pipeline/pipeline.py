"""
ADIZ 圖片座標抽取主流程
批次處理 adiz_images/ 內圖片，輸出至 BigQuery。
"""
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .association import (
    associate_lines_to_rows,
    associate_markers_to_lines,
    associate_polygons_to_rows,
)
from .bigquery_loader import (
    load_detections,
    load_events,
    load_ocr_error_queue,
    load_raw_images,
    review_status_from_confidence,
)
from .bigquery_schema import ensure_tables
from .config import (
    BQ_PROJECT,
    CONFIDENCE_AUTO_ACCEPT,
    CONFIDENCE_REVIEW,
    DEFAULT_IMAGES_DIR,
)
from .coordinate_converter import pixel_line_to_geography, pixel_to_geography
from .image_loader import load_image
from .ocr_gemini import (
    TableRow,
    compute_ocr_confidence_breakdown,
    extract_table_ocr,
)
from .red_detector import (
    RedLine,
    RedMarker,
    RedPolygon,
    detect_red_lines,
    detect_red_markers,
    detect_red_regions,
)

logger = logging.getLogger(__name__)


def _file_hash(path: Path) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:32]


def _source_id(article_id: str, file_name: str) -> str:
    return f"{article_id}|{file_name}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def discover_images(images_dir: Path) -> Iterator[Tuple[str, Path]]:
    """遍歷 adiz_images/<article_id>/* 回傳 (article_id, file_path)"""
    if not images_dir.exists():
        return
    for article_dir in sorted(images_dir.iterdir()):
        if not article_dir.is_dir():
            continue
        article_id = article_dir.name
        for f in sorted(article_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".svg", ".gif", ".bmp", ".webp"):
                yield article_id, f


def process_single_image(
    article_id: str,
    file_path: Path,
    source_url: str = "",
    pipeline_version: str = "0.1.0",
) -> Tuple[
    Optional[Dict[str, Any]],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    Optional[Dict[str, Any]],
]:
    """
    處理單張圖片。
    回傳 (raw_image_row, detection_rows, event_rows, error_queue_rows, stats)
    """
    file_name = file_path.name
    source_id = _source_id(article_id, file_name)

    raw_row = {
        "source_id": source_id,
        "article_id": article_id,
        "file_name": file_name,
        "file_path": str(file_path),
        "file_hash": _file_hash(file_path),
        "source_url": source_url or f"https://www.mnd.gov.tw/news/plaact/{article_id}",
        "media_type": file_path.suffix.lower().lstrip("."),
        "fetched_at": None,
        "processing_status": "pending",
        "review_status": "pending",
    }

    detections: List[Dict] = []
    events: List[Dict] = []
    errors: List[Dict] = []

    img = load_image(file_path)
    if img is None:
        raw_row["processing_status"] = "failed"
        raw_row["error_code"] = "LOAD_FAILED"
        return raw_row, [], [], [], None

    # 1. 紅框偵測（多邊形、線段、標點）
    polygons = detect_red_regions(img)
    lines: List[RedLine] = detect_red_lines(img)
    markers: List[RedMarker] = detect_red_markers(img)

    if not polygons and not lines:
        raw_row["processing_status"] = "no_red_regions"
        raw_row["error_code"] = "NO_RED_REGIONS"
        polygons = []

    # 2. OCR
    rows, ocr_raw, ocr_conf, ocr_err = extract_table_ocr(img, "")
    if ocr_err:
        errors.append({
            "queue_id": str(uuid.uuid4()),
            "source_id": source_id,
            "failure_stage": "ocr",
            "failure_reason": ocr_err,
            "raw_response": ocr_raw[:2000] if ocr_raw else "",
        })

    # 3. 關聯
    polygon_associations = associate_polygons_to_rows(polygons, rows) if rows else []
    marker_to_line = associate_markers_to_lines(lines, markers)
    line_associations = (
        associate_lines_to_rows(lines, markers, marker_to_line, rows, polygon_count=len(polygons))
        if rows else []
    )

    # 4. 座標轉換 + 組裝 detections / events
    h, w = img.shape[:2]

    # 4a. 線段為主體：輸出 line_geometry + line_text
    for li, line in enumerate(lines):
        det_id = str(uuid.uuid4())
        line_geom_wkt, line_geom_conf = pixel_line_to_geography(
            line.pixel_path, img_size=(w, h)
        )
        row_idx = next((a[1] for a in line_associations if a[0] == li), None)
        assoc_conf = next((a[2] for a in line_associations if a[0] == li), 0.5)
        line_markers = marker_to_line.get(li, [])
        marker_centers = [markers[mi].center for mi in line_markers] if line_markers else []

        line_text = ""
        if row_idx is not None and row_idx < len(rows):
            row = rows[row_idx]
            parts = [row.event_time, row.aircraft_type, row.remarks]
            line_text = " | ".join(str(p) for p in parts if p)

        conf = line.confidence * 0.5 + line_geom_conf * 0.5
        if rows:
            conf = conf * 0.7 + ocr_conf * 0.3

        detections.append({
            "detection_id": det_id,
            "source_id": source_id,
            "source_image_id": source_id,
            "pixel_polygon": None,
            "pixel_bbox": None,
            "geometry": None,
            "geometry_type": "linestring",
            "line_geometry": line_geom_wkt,
            "line_type": line.line_type,
            "pixel_line": json.dumps(line.pixel_path),
            "marker_center_pixel": json.dumps(marker_centers) if marker_centers else None,
            "association_confidence": assoc_conf,
            "ocr_raw_text": ocr_raw[:5000] if ocr_raw else "",
            "confidence_score": conf,
            "confidence_breakdown": json.dumps({
                "line_confidence": line.confidence,
                "geom_confidence": line_geom_conf,
                "ocr_confidence": ocr_conf,
            }),
            "error_code": None,
            "review_status": review_status_from_confidence(conf),
        })

        if row_idx is not None and row_idx < len(rows):
            row = rows[row_idx]
            event_conf = conf * 0.7 + assoc_conf * 0.3
            events.append({
                "event_id": str(uuid.uuid4()),
                "source_id": source_id,
                "detection_id": det_id,
                "item_no": row.item_no,
                "event_time": row.event_time,
                "aircraft_type": row.aircraft_type,
                "mission_type": row.mission_type,
                "flight_no": row.flight_no,
                "remarks": row.remarks,
                "geometry": line_geom_wkt,
                "line_geometry": line_geom_wkt,
                "line_type": line.line_type,
                "line_text": line_text or row.raw_text,
                "review_status": review_status_from_confidence(event_conf),
                "source_text": row.raw_text,
            })

    # 4b. 多邊形（維持相容）
    for pi, poly in enumerate(polygons):
        det_id = str(uuid.uuid4())
        geom_wkt, geom_conf = pixel_to_geography(poly.pixel_polygon, img_size=(w, h))
        conf = (poly.confidence * 0.5 + geom_conf * 0.5)
        if rows:
            conf = conf * 0.7 + ocr_conf * 0.3

        detections.append({
            "detection_id": det_id,
            "source_id": source_id,
            "source_image_id": source_id,
            "pixel_polygon": json.dumps(poly.pixel_polygon),
            "pixel_bbox": json.dumps(poly.pixel_bbox),
            "geometry": geom_wkt,
            "geometry_type": "polygon",
            "line_geometry": None,
            "line_type": None,
            "pixel_line": None,
            "marker_center_pixel": None,
            "association_confidence": None,
            "ocr_raw_text": ocr_raw[:5000] if ocr_raw else "",
            "confidence_score": conf,
            "confidence_breakdown": json.dumps({
                "polygon_confidence": poly.confidence,
                "geom_confidence": geom_conf,
                "ocr_confidence": ocr_conf,
            }),
            "error_code": None,
            "review_status": review_status_from_confidence(conf),
        })

        # 找對應的 row
        row_idx = next((a[1] for a in polygon_associations if a[0] == pi), None)
        if row_idx is not None and row_idx < len(rows):
            row = rows[row_idx]
            assoc_conf = next((a[2] for a in polygon_associations if a[0] == pi), 0.5)
            event_conf = conf * 0.7 + assoc_conf * 0.3
            events.append({
                "event_id": str(uuid.uuid4()),
                "source_id": source_id,
                "detection_id": det_id,
                "item_no": row.item_no,
                "event_time": row.event_time,
                "aircraft_type": row.aircraft_type,
                "mission_type": row.mission_type,
                "flight_no": row.flight_no,
                "remarks": row.remarks,
                "geometry": geom_wkt,
                "line_geometry": None,
                "line_type": None,
                "line_text": None,
                "review_status": review_status_from_confidence(event_conf),
                "source_text": row.raw_text,
            })

    raw_row["processing_status"] = "completed" if detections or events else "no_events"
    raw_row["review_status"] = "pending"

    stats = {
        "polygon_count": len(polygons),
        "line_count": len(lines),
        "marker_count": len(markers),
        "ocr_row_count": len(rows),
        "detection_count": len(detections),
        "event_count": len(events),
        "error_count": len(errors),
    }
    return raw_row, detections, events, errors, stats


def run_batch(
    images_dir: Optional[Path] = None,
    run_id: Optional[str] = None,
    pipeline_version: str = "0.1.0",
    max_images: Optional[int] = None,
    use_bigquery: bool = True,
) -> Dict[str, Any]:
    """
    執行批次處理。
    use_bigquery=False 時僅回傳結果不寫入。
    """
    images_dir = images_dir or DEFAULT_IMAGES_DIR
    run_id = run_id or str(uuid.uuid4())
    now = _now()

    report = {
        "run_id": run_id,
        "pipeline_version": pipeline_version,
        "started_at": now,
        "total_images": 0,
        "success": 0,
        "failed": 0,
        "no_red_regions": 0,
        "no_events": 0,
        "total_detections": 0,
        "total_events": 0,
        "total_errors": 0,
        "low_confidence_count": 0,
        "low_confidence_sources": [],  # 低信心清單供人工覆核
    }

    all_raw: List[Dict] = []
    all_detections: List[Dict] = []
    all_events: List[Dict] = []
    all_errors: List[Dict] = []

    client = None
    if use_bigquery and BQ_PROJECT:
        try:
            from google.cloud import bigquery
            client = bigquery.Client(project=BQ_PROJECT)
            ensure_tables(client)
        except Exception as e:
            logger.warning("BigQuery 不可用，改為僅輸出結果: %s", e)
            use_bigquery = False

    images = list(discover_images(images_dir))
    if max_images:
        images = images[:max_images]
    report["total_images"] = len(images)

    for i, (article_id, file_path) in enumerate(images):
        raw, dets, evts, errs, stats = process_single_image(
            article_id, file_path, pipeline_version=pipeline_version
        )
        raw["run_id"] = run_id
        raw["pipeline_version"] = pipeline_version
        raw["processed_at"] = now

        all_raw.append(raw)
        all_detections.extend(dets)
        all_events.extend(evts)
        all_errors.extend(errs)

        if stats:
            report["total_detections"] += stats["detection_count"]
            report["total_events"] += stats["event_count"]
            report["total_errors"] += stats["error_count"]
            if raw.get("processing_status") == "completed":
                report["success"] += 1
            elif raw.get("processing_status") == "no_red_regions":
                report["no_red_regions"] += 1
            elif raw.get("processing_status") == "no_events":
                report["no_events"] += 1
            else:
                report["failed"] += 1
            # 低信心清單
            for d in dets:
                if d.get("review_status") == "low_confidence":
                    report["low_confidence_count"] += 1
                    sid = raw.get("source_id")
                    if sid and sid not in report["low_confidence_sources"]:
                        report["low_confidence_sources"].append(sid)

    if use_bigquery and client:
        load_raw_images(client, all_raw, run_id, pipeline_version)
        load_detections(client, all_detections, run_id, pipeline_version)
        load_events(client, all_events, run_id, pipeline_version)
        load_ocr_error_queue(client, all_errors, run_id)

    report["finished_at"] = _now()
    return report
