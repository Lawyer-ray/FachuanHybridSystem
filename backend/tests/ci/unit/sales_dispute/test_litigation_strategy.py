"""起诉策略推荐引擎单元测试。"""
from __future__ import annotations

from decimal import Decimal

import pytest

from apps.sales_dispute.services.collection.litigation_strategy_service import (
    LitigationStrategyService,
    StrategyParams,
    PRESERVATION_THRESHOLD,
    SMALL_CLAIMS_RATIO,
    SUMMARY_THRESHOLD,
)


@pytest.fixture
def svc() -> LitigationStrategyService:
    return LitigationStrategyService()


def _params(**kwargs) -> StrategyParams:
    defaults = {
        "principal_amount": Decimal("100000"),
        "evidence_score": Decimal("50"),
        "solvency_rating": "poor",
        "local_avg_salary": Decimal("100000"),
        "willing_to_mediate": False,
    }
    defaults.update(kwargs)
    return StrategyParams(**defaults)


# ── recommend ──────────────────────────────────────────────────────────────

def test_recommend_mediation(svc: LitigationStrategyService) -> None:
    """有调解意愿推荐诉前调解。"""
    result = svc.recommend(_params(willing_to_mediate=True))
    assert result.strategy_type == "pre_litigation_mediation"
    assert "调解" in result.recommendation_reason


def test_recommend_payment_order(svc: LitigationStrategyService) -> None:
    """证据充分推荐支付令。"""
    result = svc.recommend(_params(evidence_score=Decimal("80")))
    assert result.strategy_type == "payment_order"


def test_recommend_payment_order_boundary(svc: LitigationStrategyService) -> None:
    """证据评分正好 70 推荐支付令。"""
    result = svc.recommend(_params(evidence_score=Decimal("70")))
    assert result.strategy_type == "payment_order"


def test_recommend_small_claims(svc: LitigationStrategyService) -> None:
    """标的额 <= 当地年均工资 30% 推荐小额诉讼。"""
    local_salary = Decimal("100000")
    threshold = local_salary * SMALL_CLAIMS_RATIO  # 30000
    result = svc.recommend(_params(
        principal_amount=threshold,
        evidence_score=Decimal("50"),
        local_avg_salary=local_salary,
    ))
    assert result.strategy_type == "small_claims"


def test_recommend_summary_procedure(svc: LitigationStrategyService) -> None:
    """标的额 <= 50 万推荐简易程序。"""
    result = svc.recommend(_params(
        principal_amount=Decimal("400000"),
        evidence_score=Decimal("50"),
        local_avg_salary=Decimal("10000"),  # 低工资，排除小额诉讼
    ))
    assert result.strategy_type == "summary_procedure"


def test_recommend_summary_boundary(svc: LitigationStrategyService) -> None:
    """标的额正好 50 万推荐简易程序。"""
    result = svc.recommend(_params(
        principal_amount=SUMMARY_THRESHOLD,
        evidence_score=Decimal("50"),
        local_avg_salary=Decimal("10000"),
    ))
    assert result.strategy_type == "summary_procedure"


def test_recommend_ordinary_procedure(svc: LitigationStrategyService) -> None:
    """标的额 > 50 万推荐普通程序。"""
    result = svc.recommend(_params(
        principal_amount=Decimal("1000000"),
        evidence_score=Decimal("50"),
        local_avg_salary=Decimal("10000"),
    ))
    assert result.strategy_type == "ordinary_procedure"


# ── preservation ───────────────────────────────────────────────────────────

def test_preservation_suggest_when_good_solvency(svc: LitigationStrategyService) -> None:
    """偿付能力好 + 标的额大 → 建议保全。"""
    result = svc.recommend(_params(
        principal_amount=Decimal("100000"),
        solvency_rating="good",
    ))
    assert result.suggest_preservation is True
    assert "保全" in result.preservation_reason


def test_preservation_suggest_when_fair_solvency(svc: LitigationStrategyService) -> None:
    """偿付能力一般 + 标的额大 → 建议保全。"""
    result = svc.recommend(_params(
        principal_amount=Decimal("100000"),
        solvency_rating="fair",
    ))
    assert result.suggest_preservation is True


def test_preservation_not_suggest_poor_solvency(svc: LitigationStrategyService) -> None:
    """偿付能力差 → 不建议保全。"""
    result = svc.recommend(_params(
        principal_amount=Decimal("100000"),
        solvency_rating="poor",
    ))
    assert result.suggest_preservation is False


def test_preservation_not_suggest_small_amount(svc: LitigationStrategyService) -> None:
    """标的额小 → 不建议保全。"""
    result = svc.recommend(_params(
        principal_amount=Decimal("1000"),
        solvency_rating="good",
    ))
    assert result.suggest_preservation is False


# ── edge cases ─────────────────────────────────────────────────────────────

def test_recommend_no_local_salary_excludes_small_claims(svc: LitigationStrategyService) -> None:
    """无当地工资时不推荐小额诉讼。"""
    result = svc.recommend(_params(
        principal_amount=Decimal("100"),
        evidence_score=Decimal("50"),
        local_avg_salary=None,
    ))
    # 标的额小但无工资信息，走简易程序
    assert result.strategy_type == "summary_procedure"


def test_recommend_estimated_duration_present(svc: LitigationStrategyService) -> None:
    """所有策略都有预估时长。"""
    for mediate in [True, False]:
        result = svc.recommend(_params(willing_to_mediate=mediate))
        assert result.estimated_duration


def test_recommend_applicable_conditions_present(svc: LitigationStrategyService) -> None:
    """所有策略都有适用条件。"""
    result = svc.recommend(_params())
    assert result.applicable_conditions


def test_priority_mediation_over_payment_order(svc: LitigationStrategyService) -> None:
    """调解优先于支付令。"""
    result = svc.recommend(_params(
        willing_to_mediate=True,
        evidence_score=Decimal("90"),
    ))
    assert result.strategy_type == "pre_litigation_mediation"
