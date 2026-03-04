#!/usr/bin/env python3
"""初始化資料庫 schema"""
import os
import sys
from pathlib import Path

# 加入專案根目錄
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATABASE_URL


def main():
    schema_path = Path(__file__).parent.parent / "schema.sql"
    with open(schema_path) as f:
        sql = f.read()

    import psycopg2
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    try:
        conn.cursor().execute(sql)
        print("Schema 建立完成")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
