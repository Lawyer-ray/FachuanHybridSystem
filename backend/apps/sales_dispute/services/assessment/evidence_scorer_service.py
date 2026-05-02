"""
证据完整度评分引擎

按5种证据类型加权计算证据链完整度得分（0-100）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

logger = logging.getLogger(__name__)

# 证据权重配置
EVIDENCE_WEIGHTS: dict[str, Decimal] = {
    "written_contract": Decimal("0.25"),
    "delivery_receipt": Decimal("0.25"),
    "reconciliation": Decimal("0.20"),
    "collection_record": Decimal("0.15"),
    "payment_record": Decimal("0.15"),
}

# 评分等级阈值（降序）
GRADE_THRESHOLDS: list[tuple[int, str]] = [
    (90, "sufficient"),
    (70, "fairly_sufficient"),
    (50, "average"),
    (30, "weak"),
    (0, "severely_insufficient"),
]


@dataclass(frozen=True)
class EvidenceItem:
    """证据条目输入"""

    evidence_type: str
    has_evidence: bool
    quality_score: int  # 0-100


@dataclass(frozen=True)
class EvidenceItemResult:
    """单项证据评分结果"""

    evidence_type: str
    has_evidence: bool
    quality_score: int
    weight: Decimal
    weighted_score: Decimal


@dataclass(frozen=True)
class EvidenceScoreResult:
    """证据评分结果"""

    total_score: Decimal
    grade: str
    details: list[EvidenceItemResult]


class EvidenceScorerService:
    """证据完整度评分服务"""

    def calculate(self, items: list[EvidenceItem]) -> EvidenceScoreResult:
        """
        计算证据完整度总分。

        - 不具备的证据类型，质量评分视为 0
        - 总分 = Σ(质量评分 × 权重)
        - 根据总分判定等级
        """
        details: list[EvidenceItemResult] = []
        total = Decimal("0")

        for item in items:
            weight = EVIDENCE_WEIGHTS.get(item.evidence_type, Decimal("0"))
            effective_score = item.quality_score if item.has_evidence else 0
            weighted = Decimal(str(effective_score)) * weight
            weighted = weighted.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            total += weighted
            details.append(
                EvidenceItemResult(
                    evidence_type=item.evidence_type,
                    has_evidence=item.has_evidence,
                    quality_score=effective_score,
                    weight=weight,
                    weighted_score=weighted,
                )
            )

        total = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        grade = self._determine_grade(total)
        return EvidenceScoreResult(total_score=total, grade=grade, details=details)

    def _determine_grade(self, score: Decimal) -> str:
        """根据总分判定评分等级"""
        for threshold, grade in GRADE_THRESHOLDS:
            if score >= threshold:
                return grade
        return "severely_insufficient"
