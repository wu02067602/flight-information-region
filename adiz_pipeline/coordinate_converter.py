"""
像素座標轉經緯度
使用校正點做仿射/透視轉換，並做範圍驗證。
"""
from typing import List, Optional, Tuple

from .config import (
    DEFAULT_CALIBRATION_POINTS,
    TAIWAN_LAT_MAX,
    TAIWAN_LAT_MIN,
    TAIWAN_LON_MAX,
    TAIWAN_LON_MIN,
)


def pixel_to_geography(
    pixel_points: List[Tuple[float, float]],
    calibration_points: Optional[List[Tuple[Tuple[float, float], Tuple[float, float]]]] = None,
    img_size: Optional[Tuple[int, int]] = None,
) -> Tuple[str, float]:
    """
    將像素多邊形轉為 WKT POLYGON 字串（BigQuery GEOGRAPHY 相容）。
    回傳 (wkt_string, confidence)，若超出有效範圍則 confidence 降低。
    """
    if calibration_points is None:
        calibration_points = DEFAULT_CALIBRATION_POINTS

    # 簡化：使用線性插值（實際可改為 cv2.getPerspectiveTransform）
    # 假設圖為矩形，四角對應已知經緯度
    src_pts = [p[0] for p in calibration_points]
    dst_pts = [p[1] for p in calibration_points]

    if img_size:
        w, h = img_size
        # 依圖尺寸調整校正點
        pass  # 可擴充動態校正

    def interpolate(px: float, py: float) -> Tuple[float, float]:
        # 雙線性插值
        x0, y0 = min(s[0] for s in src_pts), min(s[1] for s in src_pts)
        x1, y1 = max(s[0] for s in src_pts), max(s[1] for s in src_pts)
        tx = (px - x0) / (x1 - x0) if x1 != x0 else 0
        ty = (py - y0) / (y1 - y0) if y1 != y0 else 0
        lon0 = dst_pts[0][0] + (dst_pts[1][0] - dst_pts[0][0]) * tx
        lon1 = dst_pts[2][0] + (dst_pts[3][0] - dst_pts[2][0]) * tx
        lat0 = dst_pts[0][1] + (dst_pts[2][1] - dst_pts[0][1]) * ty
        lat1 = dst_pts[1][1] + (dst_pts[3][1] - dst_pts[1][1]) * ty
        lon = lon0 + (lon1 - lon0) * ty
        lat = lat0 + (lat1 - lat0) * tx
        return (lon, lat)

    coords = [interpolate(x, y) for x, y in pixel_points]
    # 閉合多邊形
    if coords[0] != coords[-1]:
        coords.append(coords[0])

    # 檢查是否在有效範圍內
    in_bounds = all(
        TAIWAN_LON_MIN <= lon <= TAIWAN_LON_MAX and TAIWAN_LAT_MIN <= lat <= TAIWAN_LAT_MAX
        for lon, lat in coords
    )
    confidence = 1.0 if in_bounds else 0.5

    wkt = "POLYGON((" + ",".join(f"{lon} {lat}" for lon, lat in coords) + "))"
    return wkt, confidence


def validate_geometry(geometry_wkt: str) -> bool:
    """驗證幾何是否在台灣空域有效範圍內"""
    # 簡化：解析 WKT 取頂點檢查
    import re
    coords = re.findall(r"(\d+\.?\d*)\s+(\d+\.?\d*)", geometry_wkt)
    for c in coords:
        lon, lat = float(c[0]), float(c[1])
        if not (TAIWAN_LON_MIN <= lon <= TAIWAN_LON_MAX and TAIWAN_LAT_MIN <= lat <= TAIWAN_LAT_MAX):
            return False
    return True
