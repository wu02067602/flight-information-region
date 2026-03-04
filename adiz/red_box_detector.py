"""
紅框偵測模組
在地圖 ROI 內做紅色分割，輸出有效多邊形頂點
"""
import logging
from typing import Any

import cv2
import numpy as np

from config import (
    RED_HUE_RANGE,
    RED_HUE_RANGE_2,
    RED_SAT_MIN,
    RED_VAL_MIN,
    MIN_POLYGON_AREA,
    MAP_ROI_RATIO,
)

logger = logging.getLogger(__name__)


def extract_roi(img: np.ndarray, ratio: tuple[float, float, float, float]) -> np.ndarray:
    """
    依比例擷取 ROI
    ratio: (x_start, y_start, width, height) 皆為 0~1 比例
    """
    h, w = img.shape[:2]
    x1 = int(ratio[0] * w)
    y1 = int(ratio[1] * h)
    x2 = int((ratio[0] + ratio[2]) * w)
    y2 = int((ratio[1] + ratio[3]) * h)
    return img[y1:y2, x1:x2]


def pixel_to_global(points: list[list[int]], roi_offset: tuple[int, int]) -> list[list[int]]:
    """將 ROI 內像素座標轉回全圖座標"""
    ox, oy = roi_offset
    return [[x + ox, y + oy] for x, y in points]


def detect_red_polygons(
    img: np.ndarray,
    roi_ratio: tuple[float, float, float, float] = MAP_ROI_RATIO,
    min_area: int = MIN_POLYGON_AREA,
) -> list[dict[str, Any]]:
    """
    偵測圖上的紅色框線區域，輸出多邊形頂點
    
    回傳:
        [
            {
                "pixel_vertices": [[x,y], ...],
                "area": float,
                "confidence": float,
                "is_small": bool,
            },
            ...
        ]
    """
    roi = extract_roi(img, roi_ratio)
    h_roi, w_roi = roi.shape[:2]
    ox = int(roi_ratio[0] * img.shape[1])
    oy = int(roi_ratio[1] * img.shape[0])

    # HSV 紅色分割
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    lower1 = np.array([RED_HUE_RANGE[0], RED_SAT_MIN, RED_VAL_MIN])
    upper1 = np.array([RED_HUE_RANGE[1], 255, 255])
    lower2 = np.array([RED_HUE_RANGE_2[0], RED_SAT_MIN, RED_VAL_MIN])
    upper2 = np.array([RED_HUE_RANGE_2[1], 255, 255])
    mask1 = cv2.inRange(hsv, lower1, upper1)
    mask2 = cv2.inRange(hsv, lower2, upper2)
    red_mask = cv2.bitwise_or(mask1, mask2)

    # 形態學處理，連接斷線
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, kernel)
    red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN, kernel)

    # 找輪廓
    contours, _ = cv2.findContours(
        red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    results = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue

        # 多邊形近似
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)

        if len(approx) < 3:
            continue

        # 頂點轉為 list
        vertices = [[int(p[0][0]), int(p[0][1])] for p in approx]
        # 轉回全圖座標
        global_verts = pixel_to_global(vertices, (ox, oy))

        # 信心分數：面積適中、形狀閉合較高
        is_small = area < min_area * 3
        shape_score = min(1.0, len(approx) / 6) if len(approx) <= 8 else 1.0
        confidence = 0.9 if not is_small else 0.6
        confidence *= shape_score

        results.append({
            "pixel_vertices": global_verts,
            "area": float(area),
            "confidence": round(confidence, 4),
            "is_small": is_small,
        })

    # 依面積由大到小排序
    results.sort(key=lambda r: r["area"], reverse=True)
    return results
