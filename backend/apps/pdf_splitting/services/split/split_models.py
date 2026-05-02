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


@dataclass
class PageDescriptor:
    page_no: int
    text: str
    normalized_text: str
    head_text: str
    source_method: str
    ocr_failed: bool
    top_candidates: list[dict[str, Any]]


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
