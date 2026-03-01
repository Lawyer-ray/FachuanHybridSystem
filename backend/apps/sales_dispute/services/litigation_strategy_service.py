"""
起诉策略推荐引擎

按优先级评估并推荐最适合的诉讼策略
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

logger = logging.getLogger(__name__)

PRESERVATION_THRESHOLD: Decimal = Decimal("50000")
SMALL_CLAIMS_RATIO: Decimal = Decimal("0.3")
SUMMARY_THRESHOLD: Decimal = Decimal("500000")


@dataclass(frozen=True)
class StrategyParams:
    """策略推荐参数"""

    principal_amount: Decimal
    evidence_score: Decimal
    solvency_rating: str
    local_avg_salary: Decimal | None
    willing_to_mediate: bool


@dataclass(frozen=True)
class StrategyResult:
    """策略推荐结果"""

    strategy_type: str
    recommendation_reason: str
    estimated_duration: str
    applicable_conditions: str
    suggest_preservation: bool
    preservation_reason: str


class LitigationStrategyService:
    """起诉策略推荐服务"""

    def recommend(self, params: StrategyParams) -> StrategyResult:
        """
        按优先级评估策略：

        1. 有调解意愿 → 诉前调解
        2. 债权明确 + 证据充分(≥70) → 支付令
        3. 标的额 ≤ 当地年均工资30% → 小额诉讼
        4. 事实清楚 + 标的额 ≤ 50万 → 简易程序
        5. 以上均不满足 → 普通程序
        """
        suggest_preservation, preservation_reason = self._check_preservation(
            params
        )

        if params.willing_to_mediate:
            return StrategyResult(
                strategy_type="pre_litigation_mediation",
                recommendation_reason="当事人有调解意愿，诉前调解成本低、效率高",
                estimated_duration="1个月",
                applicable_conditions="双方均有调解意愿",
                suggest_preservation=suggest_preservation,
                preservation_reason=preservation_reason,
            )

        if params.evidence_score >= Decimal("70"):
            return StrategyResult(
                strategy_type="payment_order",
                recommendation_reason=(
                    "债权债务关系明确，证据充分（评分≥70），"
                    "符合支付令申请条件，程序简便快捷"
                ),
                estimated_duration="15天",
                applicable_conditions=(
                    "债权人请求债务人给付金钱、有价证券，"
                    "且债权债务关系明确、合法"
                ),
                suggest_preservation=suggest_preservation,
                preservation_reason=preservation_reason,
            )

        if (
            params.local_avg_salary is not None
            and params.principal_amount
            <= params.local_avg_salary * SMALL_CLAIMS_RATIO
        ):
            return StrategyResult(
                strategy_type="small_claims",
                recommendation_reason=(
                    f"标的额{params.principal_amount}元≤当地年均工资30%"
                    f"（{params.local_avg_salary * SMALL_CLAIMS_RATIO}元），"
                    "适用小额诉讼程序，一审终审"
                ),
                estimated_duration="1-2个月",
                applicable_conditions=(
                    "事实清楚、权利义务关系明确、争议不大，"
                    "标的额不超过当地上年度就业人员年平均工资30%"
                ),
                suggest_preservation=suggest_preservation,
                preservation_reason=preservation_reason,
            )

        if params.principal_amount <= SUMMARY_THRESHOLD:
            return StrategyResult(
                strategy_type="summary_procedure",
                recommendation_reason=(
                    f"标的额{params.principal_amount}元≤50万元，"
                    "事实清楚，适用简易程序审理"
                ),
                estimated_duration="3个月",
                applicable_conditions=(
                    "事实清楚、权利义务关系明确、争议不大的简单民事案件"
                ),
                suggest_preservation=suggest_preservation,
                preservation_reason=preservation_reason,
            )

        return StrategyResult(
            strategy_type="ordinary_procedure",
            recommendation_reason=(
                f"标的额{params.principal_amount}元超过50万元，"
                "案件较为复杂，适用普通程序审理"
            ),
            estimated_duration="6个月",
            applicable_conditions="不符合简易程序或小额诉讼条件的一般民事案件",
            suggest_preservation=suggest_preservation,
            preservation_reason=preservation_reason,
        )

    def _check_preservation(
        self, params: StrategyParams
    ) -> tuple[bool, str]:
        """检查是否建议财产保全"""
        if (
            params.solvency_rating in ("good", "fair")
            and params.principal_amount > PRESERVATION_THRESHOLD
        ):
            return (
                True,
                f"偿付能力评级为{params.solvency_rating}，"
                f"标的额{params.principal_amount}元超过5万元，"
                "建议申请财产保全以保障债权实现",
            )
        return False, ""
