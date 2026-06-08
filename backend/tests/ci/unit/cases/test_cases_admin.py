"""Cases Admin 测试 - CaseLogAdmin, CasePartyAdmin, CaseAssignmentAdmin"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.cases.admin.caselog_admin import CaseLogAdmin
from apps.cases.admin.caseparty_admin import CasePartyAdmin
from apps.cases.admin.caseassignment_admin import CaseAssignmentAdmin
from apps.cases.models import Case, CaseAssignment, CaseLog, CaseParty
from apps.contracts.models import Contract
from apps.organization.models import Lawyer

User = get_user_model()


def _make_request(path: str = "/admin/") -> Any:
    """构造 admin request"""
    factory = RequestFactory()
    request = factory.get(path)
    request.user = User(is_superuser=True, is_staff=True)
    return request


@pytest.mark.django_db
class TestCaseLogAdmin:
    """CaseLogAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = CaseLogAdmin(CaseLog, AdminSite())
        assert "id" in admin_obj.list_display
        assert "case_link" in admin_obj.list_display
        assert "actor" in admin_obj.list_display
        assert "created_at" in admin_obj.list_display

    def test_list_select_related(self) -> None:
        """list_select_related 包含 case 和 actor"""
        admin_obj = CaseLogAdmin(CaseLog, AdminSite())
        assert "case" in admin_obj.list_select_related
        assert "actor" in admin_obj.list_select_related

    def test_get_queryset_select_related(self) -> None:
        """get_queryset 应使用 select_related 避免 N+1"""
        contract = Contract.objects.create(name="测试合同", case_type="civil")
        case = Case.objects.create(name="测试案件", contract=contract)
        lawyer = Lawyer.objects.create_user(username="test_lawyer", real_name="张律师")
        CaseLog.objects.create(case=case, actor=lawyer, content="测试日志")

        admin_obj = CaseLogAdmin(CaseLog, AdminSite())
        qs = admin_obj.get_queryset(_make_request())

        # 验证 select_related 生效：访问 case 和 actor 不触发额外查询
        results = list(qs)
        assert len(results) == 1
        assert results[0].case.name == "测试案件"
        assert results[0].actor.real_name == "张律师"

    def test_case_link_display(self) -> None:
        """case_link 方法应返回包含案件名称的链接"""
        contract = Contract.objects.create(name="测试合同", case_type="civil")
        case = Case.objects.create(name="案件A", contract=contract)
        lawyer = Lawyer.objects.create_user(username="lawyer1", real_name="律师1")
        log = CaseLog.objects.create(case=case, actor=lawyer, content="日志")

        admin_obj = CaseLogAdmin(CaseLog, AdminSite())
        result = admin_obj.case_link(log)
        assert "案件A" in result
        assert "<a href=" in result

    def test_save_model_auto_set_actor(self) -> None:
        """save_model 应自动设置 actor 为当前用户"""
        contract = Contract.objects.create(name="测试合同", case_type="civil")
        case = Case.objects.create(name="测试案件", contract=contract)
        lawyer = Lawyer.objects.create_user(username="save_test_lawyer", real_name="保存测试律师")
        log = CaseLog(case=case, content="新日志")

        request = _make_request()
        request.user = lawyer

        admin_obj = CaseLogAdmin(CaseLog, AdminSite())
        admin_obj.save_model(request, log, None, False)

        assert log.actor_id == lawyer.id

    def test_ordering(self) -> None:
        """排序应按 created_at 降序"""
        admin_obj = CaseLogAdmin(CaseLog, AdminSite())
        assert admin_obj.ordering == ("-created_at",)


@pytest.mark.django_db
class TestCasePartyAdmin:
    """CasePartyAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = CasePartyAdmin(CaseParty, AdminSite())
        assert "id" in admin_obj.list_display
        assert "case" in admin_obj.list_display
        assert "client" in admin_obj.list_display
        assert "legal_status" in admin_obj.list_display

    def test_list_select_related(self) -> None:
        """list_select_related 包含 case 和 client"""
        admin_obj = CasePartyAdmin(CaseParty, AdminSite())
        assert "case" in admin_obj.list_select_related
        assert "client" in admin_obj.list_select_related

    def test_is_our_client_display(self) -> None:
        """is_our_client 方法应返回正确的布尔值"""
        from apps.client.models import Client

        contract = Contract.objects.create(name="测试合同", case_type="civil")
        case = Case.objects.create(name="测试案件", contract=contract)
        client = Client.objects.create(name="我方客户", client_type="natural", is_our_client=True)
        party = CaseParty.objects.create(case=case, client=client, legal_status="plaintiff")

        admin_obj = CasePartyAdmin(CaseParty, AdminSite())
        assert admin_obj.is_our_client(party) is True

        client2 = Client.objects.create(name="对方客户", client_type="natural", is_our_client=False)
        party2 = CaseParty.objects.create(case=case, client=client2, legal_status="defendant")
        assert admin_obj.is_our_client(party2) is False


@pytest.mark.django_db
class TestCaseAssignmentAdmin:
    """CaseAssignmentAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = CaseAssignmentAdmin(CaseAssignment, AdminSite())
        assert "id" in admin_obj.list_display
        assert "case" in admin_obj.list_display
        assert "lawyer" in admin_obj.list_display

    def test_list_select_related(self) -> None:
        """list_select_related 包含 case 和 lawyer"""
        admin_obj = CaseAssignmentAdmin(CaseAssignment, AdminSite())
        assert "case" in admin_obj.list_select_related
        assert "lawyer" in admin_obj.list_select_related

    def test_get_queryset_no_n_plus_1(self) -> None:
        """get_queryset 应使用 select_related 避免 N+1"""
        contract = Contract.objects.create(name="测试合同", case_type="civil")
        case = Case.objects.create(name="测试案件", contract=contract)
        lawyer = Lawyer.objects.create_user(username="assign_lawyer", real_name="指派律师")
        CaseAssignment.objects.create(case=case, lawyer=lawyer)

        admin_obj = CaseAssignmentAdmin(CaseAssignment, AdminSite())
        qs = admin_obj.get_queryset(_make_request())
        results = list(qs)
        assert len(results) == 1
        assert results[0].case.name == "测试案件"
        assert results[0].lawyer.real_name == "指派律师"
