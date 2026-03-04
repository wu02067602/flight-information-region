"""
影像載入與格式分流
支援 JPG/PNG 等點陣圖，SVG 需轉換為點陣圖後處理
"""
import hashlib
import logging
from pathlib import Path

import cv2
import numpy as np

from config import SUPPORTED_RASTER_FORMATS, SUPPORTED_SVG

logger = logging.getLogger(__name__)


def compute_file_hash(file_path: Path) -> str:
    """計算檔案 SHA256 hash"""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def svg_to_raster(svg_path: Path, dpi: int = 150) -> np.ndarray | None:
    """
    將 SVG 轉為 numpy 點陣圖（BGR）
    需安裝 cairosvg
    """
    try:
        import cairosvg
        import io
        png_data = cairosvg.svg2png(
            url=str(svg_path),
            dpi=dpi,
            output_width=None,
            output_height=None,
        )
        arr = np.frombuffer(png_data, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return img
    except ImportError:
        logger.warning("cairosvg 未安裝，無法處理 SVG。請執行: pip install cairosvg")
        return None
    except Exception as e:
        logger.error("SVG 轉換失敗 %s: %s", svg_path, e)
        return None


def load_image(file_path: Path) -> tuple[np.ndarray | None, str | None]:
    """
    載入圖片為 OpenCV BGR 格式
    回傳 (image_array, error_message)
    """
    path = Path(file_path)
    if not path.exists():
        return None, f"檔案不存在: {path}"

    ext = path.suffix.lower()
    if ext in SUPPORTED_RASTER_FORMATS:
        img = cv2.imread(str(path))
        if img is None:
            return None, f"無法讀取點陣圖: {path}"
        return img, None

    if ext in SUPPORTED_SVG:
        img = svg_to_raster(path)
        if img is None:
            return None, f"SVG 轉換失敗: {path}"
        return img, None

    return None, f"不支援的格式: {ext}"
