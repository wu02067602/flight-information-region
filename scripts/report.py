#!/usr/bin/env python3
"""產生處理報告：成功率、失敗率、主要失敗類型"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATABASE_URL, CONFIDENCE_MANUAL_REVIEW
import psycopg2
from psycopg2.extras import RealDictCursor


def main():
    conn = psycopg2.connect(DATABASE_URL)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # 總體統計
        cur.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE processing_status = 'done') as done,
                COUNT(*) FILTER (WHERE processing_status = 'failed') as failed,
                COUNT(*) FILTER (WHERE processing_status = 'pending') as pending,
                COUNT(*) as total
            FROM raw_images
            """
        )
        stat = cur.fetchone()

        # 低信心數量
        cur.execute(
            "SELECT COUNT(*) as cnt FROM events WHERE confidence_score < %s",
            (CONFIDENCE_MANUAL_REVIEW,),
        )
        low_conf = cur.fetchone()["cnt"]

        # 最近一次 run
        cur.execute(
            """
            SELECT run_id, pipeline_version, total_images, success_count, failed_count,
                   low_confidence_count, error_summary, finished_at
            FROM pipeline_runs
            ORDER BY started_at DESC
            LIMIT 1
            """
        )
        last_run = cur.fetchone()

    conn.close()

    total = stat["total"] or 0
    done = stat["done"] or 0
    failed = stat["failed"] or 0
    success_rate = (done / total * 100) if total else 0
    fail_rate = (failed / total * 100) if total else 0

    print("=" * 60)
    print("ADIZ 圖片座標抽取 - 處理報告")
    print("=" * 60)
    print(f"\n【總體統計】")
    print(f"  總圖片數: {total}")
    print(f"  處理完成: {done} ({success_rate:.1f}%)")
    print(f"  處理失敗: {failed} ({fail_rate:.1f}%)")
    print(f"  待處理: {stat['pending'] or 0}")
    print(f"  低信心事件(待覆核): {low_conf}")

    if last_run:
        print(f"\n【最近一次執行】run_id={last_run['run_id']}")
        print(f"  總計: {last_run['total_images']} | 成功: {last_run['success_count']} | 失敗: {last_run['failed_count']}")
        print(f"  低信心: {last_run['low_confidence_count']}")
        err_sum = last_run.get("error_summary") or {}
        if isinstance(err_sum, str):
            import json
            err_sum = json.loads(err_sum) if err_sum else {}
        if err_sum:
            print("\n  主要失敗類型:")
            for err, cnt in sorted(err_sum.items(), key=lambda x: -x[1])[:5]:
                print(f"    - {cnt}x: {err}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
