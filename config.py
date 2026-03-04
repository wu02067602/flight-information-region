"""
ADIZ 圖片座標抽取專案 - 設定檔
"""
import os
from pathlib import Path

# 預設路徑
DEFAULT_IMAGES_DIR = Path("adiz_images")
DEFAULT_OUTPUT_DIR = Path("adiz_output")

# 資料庫連線（可透過環境變數覆寫）
DATABASE_URL = os.getenv(
    "ADIZ_DATABASE_URL",
    "postgresql://localhost:5432/adiz?user=adiz&password=adiz",
)

# 管線版本（重跑時可區分）
PIPELINE_VERSION = os.getenv("ADIZ_PIPELINE_VERSION", "v1.0")

# 信心分數門檻
CONFIDENCE_AUTO_ACCEPT = 0.95   # 高於此自動接受
CONFIDENCE_MANUAL_REVIEW = 0.70  # 低於此需人工覆核

# 影像處理參數
RED_HUE_RANGE = (0, 15)          # HSV 紅色色相範圍（0-15 與 165-180）
RED_HUE_RANGE_2 = (165, 180)
RED_SAT_MIN = 100
RED_VAL_MIN = 100
MIN_POLYGON_AREA = 500           # 最小多邊形面積（像素²），過濾噪點
MAP_ROI_RATIO = (0.0, 0.0, 1.0, 1.0)  # 地圖 ROI 佔整圖比例 (x, y, w, h)，預設全圖

# 表格 ROI（左上角）佔圖比例
TABLE_ROI_RATIO = (0.0, 0.0, 0.35, 0.25)  # x, y, width, height

# 支援的圖片格式
SUPPORTED_RASTER_FORMATS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif"}
SUPPORTED_SVG = {".svg"}

# 日誌
LOG_LEVEL = os.getenv("ADIZ_LOG_LEVEL", "INFO")
