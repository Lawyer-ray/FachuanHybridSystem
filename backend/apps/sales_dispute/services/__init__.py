"""
Sales Dispute Services 模块

子目录分组：
- assessment:  案件评估、证据评分、管辖权分析、成本收益分析
- calculation: 利息计算、诉讼时效、LPR利率、还款冲抵
- generation:  执行文书、律师函、对账函、和解协议、看板
- collection:  催收流程、催收提醒、诉讼策略
"""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "LprRateService",
    "RateSegment",
    "InterestCalculatorService",
    "InterestStartType",
    "RateType",
    "InterestCalcParams",
    "InterestCalcResult",
    "BatchDelivery",
    "SegmentDetail",
    "RepaymentOffsetService",
    "DebtItem",
    "OffsetDetail",
    "OffsetResult",
    "PaymentInput",
    "CostBenefitService",
    "CostBenefitParams",
    "CostBenefitResult",
    "CaseAssessmentService",
    "EvidenceScorerService",
    "JurisdictionAnalyzerService",
    "LimitationCalculatorService",
    "LitigationStrategyService",
    "CollectionWorkflowService",
    "CollectionReminderService",
    "LawyerLetterGeneratorService",
    "ReconciliationGeneratorService",
    "SettlementGeneratorService",
    "ExecutionDocGeneratorService",
    "DashboardService",
]

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    # calculation
    "LprRateService": (
        "apps.sales_dispute.services.calculation.lpr_rate_service",
        "LprRateService",
    ),
    "RateSegment": (
        "apps.sales_dispute.services.calculation.lpr_rate_service",
        "RateSegment",
    ),
    "InterestCalculatorService": (
        "apps.sales_dispute.services.calculation.interest_calculator_service",
        "InterestCalculatorService",
    ),
    "InterestStartType": (
        "apps.sales_dispute.services.calculation.interest_calculator_service",
        "InterestStartType",
    ),
    "RateType": (
        "apps.sales_dispute.services.calculation.interest_calculator_service",
        "RateType",
    ),
    "InterestCalcParams": (
        "apps.sales_dispute.services.calculation.interest_calculator_service",
        "InterestCalcParams",
    ),
    "InterestCalcResult": (
        "apps.sales_dispute.services.calculation.interest_calculator_service",
        "InterestCalcResult",
    ),
    "BatchDelivery": (
        "apps.sales_dispute.services.calculation.interest_calculator_service",
        "BatchDelivery",
    ),
    "SegmentDetail": (
        "apps.sales_dispute.services.calculation.interest_calculator_service",
        "SegmentDetail",
    ),
    "RepaymentOffsetService": (
        "apps.sales_dispute.services.calculation.repayment_offset_service",
        "RepaymentOffsetService",
    ),
    "DebtItem": (
        "apps.sales_dispute.services.calculation.repayment_offset_service",
        "DebtItem",
    ),
    "OffsetDetail": (
        "apps.sales_dispute.services.calculation.repayment_offset_service",
        "OffsetDetail",
    ),
    "OffsetResult": (
        "apps.sales_dispute.services.calculation.repayment_offset_service",
        "OffsetResult",
    ),
    "PaymentInput": (
        "apps.sales_dispute.services.calculation.repayment_offset_service",
        "PaymentInput",
    ),
    "LimitationCalculatorService": (
        "apps.sales_dispute.services.calculation.limitation_calculator_service",
        "LimitationCalculatorService",
    ),
    # assessment
    "CostBenefitService": (
        "apps.sales_dispute.services.assessment.cost_benefit_service",
        "CostBenefitService",
    ),
    "CostBenefitParams": (
        "apps.sales_dispute.services.assessment.cost_benefit_service",
        "CostBenefitParams",
    ),
    "CostBenefitResult": (
        "apps.sales_dispute.services.assessment.cost_benefit_service",
        "CostBenefitResult",
    ),
    "CaseAssessmentService": (
        "apps.sales_dispute.services.assessment.case_assessment_service",
        "CaseAssessmentService",
    ),
    "EvidenceScorerService": (
        "apps.sales_dispute.services.assessment.evidence_scorer_service",
        "EvidenceScorerService",
    ),
    "JurisdictionAnalyzerService": (
        "apps.sales_dispute.services.assessment.jurisdiction_analyzer_service",
        "JurisdictionAnalyzerService",
    ),
    # generation
    "LawyerLetterGeneratorService": (
        "apps.sales_dispute.services.generation.lawyer_letter_generator_service",
        "LawyerLetterGeneratorService",
    ),
    "ReconciliationGeneratorService": (
        "apps.sales_dispute.services.generation.reconciliation_generator_service",
        "ReconciliationGeneratorService",
    ),
    "SettlementGeneratorService": (
        "apps.sales_dispute.services.generation.settlement_generator_service",
        "SettlementGeneratorService",
    ),
    "ExecutionDocGeneratorService": (
        "apps.sales_dispute.services.generation.execution_doc_generator_service",
        "ExecutionDocGeneratorService",
    ),
    "DashboardService": (
        "apps.sales_dispute.services.generation.dashboard_service",
        "DashboardService",
    ),
    # collection
    "LitigationStrategyService": (
        "apps.sales_dispute.services.collection.litigation_strategy_service",
        "LitigationStrategyService",
    ),
    "CollectionWorkflowService": (
        "apps.sales_dispute.services.collection.collection_workflow_service",
        "CollectionWorkflowService",
    ),
    "CollectionReminderService": (
        "apps.sales_dispute.services.collection.collection_reminder_service",
        "CollectionReminderService",
    ),
}


def __getattr__(name: str) -> Any:
    if name in _LAZY_EXPORTS:
        module_path, attr_name = _LAZY_EXPORTS[name]
        module = importlib.import_module(module_path)
        return getattr(module, attr_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals().keys()) | set(__all__) | set(_LAZY_EXPORTS.keys()))
