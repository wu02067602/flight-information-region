"""
紅色框線區域偵測
在地圖 ROI 內做紅色分割，輸出多邊形頂點、線段、標點。
"""
from dataclasses import dataclass
from typing import List, Literal, Optional, Tuple

import cv2
import numpy as np

from .config import (
    DASHED_ANGLE_TOLERANCE,
    MAP_ROI_BOTTOM,
    MAP_ROI_LEFT,
    MAP_ROI_RIGHT,
    MAP_ROI_TOP,
    MAX_LINE_GAP,
    MAX_MARKER_AREA,
    MAX_POLYGON_AREA,
    MAX_POLYGON_CIRCULARITY,
    MIN_LINE_LENGTH,
    MIN_MARKER_AREA,
    MIN_MARKER_CIRCULARITY,
    MIN_PATH_LENGTH,
    MIN_POLYGON_AREA,
    RED_HUE_RANGE,
    RED_HUE_RANGE_2,
    RED_SAT_MIN,
    RED_VAL_MIN,
)


@dataclass
class RedPolygon:
    """單一紅色多邊形"""
    pixel_polygon: List[Tuple[float, float]]
    pixel_bbox: Tuple[float, float, float, float]  # x, y, w, h
    area: float
    confidence: float  # 0~1，基於形狀閉合性、面積合理性


@dataclass
class RedLine:
    """紅色線段（實線或虛線）"""
    pixel_path: List[Tuple[float, float]]
    line_type: Literal["solid", "dashed"]
    confidence: float  # 0~1


@dataclass
class RedMarker:
    """紅色圓形標點"""
    center: Tuple[float, float]
    radius: float
    marker_label: Optional[str]  # 若可辨識編號
    confidence: float  # 0~1


def _get_red_mask(roi: np.ndarray) -> np.ndarray:
    """從 ROI 取得紅色二值遮罩（含低飽和度紅色）"""
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask1 = cv2.inRange(hsv, (RED_HUE_RANGE[0], RED_SAT_MIN, RED_VAL_MIN), (RED_HUE_RANGE[1], 255, 255))
    mask2 = cv2.inRange(hsv, (RED_HUE_RANGE_2[0], RED_SAT_MIN, RED_VAL_MIN), (RED_HUE_RANGE_2[1], 255, 255))
    return cv2.bitwise_or(mask1, mask2)


def _merge_line_segments(
    segments: List[Tuple[Tuple[float, float], Tuple[float, float]]],
    max_gap: float = MAX_LINE_GAP,
    angle_tol_deg: float = DASHED_ANGLE_TOLERANCE,
) -> List[List[Tuple[float, float]]]:
    """
    合併鄰近且方向一致的線段為路徑。
    回傳 [(x1,y1), (x2,y2), ...] 的列表。
    """
    if not segments:
        return []

    def _angle(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
        import math
        return math.degrees(math.atan2(p2[1] - p1[1], p2[0] - p1[0]))

    def _dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

    def _angle_diff(a1: float, a2: float) -> float:
        d = abs(a1 - a2)
        return min(d, 360 - d)

    paths: List[List[Tuple[float, float]]] = []
    used = [False] * len(segments)

    for i, (p1, p2) in enumerate(segments):
        if used[i]:
            continue
        seg_angle = _angle(p1, p2)
        path = [p1, p2]
        used[i] = True

        changed = True
        while changed:
            changed = False
            for j, (q1, q2) in enumerate(segments):
                if used[j]:
                    continue
                seg_j_angle = _angle(q1, q2)
                if _angle_diff(seg_angle, seg_j_angle) > angle_tol_deg:
                    continue

                head, tail = path[0], path[-1]
                d_hq1 = _dist(head, q1)
                d_hq2 = _dist(head, q2)
                d_tq1 = _dist(tail, q1)
                d_tq2 = _dist(tail, q2)
                min_d = min(d_hq1, d_hq2, d_tq1, d_tq2)
                if min_d > max_gap:
                    continue

                if min_d == d_tq1:
                    path.append(q2)
                elif min_d == d_tq2:
                    path.append(q1)
                elif min_d == d_hq1:
                    path.insert(0, q2)
                else:
                    path.insert(0, q1)
                used[j] = True
                changed = True
                break

        paths.append(path)

    return paths


def _infer_line_type(path: List[Tuple[float, float]]) -> Literal["solid", "dashed"]:
    """依路徑點數推斷 solid/dashed（多點通常為合併後的虛線）"""
    return "dashed" if len(path) > 3 else "solid"


def detect_red_lines(
    img: np.ndarray,
    min_length: int = MIN_LINE_LENGTH,
    max_gap: float = MAX_LINE_GAP,
    min_path_length: float = MIN_PATH_LENGTH,
    exclude_polygons: Optional[List["RedPolygon"]] = None,
    exclude_markers: Optional[List["RedMarker"]] = None,
) -> List[RedLine]:
    """
    偵測紅色實線與虛線（路徑線，非多邊形邊框）。
    使用 Hough 線偵測 + 鄰近段合併，可排除多邊形區域。
    """
    h, w = img.shape[:2]
    roi = img[
        int(h * MAP_ROI_TOP):int(h * MAP_ROI_BOTTOM),
        int(w * MAP_ROI_LEFT):int(w * MAP_ROI_RIGHT),
    ]
    roi_h, roi_w = roi.shape[:2]
    offset_x = int(w * MAP_ROI_LEFT)
    offset_y = int(h * MAP_ROI_TOP)

    red_mask = _get_red_mask(roi)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    line_mask = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, kernel)
    line_mask = cv2.morphologyEx(line_mask, cv2.MORPH_OPEN, kernel)

    # 排除多邊形與標點區域，避免將邊框/圓弧誤檢為線段
    exclude_mask = np.zeros((roi_h, roi_w), dtype=np.uint8)
    if exclude_polygons:
        for poly in exclude_polygons:
            pts = np.array(
                [[p[0] - offset_x, p[1] - offset_y] for p in poly.pixel_polygon],
                dtype=np.int32,
            )
            cv2.fillPoly(exclude_mask, [pts], 255)
    if exclude_markers:
        for m in exclude_markers:
            cx, cy = int(m.center[0] - offset_x), int(m.center[1] - offset_y)
            r = int(m.radius) + 8
            if 0 <= cx < roi_w and 0 <= cy < roi_h:
                cv2.circle(exclude_mask, (cx, cy), max(r, 15), 255, -1)
    if np.any(exclude_mask > 0):
        dilate_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        exclude_mask = cv2.dilate(exclude_mask, dilate_k)
        line_mask = cv2.subtract(line_mask, exclude_mask)

    # Hough 線段偵測
    segments_raw = cv2.HoughLinesP(
        line_mask,
        rho=1,
        theta=np.pi / 180,
        threshold=20,
        minLineLength=min_length,
        maxLineGap=max_gap,
    )
    if segments_raw is None:
        return []

    segments: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
    for seg in segments_raw:
        x1, y1, x2, y2 = seg[0]
        segments.append(((float(x1), float(y1)), (float(x2), float(y2))))

    merged = _merge_line_segments(segments, max_gap=max_gap)

    lines: List[RedLine] = []
    for path in merged:
        if len(path) < 2:
            continue
        # 加回 ROI 偏移
        path_global = [
            (p[0] + offset_x, p[1] + offset_y) for p in path
        ]
        length = sum(
            ((path_global[i+1][0]-path_global[i][0])**2 + (path_global[i+1][1]-path_global[i][1])**2)**0.5
            for i in range(len(path_global)-1)
        )
        if length < min_path_length:
            continue
        line_type = _infer_line_type(path)
        conf = min(1.0, length / 100.0) * 0.5 + 0.5
        lines.append(RedLine(pixel_path=path_global, line_type=line_type, confidence=conf))

    return lines


def detect_red_markers(
    img: np.ndarray,
    min_area: int = MIN_MARKER_AREA,
    max_area: int = MAX_MARKER_AREA,
    min_circularity: float = MIN_MARKER_CIRCULARITY,
) -> List[RedMarker]:
    """
    偵測紅色圓形標點。
    以圓形度與面積篩選。
    """
    h, w = img.shape[:2]
    roi = img[
        int(h * MAP_ROI_TOP):int(h * MAP_ROI_BOTTOM),
        int(w * MAP_ROI_LEFT):int(w * MAP_ROI_RIGHT),
    ]
    offset_x = int(w * MAP_ROI_LEFT)
    offset_y = int(h * MAP_ROI_TOP)

    red_mask = _get_red_mask(roi)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, kernel)
    red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    markers: List[RedMarker] = []

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue
        peri = cv2.arcLength(cnt, True)
        if peri <= 0:
            continue
        circularity = 4 * np.pi * area / (peri * peri)
        if circularity < min_circularity:
            continue
        (cx, cy), r = cv2.minEnclosingCircle(cnt)
        center = (float(cx) + offset_x, float(cy) + offset_y)
        conf = min(1.0, circularity)
        markers.append(RedMarker(center=center, radius=float(r), marker_label=None, confidence=conf))

    return markers


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

    red_mask = _get_red_mask(roi)
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
        if area > MAX_POLYGON_AREA:
            continue

        peri = cv2.arcLength(cnt, True)
        if peri <= 0:
            continue
        circularity = 4 * np.pi * area / (peri * peri)
        if circularity > MAX_POLYGON_CIRCULARITY:
            continue

        # 近似多邊形
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
