"""
資料庫連線與 CRUD
"""
import json
import logging
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import sql

from config import DATABASE_URL, CONFIDENCE_AUTO_ACCEPT, CONFIDENCE_MANUAL_REVIEW, PIPELINE_VERSION

logger = logging.getLogger(__name__)


@contextmanager
def get_connection() -> Generator:
    """取得資料庫連線"""
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_raw_image(
    conn,
    source_id: str,
    article_id: str,
    file_path: str,
    source_url: str | None = None,
    file_hash: str | None = None,
    fetched_at: datetime | None = None,
) -> int:
    """確保 raw_images 存在，回傳 id"""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO raw_images (source_id, article_id, file_path, source_url, file_hash, fetched_at, processing_status)
            VALUES (%s, %s, %s, %s, %s, %s, 'pending')
            ON CONFLICT (source_id) DO UPDATE SET
                file_path = EXCLUDED.file_path,
                updated_at = NOW()
            RETURNING id
            """,
            (source_id, article_id, file_path, source_url, file_hash, fetched_at),
        )
        row = cur.fetchone()
        return row["id"]


def update_raw_image_status(
    conn,
    raw_image_id: int,
    status: str,
    error_message: str | None = None,
    pipeline_version: str | None = None,
):
    """更新 raw_images 處理狀態"""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE raw_images
            SET processing_status = %s, error_message = %s, pipeline_version = %s,
                processed_at = CASE WHEN %s IN ('done', 'failed') THEN NOW() ELSE processed_at END,
                updated_at = NOW()
            WHERE id = %s
            """,
            (status, error_message, pipeline_version or PIPELINE_VERSION, status, raw_image_id),
        )


def insert_detection(
    conn,
    raw_image_id: int,
    detection_index: int,
    pixel_vertices: list,
    geo_wkt: str | None,
    ocr_raw_text: str | None,
    confidence_score: float,
    error_message: str | None = None,
) -> int:
    """插入 detection，回傳 id"""
    pixel_json = json.dumps(pixel_vertices)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO detections (raw_image_id, detection_index, pixel_geometry, geo_geometry, ocr_raw_text, confidence_score, error_message, pipeline_version)
            VALUES (%s, %s, %s, ST_GeomFromEWKT('SRID=4326;' || %s), %s, %s, %s, %s)
            ON CONFLICT (raw_image_id, detection_index) DO UPDATE SET
                pixel_geometry = EXCLUDED.pixel_geometry,
                geo_geometry = EXCLUDED.geo_geometry,
                ocr_raw_text = EXCLUDED.ocr_raw_text,
                confidence_score = EXCLUDED.confidence_score,
                error_message = EXCLUDED.error_message,
                pipeline_version = EXCLUDED.pipeline_version,
                processed_at = NOW()
            RETURNING id
            """,
            (
                raw_image_id,
                detection_index,
                pixel_json,
                geo_wkt or "POLYGON((120 24, 120.01 24, 120.01 24.01, 120 24))",
                ocr_raw_text,
                confidence_score,
                error_message,
                PIPELINE_VERSION,
            ),
        )
        row = cur.fetchone()
        return row["id"]


def insert_event(
    conn,
    detection_id: int | None,
    raw_image_id: int,
    item_number: str | None,
    event_time: str | None,
    aircraft_type: str | None,
    sorties: str | None,
    remarks: str | None,
    geometry_wkt: str | None,
    confidence_score: float,
    source_id: str,
):
    """插入 event"""
    review_status = (
        "auto_accepted"
        if confidence_score >= CONFIDENCE_AUTO_ACCEPT
        else "manual_review"
        if confidence_score >= CONFIDENCE_MANUAL_REVIEW
        else "manual_review"
    )
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO events (detection_id, raw_image_id, item_number, event_time, aircraft_type, sorties, remarks, geometry, review_status, confidence_score, source_id, pipeline_version)
            VALUES (%s, %s, %s, %s::timestamptz, %s, %s, %s, ST_GeomFromEWKT('SRID=4326;' || %s), %s, %s, %s, %s)
            ON CONFLICT (source_id, pipeline_version) DO UPDATE SET
                detection_id = EXCLUDED.detection_id,
                item_number = EXCLUDED.item_number,
                event_time = EXCLUDED.event_time,
                aircraft_type = EXCLUDED.aircraft_type,
                sorties = EXCLUDED.sorties,
                remarks = EXCLUDED.remarks,
                geometry = EXCLUDED.geometry,
                review_status = EXCLUDED.review_status,
                confidence_score = EXCLUDED.confidence_score,
                processed_at = NOW()
            """,
            (
                detection_id,
                raw_image_id,
                item_number,
                event_time,
                aircraft_type,
                sorties,
                remarks,
                geometry_wkt or "POINT(0 0)",
                review_status,
                confidence_score,
                source_id,
                PIPELINE_VERSION,
            ),
        )


def record_pipeline_run(
    conn,
    run_id: str,
    total: int,
    success: int,
    failed: int,
    low_conf: int,
    error_summary: dict | None = None,
):
    """記錄管線執行"""
    import json
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO pipeline_runs (run_id, pipeline_version, total_images, success_count, failed_count, low_confidence_count, finished_at, error_summary)
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s)
            """,
            (run_id, PIPELINE_VERSION, total, success, failed, low_conf, json.dumps(error_summary or {})),
        )
