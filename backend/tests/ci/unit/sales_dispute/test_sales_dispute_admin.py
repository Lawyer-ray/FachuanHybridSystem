"""Sales Dispute Admin 测试 - CaseAssessmentAdmin, CollectionRecordAdmin, PaymentRecordAdmin, LPRRateAdmin"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.sales_dispute.admin.case_assessment_admin import CaseAssessmentAdmin
from apps.sales_dispute.admin.collection_record_admin import CollectionRecordAdmin
from apps.sales_dispute.admin.payment_record_admin import PaymentRecordAdmin
from apps.sales_dispute.admin.lpr_rate_admin import LPRRateAdmin
from apps.sales_dispute.models import CaseAssessment, CollectionRecord, PaymentRecord, LPRRate
from apps.cases.models import Case
from apps.contracts.models import Contract

User = get_user_model()


def _make_request(path: str = "/admin/") -> Any:
    factory = RequestFactory()
    request = factory.get(path)
    request.user = User(is_superuser=True, is_staff=True)
    return request


def _create_case() -> Case:
    contract = Contract.objects.create(name="销售纠纷测试合同", case_type="civil")
    return Case.objects.create(name="销售纠纷测试案件", contract=contract)


@pytest.mark.django_db
class TestCaseAssessmentAdmin:
    """CaseAssessmentAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = CaseAssessmentAdmin(CaseAssessment, AdminSite())
        assert "case" in admin_obj.list_display
        assert "principal_amount" in admin_obj.list_display
        assert "evidence_total_score" in admin_obj.list_display
        assert "limitation_status" in admin_obj.list_display
        assert "assessment_grade" in admin_obj.list_display

    def test_list_filter(self) -> None:
        """list_filter 包含 assessment_grade"""
        admin_obj = CaseAssessmentAdmin(CaseAssessment, AdminSite())
        assert "assessment_grade" in admin_obj.list_filter

    def test_search_fields(self) -> None:
        """search_fields 包含 case__name"""
        admin_obj = CaseAssessmentAdmin(CaseAssessment, AdminSite())
        assert "case__name" in admin_obj.search_fields


@pytest.mark.django_db
class TestCollectionRecordAdmin:
    """CollectionRecordAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = CollectionRecordAdmin(CollectionRecord, AdminSite())
        assert "case" in admin_obj.list_display
        assert "current_stage" in admin_obj.list_display
        assert "start_date" in admin_obj.list_display

    def test_list_filter(self) -> None:
        """list_filter 包含 current_stage"""
        admin_obj = CollectionRecordAdmin(CollectionRecord, AdminSite())
        assert "current_stage" in admin_obj.list_filter


@pytest.mark.django_db
class TestPaymentRecordAdmin:
    """PaymentRecordAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = PaymentRecordAdmin(PaymentRecord, AdminSite())
        assert "case" in admin_obj.list_display
        assert "payment_date" in admin_obj.list_display
        assert "payment_amount" in admin_obj.list_display
        assert "remaining_principal" in admin_obj.list_display

    def test_list_filter(self) -> None:
        """list_filter 包含 payment_date"""
        admin_obj = PaymentRecordAdmin(PaymentRecord, AdminSite())
        assert "payment_date" in admin_obj.list_filter


@pytest.mark.django_db
class TestSalesDisputeLPRRateAdmin:
    """Sales Dispute LPRRateAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = LPRRateAdmin(LPRRate, AdminSite())
        assert "effective_date" in admin_obj.list_display
        assert "rate_1y" in admin_obj.list_display
        assert "rate_5y" in admin_obj.list_display

    def test_ordering(self) -> None:
        """排序应按 effective_date 降序"""
        admin_obj = LPRRateAdmin(LPRRate, AdminSite())
        assert admin_obj.ordering == ("-effective_date",)
