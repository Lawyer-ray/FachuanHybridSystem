"""数据模型：dataclass + 常量 + levenshtein。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_WINDOWS_ABS_RE = re.compile(r"^[A-Za-z]:[\\/]")
_NON_WORD_RE = re.compile(r"\s+")
_TEXT_MIN_LENGTH = 12


def _levenshtein_distance(s1: str, s2: str) -> int:
    """计算两个字符串的 Levenshtein 编辑距离。"""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if not s2:
        return len(s1)
    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            cost = 0 if c1 == c2 else 1
            curr_row.append(min(curr_row[j] + 1, prev_row[j + 1] + 1, prev_row[j] + cost))
        prev_row = curr_row
    return prev_row[-1]


#: 取字路径判定的材料类别。写进 summary 供排障与前端提示，不用来「换后端」。
MATERIAL_KIND_DIGITAL_PDF = "digital_pdf"
MATERIAL_KIND_SCANNED_PDF = "scanned_pdf"
MATERIAL_KIND_MIXED_PDF = "mixed_pdf"

#: 判定「电子版 / 扫描件」时抽样的页数（首、中、尾）。
#: 不读全文：判定只是选路，为它把整本扫一遍等于把最贵的 IO 做两遍。
_TEXT_SAMPLE_PAGES = 3


@dataclass
class PageDescriptor:
    page_no: int
    text: str
    normalized_text: str
    head_text: str
    source_method: str
    ocr_failed: bool
    top_candidates: list[dict[str, Any]]
    layout: dict[str, Any] | None = None
    layout_title: str = ""


@dataclass
class SegmentDraft:
    order: int
    page_start: int
    page_end: int
    segment_type: str
    filename: str
    confidence: float
    source_method: str
    review_flag: str


@dataclass(frozen=True)
class OCRRuntimeProfile:
    key: str
    use_v5: bool
    dpi: int
    workers: int


@dataclass(frozen=True)
class OCRPageResult:
    page_no: int
    text: str
    source_method: str
    ocr_failed: bool
    layout: dict[str, Any] | None = None


def classify_pdf_material(doc: Any, *, is_effective_text: Any) -> str:
    """抽样判定一份 PDF 属于电子版 / 扫描件 / 混合。

    只抽首、中、尾至多 ``_TEXT_SAMPLE_PAGES`` 页读文本层，不扫全文——
    判定只是选路，为它把整本走一遍等于把最贵的 IO 做两遍。

    三档语义：
      · digital_pdf：抽到的页都有有效文本层 —— 电子版，文本层抽字最准也最便宜
      · scanned_pdf：抽到的页全无有效文本层 —— 扫描件，必须 OCR / 云端视觉
      · mixed_pdf：部分有部分没有 —— 同一本里混了扫描页（附件总是扫描件的
        常态），逐页调度会各自选路，这里只如实标注，不用来一刀切

    Args:
        doc: 已打开的 PyMuPDF Document。
        is_effective_text: 判定文本层是否有效的回调用（复用 SegmentDetector 的
            口径，避免这里再定义一份「多少字算有字」）。

    Returns:
        上: MATERIAL_KIND_* 之一。总页数为 0 时返回 scanned_pdf（无内容可抽）。
    """
    try:
        total = int(doc.page_count)
    except (TypeError, ValueError):
        return MATERIAL_KIND_SCANNED_PDF
    if total <= 0:
        return MATERIAL_KIND_SCANNED_PDF

    # 首、中、尾；去重后保持顺序（总页数少时 _TEXT_SAMPLE_PAGES 会重样）
    indexes = sorted({0, total // 2, total - 1})
    hits = 0
    for index in indexes:
        try:
            text = doc.load_page(index).get_text("text") or ""
        except Exception:  # 单页读不出来不能拖垮整份判定
            continue
        if is_effective_text(text):
            hits += 1

    if hits == 0:
        return MATERIAL_KIND_SCANNED_PDF
    if hits == len(indexes):
        return MATERIAL_KIND_DIGITAL_PDF
    return MATERIAL_KIND_MIXED_PDF


# ↓↓ 版面标题提取（纯函数；由 service.py 下沉，pipeline / service 共用）
def extract_layout_title(layout: dict[str, Any] | None) -> str:
    """取解析器标记为标题的短文本块，用于开放集材料命名和边界提示。"""
    if not layout:
        return ""
    blocks = layout.get("blocks")
    if not isinstance(blocks, list):
        return ""

    title_types = {"title", "text_level_title", "heading", "标题"}
    candidates: list[tuple[float, int, str]] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "").strip().lower()
        is_title = block_type in title_types or block.get("text_level") not in (None, "", 0, "0")
        text = " ".join(str(block.get("text") or "").split()).strip(" #\t\r\n")
        if not is_title or not text or len(text) > 48:
            continue
        bbox = block.get("bbox")
        y = 0.0
        if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
            try:
                y = float(bbox[1])
            except (TypeError, ValueError):
                y = 0.0
        candidates.append((y, -len(text), text))
    if not candidates:
        return ""
    candidates.sort()
    return candidates[0][2]
