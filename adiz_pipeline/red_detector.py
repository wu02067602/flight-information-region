"""
紅色框線區域偵測
在地圖 ROI 內做紅色分割，輸出多邊形頂點。
"""
from dataclasses import dataclass
from typing import List, Tuple

import cv2
import numpy as np

from .config import (
    MAP_ROI_BOTTOM,
    MAP_ROI_LEFT,
    MAP_ROI_RIGHT,
    MAP_ROI_TOP,
    MIN_POLYGON_AREA,
    RED_HUE_RANGE,
    RED_HUE_RANGE_2,
)


@dataclass
class RedPolygon:
    """單一紅色多邊形"""
    pixel_polygon: List[Tuple[float, float]]
    pixel_bbox: Tuple[float, float, float, float]  # x, y, w, h
    area: float
    confidence: float  # 0~1，基於形狀閉合性、面積合理性


def detect_red_regions(
    img: np.ndarray,
    min_area: int = MIN_POLYGON_AREA,
    max_area_ratio: float = 0.5,
) -> List[RedPolygon]:
    """
    偵測影像中的紅色框線區域，回傳多邊形列表。
    僅在 MAP_ROI 內搜尋。
    """
    h, w = img.shape[:2]
    roi = img[
        int(h * MAP_ROI_TOP):int(h * MAP_ROI_BOTTOM),
        int(w * MAP_ROI_LEFT):int(w * MAP_ROI_RIGHT),
    ]
    roi_h, roi_w = roi.shape[:2]
    offset_x = int(w * MAP_ROI_LEFT)
    offset_y = int(h * MAP_ROI_TOP)

    # HSV 紅色分割
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask1 = cv2.inRange(hsv, (RED_HUE_RANGE[0], 100, 100), (RED_HUE_RANGE[1], 255, 255))
    mask2 = cv2.inRange(hsv, (RED_HUE_RANGE_2[0], 100, 100), (RED_HUE_RANGE_2[1], 255, 255))
    red_mask = cv2.bitwise_or(mask1, mask2)

    # 形態學處理，連接斷線
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, kernel)
    red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN, kernel)

    # 找輪廓
    contours, _ = cv2.findContours(
        red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    polygons: List[RedPolygon] = []
    max_area = roi_w * roi_h * max_area_ratio

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue

        # 近似多邊形
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)

        if len(approx) < 3:
            continue

        # 轉為 (x, y) 列表，加回 ROI 偏移
        points = [
            (float(p[0][0]) + offset_x, float(p[0][1]) + offset_y)
            for p in approx
        ]

        x, y, bw, bh = cv2.boundingRect(approx)
        bbox = (float(x + offset_x), float(y + offset_y), float(bw), float(bh))

        # 信心：面積合理性 + 頂點數
        area_ratio = area / max_area
        vertex_score = min(1.0, len(approx) / 6)
        confidence = 0.5 * (1 - min(area_ratio, 1)) + 0.5 * vertex_score

        polygons.append(RedPolygon(
            pixel_polygon=points,
            pixel_bbox=bbox,
            area=area,
            confidence=min(1.0, confidence),
        ))

    return polygons
