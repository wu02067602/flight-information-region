#!/usr/bin/env python3
"""
ADIZ 圖片座標抽取 - CLI 主程式
批次處理 adiz_images/ 內圖片，輸出至 PostgreSQL + PostGIS
"""
import argparse
import logging
import sys
from pathlib import Path

from config import DEFAULT_IMAGES_DIR, LOG_LEVEL
from adiz.pipeline import run_pipeline


def setup_logging(level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main():
    parser = argparse.ArgumentParser(
        description="ADIZ 圖片座標抽取 - 從示意圖抽取紅框座標與表格文字"
    )
    parser.add_argument(
        "-i", "--images-dir",
        default=str(DEFAULT_IMAGES_DIR),
        help=f"圖片目錄 (預設: {DEFAULT_IMAGES_DIR})",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="不略過已處理，強制重跑",
    )
    parser.add_argument(
        "--max-images",
        type=int,
        default=None,
        help="最多處理幾張圖（測試用）",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="詳細日誌",
    )
    args = parser.parse_args()

    setup_logging("DEBUG" if args.verbose else LOG_LEVEL)

    images_dir = Path(args.images_dir)
    report = run_pipeline(
        images_dir=images_dir,
        resume=not args.no_resume,
        max_images=args.max_images,
    )

    if "error" in report:
        print(f"錯誤: {report['error']}", file=sys.stderr)
        sys.exit(1)

    if report.get("total", 0) == 0:
        print("無待處理圖片")
        sys.exit(0)

    print("\n=== 處理報告 ===")
    print(f"總計: {report['total']} 張")
    print(f"成功: {report['success']}")
    print(f"失敗: {report['failed']}")
    print(f"低信心(待覆核): {report['low_confidence']}")
    if report.get("error_summary"):
        print("\n失敗類型:")
        for err, cnt in report["error_summary"].items():
            print(f"  - {cnt}x: {err}")

    sys.exit(0 if report["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
