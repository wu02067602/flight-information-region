"""
管線單元測試
在無實際圖片時驗證模組可正確 import 與基本邏輯。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

from adiz_pipeline.association import (
    associate_lines_to_rows,
    associate_markers_to_lines,
    associate_polygons_to_rows,
)
from adiz_pipeline.coordinate_converter import (
    pixel_line_to_geography,
    pixel_to_geography,
    validate_geometry,
)
from adiz_pipeline.image_loader import load_image
from adiz_pipeline.ocr_gemini import TableRow
from adiz_pipeline.red_detector import (
    RedLine,
    RedMarker,
    RedPolygon,
    detect_red_lines,
    detect_red_markers,
    detect_red_regions,
)


def test_red_detector_on_synthetic():
    """在合成紅框圖上測試偵測"""
    # 建立 100x100 紅框圖
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    img[10:90, 10:90] = [0, 0, 255]  # BGR 紅色
    img[20:80, 20:80] = [255, 255, 255]  # 白色內
    polygons = detect_red_regions(img, min_area=50)
    # 可能偵測到外框或內框
    assert isinstance(polygons, list)


def test_coordinate_converter():
    """測試座標轉換"""
    points = [(100, 200), (200, 200), (200, 300), (100, 300)]
    wkt, conf = pixel_to_geography(points)
    assert "POLYGON" in wkt
    assert 0 <= conf <= 1


def test_association():
    """測試紅框與表格關聯"""
    polygons = [
        RedPolygon([(0, 0), (10, 0), (10, 10)], (0, 0, 10, 10), 50, 0.9),
    ]
    rows = [
        TableRow("①", "2024-01-01 12:00", "B-52", "轟炸機", "2", "備註", "{}"),
    ]
    assoc = associate_polygons_to_rows(polygons, rows)
    assert len(assoc) >= 1


def test_validate_geometry():
    """測試幾何驗證"""
    assert validate_geometry("POLYGON((120 25, 121 25, 121 24, 120 24, 120 25))")
    assert not validate_geometry("POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))")


def test_detect_red_lines():
    """合成圖測試紅色線段偵測"""
    img = np.zeros((200, 200, 3), dtype=np.uint8)
    img[50:52, 20:180] = [0, 0, 255]  # BGR 紅色實線
    lines = detect_red_lines(img, min_length=15)
    assert isinstance(lines, list)
    assert len(lines) >= 1
    assert lines[0].line_type in ("solid", "dashed")
    assert len(lines[0].pixel_path) >= 2


def test_detect_red_markers():
    """合成圖測試紅色圓形標點偵測"""
    img = np.zeros((200, 200, 3), dtype=np.uint8)
    # 畫紅色圓
    import cv2
    cv2.circle(img, (100, 100), 15, (0, 0, 255), -1)
    markers = detect_red_markers(img, min_area=50, max_area=5000)
    assert isinstance(markers, list)


def test_pixel_line_to_geography():
    """測試線段轉 LINESTRING"""
    points = [(100, 200), (150, 250), (200, 200)]
    wkt, conf = pixel_line_to_geography(points)
    assert "LINESTRING" in wkt
    assert "POLYGON" not in wkt
    assert 0 <= conf <= 1


def test_associate_markers_to_lines():
    """測試標點與線段關聯"""
    lines = [
        RedLine(pixel_path=[(50, 50), (150, 50)], line_type="solid", confidence=0.9),
    ]
    markers = [
        RedMarker(center=(100, 52), radius=5, marker_label=None, confidence=0.9),
    ]
    mtl = associate_markers_to_lines(lines, markers, distance_threshold=25)
    assert 0 in mtl
    assert 0 in mtl[0]


def test_associate_lines_to_rows():
    """測試線段與表格列關聯"""
    lines = [
        RedLine(pixel_path=[(50, 50), (150, 50)], line_type="solid", confidence=0.9),
    ]
    markers = [RedMarker(center=(100, 52), radius=5, marker_label=None, confidence=0.9)]
    mtl = associate_markers_to_lines(lines, markers)
    rows = [
        TableRow("①", "12:00", "B-52", "轟炸", "2", "備註", "{}"),
        TableRow("④", "14:00", "氣球", "空飄", "2", "消失", "{}"),
    ]
    assoc = associate_lines_to_rows(lines, markers, mtl, rows, polygon_count=1)
    assert isinstance(assoc, list)
