"""
BigQuery 載入邏輯
以 source_id + run_id 做批次追蹤，支援重跑。
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from google.cloud import bigquery

from .config import (
    BQ_DATASET,
    BQ_DETECTIONS_TABLE,
    BQ_EVENTS_TABLE,
    BQ_OCR_ERROR_QUEUE_TABLE,
    BQ_PROJECT,
    BQ_RAW_IMAGES_TABLE,
    CONFIDENCE_AUTO_ACCEPT,
    CONFIDENCE_REVIEW,
)
from .ocr_gemini import TableRow


def _file_hash(path: Path) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:32]


def _source_id(article_id: str, file_name: str) -> str:
    return f"{article_id}|{file_name}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def load_raw_images(
    client: bigquery.Client,
    rows: List[Dict[str, Any]],
    run_id: str,
    pipeline_version: str,
) -> None:
    """載入 raw_images"""
    table_ref = f"{BQ_PROJECT or client.project}.{BQ_DATASET}.{BQ_RAW_IMAGES_TABLE}"
    now = _now().isoformat()
    for r in rows:
        r.setdefault("run_id", run_id)
        r.setdefault("pipeline_version", pipeline_version)
        r.setdefault("created_at", now)
        r.setdefault("updated_at", now)
    client.insert_rows_json(table_ref, rows)


def load_detections(
    client: bigquery.Client,
    rows: List[Dict[str, Any]],
    run_id: str,
    pipeline_version: str,
) -> None:
    """載入 detections"""
    table_ref = f"{BQ_PROJECT or client.project}.{BQ_DATASET}.{BQ_DETECTIONS_TABLE}"
    now = _now().isoformat()
    for r in rows:
        r.setdefault("run_id", run_id)
        r.setdefault("pipeline_version", pipeline_version)
        r.setdefault("ocr_provider", "gemini")
        r.setdefault("created_at", now)
    client.insert_rows_json(table_ref, rows)


def load_events(
    client: bigquery.Client,
    rows: List[Dict[str, Any]],
    run_id: str,
    pipeline_version: str,
) -> None:
    """載入 events"""
    table_ref = f"{BQ_PROJECT or client.project}.{BQ_DATASET}.{BQ_EVENTS_TABLE}"
    now = _now().isoformat()
    for r in rows:
        r.setdefault("run_id", run_id)
        r.setdefault("pipeline_version", pipeline_version)
        r.setdefault("created_at", now)
        r.setdefault("updated_at", now)
    client.insert_rows_json(table_ref, rows)


def load_ocr_error_queue(
    client: bigquery.Client,
    rows: List[Dict[str, Any]],
    run_id: str,
) -> None:
    """載入 ocr_error_queue"""
    table_ref = f"{BQ_PROJECT or client.project}.{BQ_DATASET}.{BQ_OCR_ERROR_QUEUE_TABLE}"
    now = _now().isoformat()
    for r in rows:
        r.setdefault("run_id", run_id)
        r.setdefault("retry_count", 0)
        r.setdefault("created_at", now)
    client.insert_rows_json(table_ref, rows)


def review_status_from_confidence(score: float) -> str:
    if score >= CONFIDENCE_AUTO_ACCEPT:
        return "auto_accepted"
    if score >= CONFIDENCE_REVIEW:
        return "pending_review"
    return "low_confidence"
