#!/usr/bin/env python3
"""查詢低信心清單供人工覆核"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import CONFIDENCE_MANUAL_REVIEW, DATABASE_URL
import psycopg2
from psycopg2.extras import RealDictCursor


def main():
    conn = psycopg2.connect(DATABASE_URL)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT e.id, e.source_id, e.item_number, e.event_time, e.aircraft_type,
                   e.sorties, e.remarks, e.confidence_score, e.review_status,
                   r.file_path, r.article_id
            FROM events e
            JOIN raw_images r ON e.raw_image_id = r.id
            WHERE e.confidence_score < %s
            ORDER BY e.confidence_score ASC, e.processed_at DESC
            """,
            (CONFIDENCE_MANUAL_REVIEW,),
        )
        rows = cur.fetchall()

    print(f"低信心清單 (confidence < {CONFIDENCE_MANUAL_REVIEW})，共 {len(rows)} 筆\n")
    print("-" * 80)
    for r in rows:
        print(f"ID: {r['id']} | source: {r['source_id']}")
        print(f"  項次: {r['item_number']} | 時間: {r['event_time']} | 機型: {r['aircraft_type']} | 架次: {r['sorties']}")
        print(f"  信心: {r['confidence_score']:.2%} | 原圖: {r['file_path']}")
        print("-" * 80)

    conn.close()


if __name__ == "__main__":
    main()
