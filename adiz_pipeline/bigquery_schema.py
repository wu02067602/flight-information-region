"""
BigQuery 資料表結構定義
"""
from google.cloud import bigquery

from .config import BQ_DATASET, BQ_PROJECT


def get_raw_images_schema() -> list:
    return [
        bigquery.SchemaField("source_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("article_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("file_name", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("file_path", "STRING"),
        bigquery.SchemaField("file_hash", "STRING"),
        bigquery.SchemaField("source_url", "STRING"),
        bigquery.SchemaField("media_type", "STRING"),
        bigquery.SchemaField("fetched_at", "TIMESTAMP"),
        bigquery.SchemaField("pipeline_version", "STRING"),
        bigquery.SchemaField("run_id", "STRING"),
        bigquery.SchemaField("processed_at", "TIMESTAMP"),
        bigquery.SchemaField("processing_status", "STRING"),
        bigquery.SchemaField("review_status", "STRING"),
        bigquery.SchemaField("error_code", "STRING"),
        bigquery.SchemaField("created_by", "STRING"),
        bigquery.SchemaField("created_at", "TIMESTAMP"),
        bigquery.SchemaField("updated_at", "TIMESTAMP"),
    ]


def get_detections_schema() -> list:
    return [
        bigquery.SchemaField("detection_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("source_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("run_id", "STRING"),
        bigquery.SchemaField("source_image_id", "STRING"),
        bigquery.SchemaField("pixel_polygon", "STRING"),  # JSON
        bigquery.SchemaField("pixel_bbox", "STRING"),  # JSON
        bigquery.SchemaField("geometry", "GEOGRAPHY"),
        bigquery.SchemaField("geometry_type", "STRING"),  # polygon | linestring
        bigquery.SchemaField("line_geometry", "GEOGRAPHY"),
        bigquery.SchemaField("line_type", "STRING"),  # solid | dashed
        bigquery.SchemaField("pixel_line", "STRING"),  # JSON
        bigquery.SchemaField("marker_center_pixel", "STRING"),  # JSON
        bigquery.SchemaField("association_confidence", "FLOAT64"),
        bigquery.SchemaField("ocr_raw_text", "STRING"),
        bigquery.SchemaField("confidence_score", "FLOAT64"),
        bigquery.SchemaField("confidence_breakdown", "STRING"),  # JSON
        bigquery.SchemaField("ocr_provider", "STRING"),
        bigquery.SchemaField("error_code", "STRING"),
        bigquery.SchemaField("review_status", "STRING"),
        bigquery.SchemaField("pipeline_version", "STRING"),
        bigquery.SchemaField("processed_at", "TIMESTAMP"),
        bigquery.SchemaField("created_at", "TIMESTAMP"),
    ]


def get_events_schema() -> list:
    return [
        bigquery.SchemaField("event_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("source_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("run_id", "STRING"),
        bigquery.SchemaField("detection_id", "STRING"),
        bigquery.SchemaField("item_no", "STRING"),
        bigquery.SchemaField("event_time", "STRING"),
        bigquery.SchemaField("aircraft_type", "STRING"),
        bigquery.SchemaField("mission_type", "STRING"),
        bigquery.SchemaField("flight_no", "STRING"),
        bigquery.SchemaField("remarks", "STRING"),
        bigquery.SchemaField("geometry", "GEOGRAPHY"),
        bigquery.SchemaField("line_geometry", "GEOGRAPHY"),
        bigquery.SchemaField("line_type", "STRING"),
        bigquery.SchemaField("line_text", "STRING"),
        bigquery.SchemaField("review_status", "STRING"),
        bigquery.SchemaField("reviewer", "STRING"),
        bigquery.SchemaField("reviewed_at", "TIMESTAMP"),
        bigquery.SchemaField("pipeline_version", "STRING"),
        bigquery.SchemaField("processed_at", "TIMESTAMP"),
        bigquery.SchemaField("created_at", "TIMESTAMP"),
        bigquery.SchemaField("updated_at", "TIMESTAMP"),
        bigquery.SchemaField("source_text", "STRING"),
    ]


def get_ocr_error_queue_schema() -> list:
    return [
        bigquery.SchemaField("queue_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("source_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("run_id", "STRING"),
        bigquery.SchemaField("failure_stage", "STRING"),
        bigquery.SchemaField("failure_reason", "STRING"),
        bigquery.SchemaField("raw_response", "STRING"),
        bigquery.SchemaField("retry_count", "INT64"),
        bigquery.SchemaField("review_status", "STRING"),
        bigquery.SchemaField("created_at", "TIMESTAMP"),
    ]


def ensure_tables(client: bigquery.Client) -> None:
    """建立資料集與資料表（若不存在）"""
    dataset_ref = bigquery.DatasetReference(BQ_PROJECT or client.project, BQ_DATASET)
    dataset = bigquery.Dataset(dataset_ref)
    try:
        client.create_dataset(dataset, exists_ok=True)
    except Exception:
        pass

    from .config import (
        BQ_DETECTIONS_TABLE,
        BQ_EVENTS_TABLE,
        BQ_OCR_ERROR_QUEUE_TABLE,
        BQ_RAW_IMAGES_TABLE,
    )

    tables = [
        (BQ_RAW_IMAGES_TABLE, get_raw_images_schema()),
        (BQ_DETECTIONS_TABLE, get_detections_schema()),
        (BQ_EVENTS_TABLE, get_events_schema()),
        (BQ_OCR_ERROR_QUEUE_TABLE, get_ocr_error_queue_schema()),
    ]
    for name, schema in tables:
        table_ref = dataset_ref.table(name)
        table = bigquery.Table(table_ref, schema=schema)
        try:
            client.create_table(table, exists_ok=True)
        except Exception:
            pass
