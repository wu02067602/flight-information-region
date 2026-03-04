"""
OCR 與表格結構化
只對左上角表格 ROI 做 OCR，解析固定欄位
"""
import re
import logging
from typing import Any

from config import TABLE_ROI_RATIO

logger = logging.getLogger(__name__)


def extract_table_roi(img, ratio: tuple[float, float, float, float] = TABLE_ROI_RATIO):
    """擷取表格 ROI 區域"""
    h, w = img.shape[:2]
    x1 = int(ratio[0] * w)
    y1 = int(ratio[1] * h)
    x2 = int((ratio[0] + ratio[2]) * w)
    y2 = int((ratio[1] + ratio[3]) * h)
    return img[y1:y2, x1:x2]


def run_ocr(roi_img) -> list[dict[str, Any]]:
    """
    使用 PaddleOCR 對 ROI 做文字辨識
    回傳: [{"text": str, "confidence": float, "bbox": [[x,y],...]}, ...]
    """
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        logger.warning("PaddleOCR 未安裝。請執行: pip install paddlepaddle paddleocr")
        return []

    try:
        ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
        result = ocr.ocr(roi_img, cls=True)
        if not result or not result[0]:
            return []

        items = []
        for line in result[0]:
            if len(line) >= 2:
                bbox = [[int(p[0]), int(p[1])] for p in line[0]]
                text = (line[1][0] or "").strip()
                conf = float(line[1][1] or 0)
                items.append({"text": text, "confidence": conf, "bbox": bbox})
        return items
    except Exception as e:
        logger.error("OCR 執行失敗: %s", e)
        return []


def parse_table_fields(ocr_items: list[dict]) -> list[dict[str, Any]]:
    """
    解析 OCR 結果為固定欄位
    欄位：項次、時間、機型/類型、架次、備註
    優先用編號（①②③）關聯
    """
    # 合併文字行
    lines = []
    for item in ocr_items:
        t = item.get("text", "")
        if t:
            lines.append(t)

    full_text = "\n".join(lines)
    events = []

    # 項次模式：①②③ 或 1. 2. 3.
    item_pattern = re.compile(r"[①②③④⑤⑥⑦⑧⑨⑩]|\d+[\.\s]")
    time_pattern = re.compile(
        r"(\d{4})[/\-年](\d{1,2})[/\-月](\d{1,2})[日]?\s*(\d{1,2})[:：](\d{2})"
    )
    sorties_pattern = re.compile(r"(\d+)\s*架?次?")

    # 簡化：依行解析，嘗試提取欄位
    current_item = None
    current_event = {}

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 檢查是否為新項次
        item_match = item_pattern.match(line)
        if item_match:
            if current_event:
                events.append(current_event)
            current_item = item_match.group(0).strip(".")
            current_event = {
                "item_number": current_item,
                "event_time": None,
                "aircraft_type": None,
                "sorties": None,
                "remarks": None,
                "raw_line": line,
            }

        # 時間
        tm = time_pattern.search(line)
        if tm and current_event is not None:
            current_event["event_time"] = f"{tm.group(1)}-{tm.group(2).zfill(2)}-{tm.group(3).zfill(2)} {tm.group(4).zfill(2)}:{tm.group(5)}"

        # 架次
        sm = sorties_pattern.search(line)
        if sm and current_event is not None and current_event.get("sorties") is None:
            current_event["sorties"] = sm.group(1)

        # 機型常見關鍵字
        if current_event and not current_event.get("aircraft_type"):
            for kw in ["殲", "轟", "運", "偵", "反潛", "無人機", "戰機", "運輸機"]:
                if kw in line:
                    current_event["aircraft_type"] = line
                    break

    if current_event:
        events.append(current_event)

    # 若無項次，整段當單一事件
    if not events and full_text.strip():
        events.append({
            "item_number": None,
            "event_time": None,
            "aircraft_type": None,
            "sorties": None,
            "remarks": full_text[:200],
            "raw_line": full_text,
        })

    return events


def extract_table_from_image(img) -> tuple[str, list[dict[str, Any]]]:
    """
    從圖片抽取左上角表格，回傳 (原始 OCR 文字, 結構化事件列表)
    """
    roi = extract_table_roi(img)
    ocr_items = run_ocr(roi)
    raw_text = " ".join(item.get("text", "") for item in ocr_items)
    events = parse_table_fields(ocr_items)
    return raw_text, events
