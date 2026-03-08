#!/usr/bin/env python3
"""
基於 exmpel 目錄的完整 pipeline 測試
對每張圖片輸出詳細處理結果。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adiz_pipeline.pipeline import process_single_image


def main():
    exmpel_dir = Path("exmpel")
    if not exmpel_dir.exists():
        print(f"錯誤：找不到 {exmpel_dir}")
        return 1

    images = []
    for article_dir in sorted(exmpel_dir.iterdir()):
        if not article_dir.is_dir():
            continue
        for f in sorted(article_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"):
                images.append((article_dir.name, f))

    print(f"共找到 {len(images)} 張圖片\n")
    print("=" * 80)

    all_results = []
    for i, (article_id, file_path) in enumerate(images):
        print(f"\n【圖片 {i+1}/{len(images)}】 {article_id}/{file_path.name}")
        print("-" * 60)

        raw, detections, events, errors, stats = process_single_image(
            article_id, file_path, pipeline_version="0.1.0"
        )

        status = raw.get("processing_status", "unknown")
        error_code = raw.get("error_code", "")

        print(f"  狀態: {status}" + (f" ({error_code})" if error_code else ""))
        print(f"  統計: polygon={stats.get('polygon_count', 0)}, line={stats.get('line_count', 0)}, "
              f"marker={stats.get('marker_count', 0)}, ocr_rows={stats.get('ocr_row_count', 0)}")
        print(f"  輸出: detection={len(detections)}, event={len(events)}, error={len(errors)}")

        if errors:
            for err in errors:
                print(f"  OCR 錯誤: {err.get('failure_reason', '')[:80]}")

        # Detections 明細
        for j, d in enumerate(detections):
            geom_type = d.get("geometry_type", "?")
            line_geom = d.get("line_geometry")
            pixel_poly = d.get("pixel_polygon")
            conf = d.get("confidence_score", 0)
            print(f"  Detection[{j}]: type={geom_type}, conf={conf:.2f}")
            if geom_type == "linestring" and line_geom:
                print(f"    LINESTRING: {line_geom[:100]}..." if len(line_geom) > 100 else f"    LINESTRING: {line_geom}")
            elif geom_type == "polygon" and pixel_poly:
                pts = json.loads(pixel_poly) if isinstance(pixel_poly, str) else pixel_poly
                print(f"    POLYGON 頂點數: {len(pts)}")

        # Events 明細（含 line_text）
        for j, e in enumerate(events):
            item_no = e.get("item_no", "")
            line_text = e.get("line_text", "")
            line_geom = e.get("line_geometry")
            print(f"  Event[{j}]: item_no={item_no}")
            if line_text:
                print(f"    line_text: {line_text[:80]}..." if len(line_text) > 80 else f"    line_text: {line_text}")
            if line_geom:
                print(f"    line_geometry: {line_geom[:80]}..." if len(line_geom) > 80 else f"    line_geometry: {line_geom}")

        all_results.append({
            "article_id": article_id,
            "file_name": file_path.name,
            "status": status,
            "error_code": error_code,
            "stats": stats,
            "detection_count": len(detections),
            "event_count": len(events),
            "error_count": len(errors),
        })

    # 彙總與人工標註比對
    gt = {
        "84835": (3, 0, 6), "84840": (3, 0, 6), "84844": (3, 0, 6), "84846": (2, 0, 4),
        "84850": (1, 0, 2), "84852": (2, 0, 4), "84854": (2, 0, 4), "84857": (2, 0, 4),
        "84863": (3, 0, 6), "84866": (1, 0, 2), "84869": (2, 0, 4), "84876": (1, 0, 2),
        "84881": (2, 0, 4), "84884": (3, 0, 6), "84889": (2, 0, 4), "84891": (2, 0, 4),
        "84894": (3, 0, 6), "84896": (4, 0, 8), "84900": (4, 0, 8), "84905": (3, 0, 6),
        "86194": (1, 0, 2), "86205": (3, 0, 6), "86248": (3, 2, 12),
    }
    print("\n" + "=" * 80)
    print("\n【彙總與人工標註比對】")
    print(f"{'圖片':<12} {'多邊形':^8} {'線段':^6} {'標點':^6} {'Detection':^10} | GT: 多邊形 線段 標點")
    print("-" * 70)
    for r in all_results:
        aid = r["article_id"]
        s = r["stats"]
        p, l, m = s.get("polygon_count", 0), s.get("line_count", 0), s.get("marker_count", 0)
        det = r["detection_count"]
        gt_p, gt_l, gt_m = gt.get(aid, (0, 0, 0))
        print(f"{aid:<12} {p:^8} {l:^6} {m:^6} {det:^10} | {gt_p} {gt_l} {gt_m}")
    by_status = {}
    for r in all_results:
        s = r["status"]
        by_status[s] = by_status.get(s, 0) + 1
    print("-" * 70)
    for s, c in sorted(by_status.items()):
        print(f"  {s}: {c} 張")
    print(f"  總 detection: {sum(r['detection_count'] for r in all_results)}")

    # 寫入 JSON 報告
    report_path = Path("pipeline_test_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\n詳細報告已寫入: {report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
