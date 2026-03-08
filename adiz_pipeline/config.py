"""
管線設定：環境變數、預設值、ROI 參數
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# 路徑
DEFAULT_IMAGES_DIR = Path(os.getenv("ADIZ_IMAGES_DIR", "adiz_images"))

# Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

# BigQuery
BQ_PROJECT = os.getenv("BQ_PROJECT", "")
BQ_DATASET = os.getenv("BQ_DATASET", "adiz")
BQ_RAW_IMAGES_TABLE = "raw_images"
BQ_DETECTIONS_TABLE = "detections"
BQ_EVENTS_TABLE = "events"
BQ_OCR_ERROR_QUEUE_TABLE = "ocr_error_queue"

# 紅框偵測參數
RED_HUE_RANGE = (0, 15)  # HSV 紅色主色調
RED_HUE_RANGE_2 = (165, 180)  # HSV 紅色另一端
MIN_POLYGON_AREA = 500  # 最小多邊形面積（像素²）
MAX_POLYGON_AREA_RATIO = 0.5  # 最大面積佔圖比例

# 表格 ROI（左上角，佔圖比例）
TABLE_ROI_LEFT = 0.0
TABLE_ROI_TOP = 0.0
TABLE_ROI_RIGHT = 0.35
TABLE_ROI_BOTTOM = 0.25

# 地圖 ROI（排除左上角表格）
MAP_ROI_LEFT = 0.0
MAP_ROI_TOP = 0.2
MAP_ROI_RIGHT = 1.0
MAP_ROI_BOTTOM = 1.0

# 校正點（像素 → 經緯度，依國防部示意圖常見版型）
# 格式: (pixel_x, pixel_y) -> (lon, lat)
# 需依實際圖檔調整，此為預設參考
DEFAULT_CALIBRATION_POINTS = [
    ((100, 200), (119.0, 26.0)),
    ((500, 200), (124.0, 26.0)),
    ((100, 600), (119.0, 21.0)),
    ((500, 600), (124.0, 21.0)),
]

# 台灣空域有效範圍（經緯度）
TAIWAN_LON_MIN = 117.0
TAIWAN_LON_MAX = 125.0
TAIWAN_LAT_MIN = 20.0
TAIWAN_LAT_MAX = 27.0

# 信心門檻
CONFIDENCE_AUTO_ACCEPT = 0.85
CONFIDENCE_REVIEW = 0.6
