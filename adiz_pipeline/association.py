"""
紅框與表格關聯
優先用編號（①②③）一對一關聯。
"""
from typing import List, Optional, Tuple

from .ocr_gemini import TableRow
from .red_detector import RedPolygon


# 編號對照
CIRCLE_NUMBERS = "①②③④⑤⑥⑦⑧⑨⑩"
DIGIT_NUMBERS = "123456789"


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
