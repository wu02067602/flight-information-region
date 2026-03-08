"""
OCR 與表格結構化（Gemini API）
抽取左上角表格，輸出固定欄位 JSON。
"""
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image

from .config import GEMINI_API_KEY, GEMINI_MODEL, TABLE_ROI_BOTTOM, TABLE_ROI_LEFT, TABLE_ROI_RIGHT, TABLE_ROI_TOP


@dataclass
class TableRow:
    """單一表格列"""
    item_no: Optional[str]  # 項次 ①②③
    event_time: Optional[str]
    aircraft_type: Optional[str]
    mission_type: Optional[str]
    flight_no: Optional[str]
    remarks: Optional[str]
    raw_text: str


def _ensure_gemini():
    if not GEMINI_API_KEY:
        raise ValueError("請設定 GEMINI_API_KEY 環境變數")
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    return genai


def _pil_from_bgr(bgr: np.ndarray) -> Image.Image:
    rgb = bgr[:, :, ::-1]
    return Image.fromarray(rgb)


def extract_table_ocr(
    img: np.ndarray,
    raw_text_fallback: str = "",
) -> tuple[List[TableRow], str, float, Optional[str]]:
    """
    對左上角表格 ROI 做 OCR，結構化為 JSON。
    回傳 (rows, ocr_raw_text, confidence, error_code)
    """
    try:
        genai = _ensure_gemini()
    except ValueError as e:
        return [], raw_text_fallback, 0.0, "NO_API_KEY"

    h, w = img.shape[:2]
    roi = img[
        int(h * TABLE_ROI_TOP):int(h * TABLE_ROI_BOTTOM),
        int(w * TABLE_ROI_LEFT):int(w * TABLE_ROI_RIGHT),
    ]
    pil_img = _pil_from_bgr(roi)

    prompt = """請分析這張圖片中的左上角表格，輸出固定欄位的 JSON 陣列。
每列代表一筆事件，欄位：
- item_no: 項次（如 ①、②、③ 或 1、2、3）
- event_time: 時間（格式 YYYY-MM-DD HH:MM 或原文）
- aircraft_type: 機型/類型
- mission_type: 類型（若與機型合併則填同一欄）
- flight_no: 架次
- remarks: 備註

若無表格或無法辨識，回傳空陣列 []。
只輸出 JSON，不要其他說明文字。"""

    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content([prompt, pil_img])
        text = (getattr(response, "text", None) or "").strip()
    except Exception as e:
        return [], raw_text_fallback, 0.0, f"GEMINI_ERROR:{str(e)[:50]}"

    # 解析 JSON
    text_clean = re.sub(r"```[\w]*\n?", "", text)
    try:
        data = json.loads(text_clean)
    except json.JSONDecodeError:
        return [], text, 0.3, "JSON_PARSE_ERROR"

    if not isinstance(data, list):
        return [], text, 0.3, "INVALID_FORMAT"

    rows: List[TableRow] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        rows.append(TableRow(
            item_no=str(item.get("item_no", "") or ""),
            event_time=str(item.get("event_time", "") or ""),
            aircraft_type=str(item.get("aircraft_type", "") or ""),
            mission_type=str(item.get("mission_type", "") or ""),
            flight_no=str(item.get("flight_no", "") or ""),
            remarks=str(item.get("remarks", "") or ""),
            raw_text=json.dumps(item, ensure_ascii=False),
        ))

    # 信心：欄位完整度 + 列數合理性
    filled = sum(1 for r in rows if any([r.item_no, r.event_time, r.aircraft_type]))
    completeness = filled / len(rows) if rows else 0
    confidence = 0.5 * completeness + 0.5 * min(1.0, len(rows) / 2)

    return rows, text, min(1.0, confidence), None


def compute_ocr_confidence_breakdown(rows: List[TableRow], raw_text: str) -> Dict[str, Any]:
    """信心分數細項"""
    n = len(rows)
    filled = sum(1 for r in rows if any([r.item_no, r.event_time, r.aircraft_type]))
    return {
        "row_count": n,
        "filled_count": filled,
        "completeness": filled / n if n else 0,
        "raw_length": len(raw_text),
    }
