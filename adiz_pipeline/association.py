"""
紅框與表格關聯
優先用編號（①②③）一對一關聯。
支援線段、標點與表格列的關聯。
"""
from typing import Dict, List, Optional, Tuple

from .ocr_gemini import TableRow
from .red_detector import RedLine, RedMarker, RedPolygon


# 編號對照
CIRCLE_NUMBERS = "①②③④⑤⑥⑦⑧⑨⑩"
DIGIT_NUMBERS = "123456789"

# 標點與線段關聯的距離門檻（像素）
MARKER_LINE_DISTANCE_THRESHOLD = 25


def _parse_item_no(item_no: Optional[str]) -> Optional[int]:
    """將項次轉為 1-based 索引"""
    if not item_no or not str(item_no).strip():
        return None
    s = str(item_no).strip()
    if s in CIRCLE_NUMBERS:
        return CIRCLE_NUMBERS.index(s) + 1
    if s.isdigit():
        return int(s)
    return None


def associate_polygons_to_rows(
    polygons: List[RedPolygon],
    rows: List[TableRow],
) -> List[Tuple[int, int, float]]:
    """
    建立紅框與表格列的關聯。
    回傳 [(polygon_idx, row_idx, confidence), ...]
    """
    associations: List[Tuple[int, int, float]] = []

    # 優先：編號一對一
    for pi, poly in enumerate(polygons):
        best_row = None
        best_conf = 0.0
        for ri, row in enumerate(rows):
            idx = _parse_item_no(row.item_no)
            if idx is not None and idx == pi + 1:
                best_row = ri
                best_conf = 0.9
                break
        if best_row is not None:
            associations.append((pi, best_row, best_conf))

    # 未匹配的：依順序保守對應
    matched_p = {a[0] for a in associations}
    matched_r = {a[1] for a in associations}
    unmatched_p = [i for i in range(len(polygons)) if i not in matched_p]
    unmatched_r = [i for i in range(len(rows)) if i not in matched_r]

    for i, (pi, ri) in enumerate(zip(unmatched_p, unmatched_r)):
        associations.append((pi, ri, 0.5))  # 低信心

    return associations


def _point_to_segment_dist(
    px: float, py: float,
    seg_start: Tuple[float, float], seg_end: Tuple[float, float],
) -> float:
    """點到線段的最近距離"""
    x1, y1 = seg_start
    x2, y2 = seg_end
    dx, dy = x2 - x1, y2 - y1
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
    t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / length_sq))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return ((px - proj_x) ** 2 + (py - proj_y) ** 2) ** 0.5


def associate_markers_to_lines(
    lines: List[RedLine],
    markers: List[RedMarker],
    distance_threshold: float = MARKER_LINE_DISTANCE_THRESHOLD,
) -> Dict[int, List[int]]:
    """
    建立標點與線段的關聯。
    回傳 {line_idx: [marker_idx, ...]}，每個線段對應其上的標點。
    """
    line_to_markers: Dict[int, List[int]] = {i: [] for i in range(len(lines))}

    for mi, marker in enumerate(markers):
        cx, cy = marker.center
        best_line = None
        best_dist = float("inf")

        for li, line in enumerate(lines):
            path = line.pixel_path
            min_dist = float("inf")
            for j in range(len(path) - 1):
                d = _point_to_segment_dist(cx, cy, path[j], path[j + 1])
                min_dist = min(min_dist, d)
            if min_dist < best_dist and min_dist <= distance_threshold:
                best_dist = min_dist
                best_line = li

        if best_line is not None:
            line_to_markers[best_line].append(mi)

    return line_to_markers


def associate_lines_to_rows(
    lines: List[RedLine],
    markers: List[RedMarker],
    marker_to_line: Dict[int, List[int]],
    rows: List[TableRow],
    polygon_count: int = 0,
) -> List[Tuple[int, int, float]]:
    """
    建立線段與表格列的關聯。
    回傳 [(line_idx, row_idx, confidence), ...]
    優先以標點對應的 item_no 匹配，失敗則依順序保守配對。
    """
    associations: List[Tuple[int, int, float]] = []

    # 找出可能是線段對應的 row（item_no ④⑤⑥... 等，通常為氣球/航線類）
    line_row_indices: List[int] = []
    for ri, row in enumerate(rows):
        idx = _parse_item_no(row.item_no)
        if idx is not None and idx > polygon_count:
            line_row_indices.append(ri)

    # 依線段中心排序，與 line_row_indices 順序對應
    def line_centroid(li: int) -> Tuple[float, float]:
        path = lines[li].pixel_path
        n = len(path)
        return (sum(p[0] for p in path) / n, sum(p[1] for p in path) / n)

    sorted_line_indices = sorted(
        range(len(lines)),
        key=lambda li: (line_centroid(li)[1], line_centroid(li)[0]),
    )

    for i, li in enumerate(sorted_line_indices):
        marker_indices = marker_to_line.get(li, [])
        best_row = None
        best_conf = 0.5

        if marker_indices and i < len(line_row_indices):
            # 有標點：嘗試以標點順序對應 item_no
            row_idx = line_row_indices[i]
            idx = _parse_item_no(rows[row_idx].item_no)
            if idx is not None:
                best_row = row_idx
                best_conf = 0.9
        elif i < len(line_row_indices):
            best_row = line_row_indices[i]
            best_conf = 0.7

        if best_row is not None:
            associations.append((li, best_row, best_conf))

    return associations
