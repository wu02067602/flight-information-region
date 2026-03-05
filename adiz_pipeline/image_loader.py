"""
圖片載入與格式分流
支援 JPG/PNG 及 SVG rasterize，輸出統一為 numpy 陣列供 OpenCV 使用。
"""
import io
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

try:
    import cairosvg
    HAS_CAIROSVG = True
except ImportError:
    HAS_CAIROSVG = False


def load_image(path: Path) -> Optional[np.ndarray]:
    """
    載入圖片為 BGR numpy 陣列（OpenCV 格式）。
    若為 SVG，先 rasterize 成點陣圖。
    """
    path = Path(path)
    if not path.exists():
        return None

    suffix = path.suffix.lower()
    if suffix == ".svg":
        return _rasterize_svg(path)
    if suffix in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"):
        return _load_raster(path)
    return None


def _load_raster(path: Path) -> Optional[np.ndarray]:
    """載入點陣圖"""
    try:
        img = Image.open(path)
        if img.mode != "RGB":
            img = img.convert("RGB")
        arr = np.array(img)
        # OpenCV 使用 BGR
        return arr[:, :, ::-1].copy()
    except Exception:
        return None


def _rasterize_svg(path: Path, dpi: int = 150) -> Optional[np.ndarray]:
    """將 SVG 轉為點陣圖"""
    if not HAS_CAIROSVG:
        return None
    try:
        with open(path, "rb") as f:
            data = f.read()
        png_bytes = cairosvg.svg2png(bytestring=data, dpi=dpi)
        img = Image.open(io.BytesIO(png_bytes))
        arr = np.array(img.convert("RGB"))
        return arr[:, :, ::-1].copy()
    except Exception:
        return None


def get_image_roi(
    img: np.ndarray,
    left: float, top: float, right: float, bottom: float
) -> np.ndarray:
    """依比例裁切 ROI"""
    h, w = img.shape[:2]
    x1 = int(w * left)
    y1 = int(h * top)
    x2 = int(w * right)
    y2 = int(h * bottom)
    return img[y1:y2, x1:x2]
