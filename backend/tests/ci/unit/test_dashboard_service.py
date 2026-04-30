"""Unit tests for DashboardService (sales_dispute)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.sales_dispute.services.dashboard_service import (
    DashboardService,
    _lawyer_display_name,
    _safe_rate,
)


@pytest.fixture
def svc() -> DashboardService:
    return DashboardService()


@pytest.fixture
def setup_data(db):
    """Create test data for dashboard tests."""
    from apps.cases.models import Case
    from apps.cases.models.party import CaseAssignment
    from apps.organization.models import LawFirm, Lawyer
    from apps.sales_dispute.models.case_assessment import CaseAssessment, ContractBasisType
    from apps.sales_dispute.models.collection_record import CollectionRecord, CollectionStage
    from apps.sales_dispute.models.payment_record import PaymentRecord

    firm = LawFirm.objects.create(name="Dashboard测试律所")
    lawyer1 = Lawyer.objects.create_user(
        username="dash_lawyer_1",
        email="dash1@example.com",
        real_name="张三",
        law_firm=firm,
    )
    lawyer2 = Lawyer.objects.create_user(
        username="dash_lawyer_2",
        email="dash2@example.com",
        real_name="李四",
        law_firm=firm,
    )

    today = date.today()

    # Cases - start_date is auto_now_add, so update after creation
    case1 = Case.objects.create(name="Dashboard案件1", contract=None)
    Case.objects.filter(pk=case1.pk).update(
        start_date=today - timedelta(days=100),
        target_amount=Decimal("200000"),
        status="active",
        case_type="civil",
        preservation_amount=Decimal("50000"),
    )

    case2 = Case.objects.create(name="Dashboard案件2", contract=None)
    Case.objects.filter(pk=case2.pk).update(
        start_date=today - timedelta(days=400),
        target_amount=Decimal("800000"),
        status="closed",
        case_type="criminal",
        preservation_amount=None,
    )

    case3 = Case.objects.create(name="Dashboard案件3", contract=None)
    Case.objects.filter(pk=case3.pk).update(
        start_date=today - timedelta(days=800),
        target_amount=Decimal("50000"),
        status="active",
        case_type="civil",
        preservation_amount=Decimal("0"),
    )

    # Payments
    PaymentRecord.objects.create(
        case=case1,
        payment_date=today - timedelta(days=30),
        payment_amount=Decimal("100000"),
        remaining_principal=Decimal("100000"),
    )
    PaymentRecord.objects.create(
        case=case2,
        payment_date=today - timedelta(days=20),
        payment_amount=Decimal("300000"),
        remaining_principal=Decimal("500000"),
    )
    PaymentRecord.objects.create(
        case=case1,
        payment_date=today - timedelta(days=10),
        payment_amount=Decimal("50000"),
        remaining_principal=Decimal("50000"),
    )

    # Assignments
    CaseAssignment.objects.create(case=case1, lawyer=lawyer1)
    CaseAssignment.objects.create(case=case2, lawyer=lawyer2)
    CaseAssignment.objects.create(case=case3, lawyer=lawyer1)

    # Assessments
    CaseAssessment.objects.create(
        case=case1,
        contract_basis=ContractBasisType.WRITTEN,
        principal_amount=Decimal("200000"),
        evidence_total_score=Decimal("80"),
    )
    CaseAssessment.objects.create(
        case=case2,
        contract_basis=ContractBasisType.ORAL,
        principal_amount=Decimal("800000"),
        evidence_total_score=Decimal("60"),
    )

    # Collection records
    CollectionRecord.objects.create(
        case=case1,
        current_stage=CollectionStage.PHONE_COLLECTION,
        start_date=today - timedelta(days=50),
    )
    CollectionRecord.objects.create(
        case=case2,
        current_stage=CollectionStage.LITIGATION,
        start_date=today - timedelta(days=100),
    )

    return {
        "cases": [case1, case2, case3],
        "lawyers": [lawyer1, lawyer2],
        "today": today,
    }


# ── _safe_rate ──


def test_safe_rate_normal() -> None:
    assert _safe_rate(Decimal("50"), Decimal("200")) == Decimal("25.00")


def test_safe_rate_zero_denominator() -> None:
    assert _safe_rate(Decimal("100"), Decimal("0")) == Decimal("0.00")


# ── _lawyer_display_name ──


def test_lawyer_display_name_none() -> None:
    result = _lawyer_display_name(None)
    assert result  # should return fallback


# ── get_summary ──


@pytest.mark.django_db
def test_get_summary(svc, setup_data):
    today = setup_data["today"]
    # Use a wide range that covers all cases
    start = today - timedelta(days=365 * 3)
    end = today + timedelta(days=1)

    result = svc.get_summary(start, end)

    assert result.total_recovery == Decimal("450000")
    assert result.query_start == start
    assert result.query_end == end
    assert result.recovered_case_count >= 2
    assert result.avg_recovery_cycle > 0


# ── get_trend ──


@pytest.mark.django_db
def test_get_trend_month(svc, setup_data):
    today = setup_data["today"]
    start = today - timedelta(days=365 * 3)
    end = today + timedelta(days=1)

    result = svc.get_trend(start, end, "month")

    assert len(result) > 0
    total = sum(r.amount for r in result)
    assert total == Decimal("450000")


# ── get_breakdown ──


@pytest.mark.django_db
def test_get_breakdown_by_case_type(svc, setup_data):
    today = setup_data["today"]
    start = today - timedelta(days=365 * 3)
    end = today + timedelta(days=1)

    result = svc.get_breakdown(start, end, "case_type")

    assert len(result) >= 2
    total_cases = sum(r.case_count for r in result)
    assert total_cases == 3


@pytest.mark.django_db
def test_get_breakdown_by_amount_range(svc, setup_data):
    today = setup_data["today"]
    start = today - timedelta(days=365 * 3)
    end = today + timedelta(days=1)

    result = svc.get_breakdown(start, end, "amount_range")

    assert len(result) > 0
    total_cases = sum(r.case_count for r in result)
    assert total_cases == 3


@pytest.mark.django_db
def test_get_breakdown_by_lawyer(svc, setup_data):
    today = setup_data["today"]
    start = today - timedelta(days=365 * 3)
    end = today + timedelta(days=1)

    result = svc.get_breakdown(start, end, "lawyer")

    assert len(result) >= 2
    total_cases = sum(r.case_count for r in result)
    assert total_cases == 3


# ── get_factors ──


@pytest.mark.django_db
def test_get_factors(svc, setup_data):
    today = setup_data["today"]
    start = today - timedelta(days=365 * 3)
    end = today + timedelta(days=1)

    result = svc.get_factors(start, end)

    assert "debt_age" in result
    assert "contract_basis" in result
    assert "preservation" in result
    assert "amount_range" in result

    # debt_age should have items
    assert len(result["debt_age"]) > 0
    # contract_basis should have items for written and oral
    assert len(result["contract_basis"]) >= 2
    # preservation should have items for has/has not
    assert len(result["preservation"]) >= 1
    # amount_range should have items
    assert len(result["amount_range"]) > 0


# ── get_lawyer_performance ──


@pytest.mark.django_db
def test_get_lawyer_performance(svc, setup_data):
    today = setup_data["today"]
    start = today - timedelta(days=365 * 3)
    end = today + timedelta(days=1)

    result = svc.get_lawyer_performance(start, end, "total_recovery")

    assert len(result) >= 2
    # Should be sorted by total_recovery descending
    for i in range(len(result) - 1):
        assert result[i].total_recovery >= result[i + 1].total_recovery

    # Check that each item has expected fields
    for item in result:
        assert item.lawyer_id > 0
        assert item.lawyer_name
        assert item.case_count > 0


# ── get_case_stats ──


@pytest.mark.django_db
def test_get_case_stats(svc, setup_data):
    today = setup_data["today"]
    start = today - timedelta(days=365 * 3)
    end = today + timedelta(days=1)

    result = svc.get_case_stats(start, end)

    assert result.total_cases == 3
    assert result.active_cases >= 1
    assert result.closed_cases >= 1
    assert len(result.stage_distribution) > 0
    assert len(result.amount_distribution) > 0
    assert len(result.stage_conversion_rates) > 0
