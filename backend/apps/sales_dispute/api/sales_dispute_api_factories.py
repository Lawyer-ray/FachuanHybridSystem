"""买卖纠纷计算 API — 共享工厂函数与工具。"""

from __future__ import annotations

from datetime import date
from typing import Any


def _get_interest_calculator() -> Any:
    from apps.sales_dispute.services.calculation.interest_calculator_service import InterestCalculatorService

    return InterestCalculatorService()


def _get_cost_benefit_service() -> Any:
    from apps.sales_dispute.services.assessment.cost_benefit_service import CostBenefitService

    return CostBenefitService()


def _get_lpr_rate_service() -> Any:
    from apps.sales_dispute.services.calculation.lpr_rate_service import LprRateService

    return LprRateService()


def _get_case_assessment_service() -> Any:
    from apps.sales_dispute.services.assessment.case_assessment_service import CaseAssessmentService

    return CaseAssessmentService()


def _get_limitation_calculator() -> Any:
    from apps.sales_dispute.services.calculation.limitation_calculator_service import LimitationCalculatorService

    return LimitationCalculatorService()


def _get_jurisdiction_analyzer() -> Any:
    from apps.sales_dispute.services.assessment.jurisdiction_analyzer_service import JurisdictionAnalyzerService

    return JurisdictionAnalyzerService()


def _get_strategy_recommender() -> Any:
    from apps.sales_dispute.services.collection.litigation_strategy_service import LitigationStrategyService

    return LitigationStrategyService()


def _get_collection_workflow() -> Any:
    from apps.sales_dispute.services.collection.collection_workflow_service import CollectionWorkflowService

    return CollectionWorkflowService()


def _get_collection_reminder() -> Any:
    from apps.sales_dispute.services.collection.collection_reminder_service import CollectionReminderService

    return CollectionReminderService()


def _get_lawyer_letter_generator() -> Any:
    from apps.sales_dispute.services.generation.lawyer_letter_generator_service import LawyerLetterGeneratorService

    return LawyerLetterGeneratorService()


def _get_reconciliation_generator() -> Any:
    from apps.sales_dispute.services.generation.reconciliation_generator_service import ReconciliationGeneratorService

    return ReconciliationGeneratorService()


def _get_settlement_generator() -> Any:
    from apps.sales_dispute.services.generation.settlement_generator_service import SettlementGeneratorService

    return SettlementGeneratorService()


def _get_execution_doc_generator() -> Any:
    from apps.sales_dispute.services.generation.execution_doc_generator_service import ExecutionDocGeneratorService

    return ExecutionDocGeneratorService()


def _get_dashboard_service() -> Any:
    from apps.sales_dispute.services.generation.dashboard_service import DashboardService

    return DashboardService()


def _resolve_date_range(
    start_date: date | None,
    end_date: date | None,
) -> tuple[date, date]:
    """未提供日期时默认当前自然年"""
    today = date.today()
    return (
        start_date or date(today.year, 1, 1),
        end_date or date(today.year, 12, 31),
    )
