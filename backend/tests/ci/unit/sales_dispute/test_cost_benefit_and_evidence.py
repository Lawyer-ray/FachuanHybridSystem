"""成本收益分析与证据评分引擎单元测试。"""
from __future__ import annotations

import sys
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

# case_assessment_service.py has broken relative imports (limitation_calculator_service,
# litigation_strategy_service) - mock them before importing the assessment package
_forbidden_imports = [
    "apps.sales_dispute.services.assessment.limitation_calculator_service",
    "apps.sales_dispute.services.assessment.litigation_strategy_service",
]
for mod_name in _forbidden_imports:
    if mod_name not in sys.modules:
        mock_mod = MagicMock()
        sys.modules[mod_name] = mock_mod

from apps.sales_dispute.services.assessment.cost_benefit_service import (  # noqa: E402
    CostBenefitParams,
    CostBenefitService,
    DEFAULT_RATES,
)
from apps.sales_dispute.services.assessment.evidence_scorer_service import (  # noqa: E402
    EVIDENCE_WEIGHTS,
    EvidenceItem,
    EvidenceScorerService,
    GRADE_THRESHOLDS,
)


# ── CostBenefitService ─────────────────────────────────────────────────────

class TestCostBenefitService:

    def _service(self) -> CostBenefitService:
        mock_calc = MagicMock()
        mock_calc.calculate_property_case_fee.return_value = Decimal("5000")
        mock_calc.calculate_preservation_fee.return_value = Decimal("500")
        return CostBenefitService(fee_calculator=mock_calc)

    def test_analyze_basic(self) -> None:
        """基本成本收益分析。"""
        svc = self._service()
        params = CostBenefitParams(
            principal=Decimal("100000"),
            interest_amount=Decimal("10000"),
            lawyer_fee=Decimal("5000"),
        )
        result = svc.analyze(params)
        assert result.total_cost > Decimal("0")
        assert result.total_revenue > Decimal("0")

    def test_analyze_with_preservation(self) -> None:
        """有保全金额时计算保全费和担保费。"""
        svc = self._service()
        params = CostBenefitParams(
            principal=Decimal("100000"),
            interest_amount=Decimal("10000"),
            lawyer_fee=Decimal("5000"),
            preservation_amount=Decimal("50000"),
        )
        result = svc.analyze(params)
        assert result.cost_details["preservation_fee"] > Decimal("0")
        assert result.cost_details["guarantee_fee"] > Decimal("0")

    def test_analyze_negative_net_profit_risk_warning(self) -> None:
        """净收益为负时有风险提示。"""
        svc = self._service()
        params = CostBenefitParams(
            principal=Decimal("100"),
            interest_amount=Decimal("10"),
            lawyer_fee=Decimal("50000"),
        )
        result = svc.analyze(params)
        assert result.net_profit < Decimal("0")
        assert result.risk_warning is not None

    def test_analyze_positive_net_profit_no_warning(self) -> None:
        """净收益为正时无风险提示。"""
        svc = self._service()
        params = CostBenefitParams(
            principal=Decimal("1000000"),
            interest_amount=Decimal("100000"),
            lawyer_fee=Decimal("5000"),
        )
        result = svc.analyze(params)
        assert result.net_profit > Decimal("0")
        assert result.risk_warning is None

    def test_cost_details_complete(self) -> None:
        """成本明细包含所有费用项。"""
        svc = self._service()
        params = CostBenefitParams(
            principal=Decimal("100000"),
            interest_amount=Decimal("10000"),
            lawyer_fee=Decimal("5000"),
            notary_fee=Decimal("200"),
        )
        result = svc.analyze(params)
        assert "lawyer_fee" in result.cost_details
        assert "litigation_fee" in result.cost_details
        assert "preservation_fee" in result.cost_details
        assert "guarantee_fee" in result.cost_details
        assert "notary_fee" in result.cost_details


# ── EvidenceScorerService ──────────────────────────────────────────────────

class TestEvidenceScorerService:

    def _svc(self) -> EvidenceScorerService:
        return EvidenceScorerService()

    def test_all_evidence_present_high_quality(self) -> None:
        """所有证据都存在且质量高。"""
        items = [
            EvidenceItem(evidence_type=et, has_evidence=True, quality_score=100)
            for et in EVIDENCE_WEIGHTS
        ]
        result = self._svc().calculate(items)
        assert result.total_score == Decimal("100.00")
        assert result.grade == "sufficient"

    def test_no_evidence(self) -> None:
        """无证据总分为 0。"""
        items = [
            EvidenceItem(evidence_type=et, has_evidence=False, quality_score=0)
            for et in EVIDENCE_WEIGHTS
        ]
        result = self._svc().calculate(items)
        assert result.total_score == Decimal("0.00")
        assert result.grade == "severely_insufficient"

    def test_grade_thresholds(self) -> None:
        """评分等级判定。"""
        svc = self._svc()
        assert svc._determine_grade(Decimal("95")) == "sufficient"
        assert svc._determine_grade(Decimal("80")) == "fairly_sufficient"
        assert svc._determine_grade(Decimal("60")) == "average"
        assert svc._determine_grade(Decimal("40")) == "weak"
        assert svc._determine_grade(Decimal("10")) == "severely_insufficient"

    def test_unknown_evidence_type_weight_zero(self) -> None:
        """未知证据类型权重为 0。"""
        items = [EvidenceItem(evidence_type="unknown_type", has_evidence=True, quality_score=100)]
        result = self._svc().calculate(items)
        assert result.total_score == Decimal("0.00")

    def test_empty_items(self) -> None:
        """空输入返回 0 分。"""
        result = self._svc().calculate([])
        assert result.total_score == Decimal("0.00")
        assert result.details == []
