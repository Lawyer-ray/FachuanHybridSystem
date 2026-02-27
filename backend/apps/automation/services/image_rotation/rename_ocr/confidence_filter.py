"""
OCR 结果置信度过滤器

根据置信度分数过滤低质量文本块，减少传给 LLM 的噪声。

Requirements: 3.1, 3.2, 3.3, 3.4, 6.3
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("apps.automation.image_rotation")


@dataclass
class FilterResult:
    """过滤结果"""

    texts: list[str]
    scores: list[float]
    overall_confidence: float


class ConfidenceFilter:
    """置信度过滤器 - 过滤低置信度文本块"""

    def __init__(self, min_confidence: float = 0.5) -> None:
        self._min_confidence = min_confidence

    def filter(
        self,
        texts: list[str],
        scores: list[float],
    ) -> FilterResult:
        """
        过滤低置信度文本块。

        过滤后为空时返回全部原始文本（避免丢失所有信息）。
        计算过滤后文本块的平均置信度作为 overall_confidence。
        """
        if not texts or not scores:
            return FilterResult(texts=[], scores=[], overall_confidence=0.0)

        filtered_texts: list[str] = []
        filtered_scores: list[float] = []

        for text, score in zip(texts, scores):
            if score >= self._min_confidence:
                filtered_texts.append(text)
                filtered_scores.append(score)

        # 过滤后为空时返回全部原始文本
        if not filtered_texts:
            logger.debug(
                "置信度过滤: 全部 %d 个文本块低于阈值 %.2f, 返回原始文本",
                len(texts),
                self._min_confidence,
            )
            overall = sum(scores) / len(scores)
            return FilterResult(
                texts=list(texts),
                scores=list(scores),
                overall_confidence=overall,
            )

        overall = sum(filtered_scores) / len(filtered_scores)

        logger.debug(
            "置信度过滤: %d -> %d 个文本块 (阈值 %.2f)",
            len(texts),
            len(filtered_texts),
            self._min_confidence,
        )

        return FilterResult(
            texts=filtered_texts,
            scores=filtered_scores,
            overall_confidence=overall,
        )
