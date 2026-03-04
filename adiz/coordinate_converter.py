"""
座標轉換：像素 → 經緯度
使用固定校正點建立仿射轉換
"""
import logging
from typing import Any

from config import MAP_ROI_RATIO

logger = logging.getLogger(__name__)

# ADIZ 示意圖常見範圍（臺海周邊）
# 可依實際圖面校正點調整，此為預設參考
DEFAULT_BOUNDS = {
    "lon_min": 115.0,
    "lon_max": 125.0,
    "lat_min": 20.0,
    "lat_max": 28.0,
}


def pixel_to_geo(
    pixel_vertices: list[list[int]],
    img_width: int,
    img_height: int,
    bounds: dict[str, float] | None = None,
) -> tuple[list[tuple[float, float]], float, str | None]:
    """
    將像素多邊形頂點轉為經緯度
    
    使用簡單線性映射：圖左上→(lon_min,lat_max)，圖右下→(lon_max,lat_min)
    
    回傳: (geo_vertices, confidence, error_message)
    """
    bounds = bounds or DEFAULT_BOUNDS
    lon_min = bounds["lon_min"]
    lon_max = bounds["lon_max"]
    lat_min = bounds["lat_min"]
    lat_max = bounds["lat_max"]

    h, w = img_height, img_width
    roi = MAP_ROI_RATIO
    # 地圖區域像素範圍
    map_x1 = int(roi[0] * w)
    map_y1 = int(roi[1] * h)
    map_x2 = int((roi[0] + roi[2]) * w)
    map_y2 = int((roi[1] + roi[3]) * h)
    map_w = map_x2 - map_x1
    map_h = map_y2 - map_y1

    geo_vertices = []
    for px, py in pixel_vertices:
        # 正規化到 0~1
        nx = (px - map_x1) / map_w if map_w > 0 else 0
        ny = (py - map_y1) / map_h if map_h > 0 else 0
        # 邊界檢查
        nx = max(0, min(1, nx))
        ny = max(0, min(1, ny))
        lon = lon_min + nx * (lon_max - lon_min)
        lat = lat_max - ny * (lat_max - lat_min)  # y 向下為正
        geo_vertices.append((lon, lat))

    # 範圍驗證
    out_of_bounds = False
    for lon, lat in geo_vertices:
        if lon < 110 or lon > 130 or lat < 18 or lat > 32:
            out_of_bounds = True
            break

    confidence = 0.6 if out_of_bounds else 0.95
    error = "座標超出合理範圍，待覆核" if out_of_bounds else None

    return geo_vertices, confidence, error


def to_wkt_polygon(geo_vertices: list[tuple[float, float]]) -> str:
    """轉為 WKT POLYGON 字串供 PostGIS 使用"""
    if len(geo_vertices) < 3:
        return ""
    # 閉合多邊形
    ring = list(geo_vertices) + [geo_vertices[0]]
    pts = " ".join(f"{lon} {lat}" for lon, lat in ring)
    return f"POLYGON(({pts}))"


def to_wkt_point(lon: float, lat: float) -> str:
    """轉為 WKT POINT"""
    return f"POINT({lon} {lat})"


def polygon_centroid(geo_vertices: list[tuple[float, float]]) -> tuple[float, float]:
    """計算多邊形質心（簡單平均）"""
    if not geo_vertices:
        return (0.0, 0.0)
    n = len(geo_vertices)
    lon = sum(p[0] for p in geo_vertices) / n
    lat = sum(p[1] for p in geo_vertices) / n
    return (lon, lat)
