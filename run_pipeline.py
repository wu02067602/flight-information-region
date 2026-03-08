#!/usr/bin/env python3
"""
ADIZ 圖片座標抽取管線 - 主入口
批次處理 adiz_images/ 內圖片，輸出至 BigQuery。
"""
import argparse
import json
import logging
import sys
from pathlib import Path

# 確保 adiz_pipeline 可被 import
sys.path.insert(0, str(Path(__file__).resolve().parent))

from adiz_pipeline.config import DEFAULT_IMAGES_DIR
from adiz_pipeline.pipeline import run_batch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main():
    parser = argparse.ArgumentParser(
        description="ADIZ 圖片座標抽取管線：紅框偵測、OCR、座標轉換、BigQuery 入庫"
    )
    parser.add_argument(
        "-i", "--images-dir",
        default=str(DEFAULT_IMAGES_DIR),
        help=f"圖片根目錄 (預設: {DEFAULT_IMAGES_DIR})",
    )
    parser.add_argument(
        "--run-id",
        help="批次執行 ID，未指定則自動產生 UUID",
    )
    parser.add_argument(
        "--pipeline-version",
        default="0.1.0",
        help="管線版本號",
    )
    parser.add_argument(
        "--max-images",
        type=int,
        default=None,
        help="最多處理幾張圖（測試用）",
    )
    parser.add_argument(
        "--no-bigquery",
        action="store_true",
        help="不寫入 BigQuery，僅輸出處理報告",
    )
    parser.add_argument(
        "--report",
        type=str,
        help="將處理報告寫入指定 JSON 檔案",
    )
    args = parser.parse_args()

    report = run_batch(
        images_dir=Path(args.images_dir),
        run_id=args.run_id,
        pipeline_version=args.pipeline_version,
        max_images=args.max_images,
        use_bigquery=not args.no_bigquery,
    )

    print("\n=== 處理報告 ===")
    print(json.dumps(report, indent=2, ensure_ascii=False))

    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\n報告已寫入: {args.report}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
