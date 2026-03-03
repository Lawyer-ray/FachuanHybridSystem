"""抽帧辅助函数与数据类。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("apps.chat_records")


def safe_int(raw: Any, default: int) -> int:
    """安全转换为 int，失败返回 default。"""
    if raw is None:
        return default
    try:
        return int(raw)
    except Exception:
        logger.info(
            "safe_int 转换失败，使用默认值",
            extra={"raw": repr(raw), "default": default},
        )
        return default


def safe_float(
    raw: Any,
    default: float,
    lo: float | None = None,
    hi: float | None = None,
) -> float:
    """安全转换为 float，可选范围裁剪。"""
    if raw is None:
        return default
    try:
        v = float(raw)
    except Exception:
        logger.info(
            "safe_float 转换失败，使用默认值",
            extra={"raw": repr(raw), "default": default},
        )
        return default
    if lo is not None:
        v = max(v, lo)
    if hi is not None:
        v = min(v, hi)
    return v


def shingles(s: str, n: int = 3) -> set[str]:
    """文本 n-gram 分片。"""
    s = s or ""
    if not s:
        return set()
    if len(s) <= n:
        return {s}
    return {s[i : i + n] for i in range(0, len(s) - n + 1)}


def jaccard_sets(sa: set[str], sb: set[str]) -> float:
    """两个集合的 Jaccard 相似度。"""
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return float(inter) / float(union) if union else 0.0


@dataclass
class ExtractParams:
    """抽帧参数。"""

    interval_seconds: float = 1.0
    strategy: str = "interval"
    interval_based: bool = True
    dedup_threshold: int = 8
    ocr_similarity_threshold: float = 0.92
    ocr_min_new_chars: int = 8

    @classmethod
    def from_recording(cls, recording: Any, interval_seconds: float) -> ExtractParams:
        interval_seconds = safe_float(interval_seconds or 1.0, 1.0, lo=0.01)
        strategy = str(getattr(recording, "extract_strategy", "") or "interval").strip().lower()
        dedup_threshold = max(
            0,
            safe_int(getattr(recording, "extract_dedup_threshold", None), 8),
        )
        ocr_similarity_threshold = safe_float(
            getattr(recording, "extract_ocr_similarity_threshold", None),
            0.92,
            lo=0.0,
            hi=1.0,
        )
        ocr_min_new_chars = max(
            0,
            safe_int(getattr(recording, "extract_ocr_min_new_chars", None), 8),
        )
        return cls(
            interval_seconds=interval_seconds,
            strategy=strategy,
            interval_based=strategy in ("interval", "ocr"),
            dedup_threshold=dedup_threshold,
            ocr_similarity_threshold=ocr_similarity_threshold,
            ocr_min_new_chars=ocr_min_new_chars,
        )


@dataclass
class DedupState:
    """去重状态。"""

    existing_sha256: set[str] = field(default_factory=set)
    seen_sha256: set[str] = field(default_factory=set)
    kept_dhashes: list[str] = field(default_factory=list)
    kept_thumbs: list[bytes] = field(default_factory=list)
    kept_ocr_texts: list[str] = field(default_factory=list)
    kept_ocr_shingles: list[set[str]] = field(default_factory=list)
    created_count: int = 0
    processed_count: int = 0
    ocr_calls: int = 0
    ocr_skipped: int = 0
    ocr_disabled: bool = False
