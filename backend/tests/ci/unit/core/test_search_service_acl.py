"""安全审计第4轮：全局搜索 ACL 回归测试。

覆盖：
1. search_cases / search_contracts 按 CaseAccessPolicy / ContractAccessPolicy 过滤
2. search_clients 按 client.view_client 功能级权限过滤 + 手机号打码
3. search_court_sms 按案件 ACL 过滤，公共短信全员可见
4. search_contacts 非管理员返回空
5. resolve_request_org_access：JWT 场景 org_access 缺失时补算
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from django.test import RequestFactory
from django.utils import timezone

from apps.automation.models import CourtSMS, CourtSMSStatus
from apps.cases.models import CaseAssignment
from apps.client.models import Client
from apps.contacts.models import CaseContact
from apps.contracts.models import ContractAssignment
from apps.core.services.search_service import (
    _mask_phone,
    search_cases,
    search_clients,
    search_contacts,
    search_contracts,
    search_court_sms,
)
from apps.testing.factories import CaseFactory, ContractFactory, LawyerFactory

_factory = RequestFactory()


def _make_case_with_assignment(lawyer: Any, name: str):
    case = CaseFactory(name=name)
    CaseAssignment.objects.create(case=case, lawyer=lawyer)
    return case


def _make_contract_with_assignment(lawyer: Any, name: str):
    contract = ContractFactory(name=name)
    ContractAssignment.objects.create(contract=contract, lawyer=lawyer)
    return contract


def _make_sms(case: Any = None, content: str = "【法院】短信内容") -> CourtSMS:
    return CourtSMS.objects.create(
        content=content,
        received_at=timezone.now(),
        status=CourtSMSStatus.PENDING,
        document_file_paths=[],
        case=case,
    )


class TestCaseSearchAcl:
    @pytest.mark.django_db
    def test_lawyer_cannot_search_unassigned_case(self) -> None:
        lawyer_b = LawyerFactory()
        _make_case_with_assignment(lawyer_b, "机密并购案件")
        lawyer_a = LawyerFactory()

        results = search_cases("机密并购", 10, user=lawyer_a, org_access=None)
        assert results == []

    @pytest.mark.django_db
    def test_assigned_lawyer_and_admin_can_search(self) -> None:
        lawyer_b = LawyerFactory()
        case = _make_case_with_assignment(lawyer_b, "机密并购案件")
        admin = LawyerFactory(is_admin=True)

        results_b = search_cases("机密并购", 10, user=lawyer_b, org_access=None)
        results_admin = search_cases("机密并购", 10, user=admin, org_access=None)
        assert [r.id for r in results_b] == [case.id]
        assert case.id in [r.id for r in results_admin]

    @pytest.mark.django_db
    def test_team_member_via_org_access_can_search(self) -> None:
        """org_access 的团队口径：同团队成员（allowed_lawyers）可见。"""
        from apps.organization.models import LawFirm, Team, TeamType

        firm = LawFirm.objects.create(name="firm-acl")
        team = Team.objects.create(name="team-acl", team_type=TeamType.LAWYER, law_firm=firm)
        lawyer_a, lawyer_b = LawyerFactory(), LawyerFactory()
        lawyer_a.lawyer_teams.add(team)
        lawyer_b.lawyer_teams.add(team)
        case = _make_case_with_assignment(lawyer_b, "团队共享案件")

        org_access = {"lawyers": {lawyer_a.id, lawyer_b.id}, "team_ids": {team.id}, "extra_cases": set()}
        results = search_cases("团队共享", 10, user=lawyer_a, org_access=org_access)
        assert [r.id for r in results] == [case.id]


class TestContractSearchAcl:
    @pytest.mark.django_db
    def test_lawyer_cannot_search_unassigned_contract(self) -> None:
        lawyer_b = LawyerFactory()
        _make_contract_with_assignment(lawyer_b, "独家顾问合同")
        lawyer_a = LawyerFactory()

        assert search_contracts("独家顾问", 10, user=lawyer_a, org_access=None) == []

    @pytest.mark.django_db
    def test_assigned_lawyer_and_admin_can_search(self) -> None:
        lawyer_b = LawyerFactory()
        contract = _make_contract_with_assignment(lawyer_b, "独家顾问合同")
        admin = LawyerFactory(is_admin=True)

        results_b = search_contracts("独家顾问", 10, user=lawyer_b, org_access=None)
        results_admin = search_contracts("独家顾问", 10, user=admin, org_access=None)
        assert [r.id for r in results_b] == [contract.id]
        assert contract.id in [r.id for r in results_admin]


class TestClientSearchAcl:
    @pytest.mark.django_db
    def test_no_perm_user_gets_empty(self) -> None:
        Client.objects.create(name="张三丰", phone="13812341234")
        assert search_clients("张三丰", 10, user=LawyerFactory()) == []

    @pytest.mark.django_db
    def test_admin_gets_masked_phone(self) -> None:
        Client.objects.create(name="张三丰", phone="13812341234")
        admin = LawyerFactory(is_admin=True)

        results = search_clients("张三丰", 10, user=admin)
        assert len(results) == 1
        assert results[0].subtitle == "138****1234"
        assert "13812341234" not in results[0].subtitle

    @pytest.mark.django_db
    def test_search_by_full_phone_still_finds_but_masks(self) -> None:
        Client.objects.create(name="李四", phone="13900001111")
        admin = LawyerFactory(is_admin=True)

        results = search_clients("13900001111", 10, user=admin)
        assert len(results) == 1
        assert results[0].subtitle == "139****1111"


class TestCourtSmsSearchAcl:
    @pytest.mark.django_db
    def test_lawyer_cannot_search_others_case_sms(self) -> None:
        lawyer_b = LawyerFactory()
        case = _make_case_with_assignment(lawyer_b, "他人案件")
        _make_sms(case=case, content="开庭通知内容")
        lawyer_a = LawyerFactory()

        assert search_court_sms("开庭通知", 10, user=lawyer_a, org_access=None) == []

    @pytest.mark.django_db
    def test_public_sms_visible_and_bound_sms_for_assigned(self) -> None:
        lawyer_b = LawyerFactory()
        case = _make_case_with_assignment(lawyer_b, "自己案件")
        bound = _make_sms(case=case, content="缴费通知内容")
        public = _make_sms(case=None, content="缴费通知公共")
        admin = LawyerFactory(is_admin=True)

        results_b = search_court_sms("缴费通知", 10, user=lawyer_b, org_access=None)
        results_admin = search_court_sms("缴费通知", 10, user=admin, org_access=None)
        assert {r.id for r in results_b} == {bound.id, public.id}
        assert {bound.id, public.id} <= {r.id for r in results_admin}

    @pytest.mark.django_db
    def test_anonymous_sees_public_only(self) -> None:
        lawyer_b = LawyerFactory()
        case = _make_case_with_assignment(lawyer_b, "匿名不可见案件")
        _make_sms(case=case, content="鉴定通知内容")
        public = _make_sms(case=None, content="鉴定通知公共")

        results = search_court_sms("鉴定通知", 10, user=None, org_access=None)
        assert [r.id for r in results] == [public.id]


class TestContactsSearchAdminOnly:
    @pytest.mark.django_db
    def test_normal_user_gets_empty(self) -> None:
        assert search_contacts("任何关键词", 10, user=LawyerFactory()) == []

    @pytest.mark.django_db
    def test_admin_sees_contacts(self) -> None:
        case = CaseFactory()
        CaseContact.objects.create(case=case, name="王法官")
        admin = LawyerFactory(is_admin=True)

        results = search_contacts("王法官", 10, user=admin)
        assert len(results) == 1
        assert results[0].title == "王法官"


class TestMaskPhone:
    def test_mobile_masked(self) -> None:
        assert _mask_phone("13812341234") == "138****1234"

    def test_short_or_non_digit_masked_fully(self) -> None:
        assert _mask_phone("123456") == "******"
        assert _mask_phone("0755-1234567") == "****-*******"

    def test_empty(self) -> None:
        assert _mask_phone("") == ""
        assert _mask_phone(None) == ""


class TestResolveRequestOrgAccess:
    @pytest.mark.django_db
    def test_missing_org_access_is_computed_and_backfilled(self) -> None:
        """JWT 时序坑：request.org_access 为 None 时补算并回填（不退化为仅本人）。"""
        from apps.core.dependencies.business import resolve_request_org_access
        from apps.organization.models import LawFirm, Team, TeamType

        firm = LawFirm.objects.create(name="firm-jwt")
        team = Team.objects.create(name="team-jwt", team_type=TeamType.LAWYER, law_firm=firm)
        lawyer_a, lawyer_b = LawyerFactory(), LawyerFactory()
        lawyer_a.lawyer_teams.add(team)
        lawyer_b.lawyer_teams.add(team)

        request = _factory.get("/api/v1/search")
        request.user = lawyer_a  # 已认证但中间件未设置 org_access（模拟纯 JWT 时序）
        org_access = resolve_request_org_access(request)
        assert org_access is not None
        assert lawyer_b.id in org_access["lawyers"]
        assert getattr(request, "org_access", None) is org_access

    @pytest.mark.django_db
    def test_existing_org_access_untouched(self) -> None:
        from apps.core.dependencies.business import resolve_request_org_access

        user = LawyerFactory()
        request = _factory.get("/api/v1/search")
        request.user = user
        cached = {"lawyers": {user.id}, "team_ids": set(), "extra_cases": set()}
        request.org_access = cached
        assert resolve_request_org_access(request) is cached

    def test_anonymous_returns_none(self) -> None:
        from django.contrib.auth.models import AnonymousUser

        from apps.core.dependencies.business import resolve_request_org_access

        request = _factory.get("/api/v1/search")
        request.user = AnonymousUser()
        with patch("apps.organization.middleware.get_or_compute_org_access") as mock_compute:
            assert resolve_request_org_access(request) is None
        mock_compute.assert_not_called()


class TestGlobalSearchEndpoint:
    # 视图内搜索走 thread_sensitive=False 工作线程（独立 DB 连接），
    # 须用事务库让数据跨连接可见
    @pytest.mark.django_db(transaction=True)
    def test_http_admin_search_masks_phone(self) -> None:
        """HTTP 层冒烟：管理员经会话认证搜索，手机号出参已打码。"""
        from django.test import Client as TestClient

        admin = LawyerFactory(is_admin=True, is_staff=True)
        Client.objects.create(name="赵五", phone="13711112222")
        case = CaseFactory(name="HTTP冒烟案件")

        client = TestClient()
        client.force_login(admin)
        resp = client.get("/api/v1/search", {"q": "HTTP冒烟"})
        assert resp.status_code == 200
        payload = resp.json()
        assert any(item["id"] == case.id for item in payload["cases"])
        # 未命中关键词的客户不出现在结果里
        assert payload["clients"] == []

        resp_client = client.get("/api/v1/search", {"q": "赵五"})
        assert resp_client.status_code == 200
        assert [c["subtitle"] for c in resp_client.json()["clients"]] == ["137****2222"]

    @pytest.mark.django_db(transaction=True)
    def test_http_lawyer_cannot_see_others_case(self) -> None:
        from django.test import Client as TestClient

        lawyer_b = LawyerFactory()
        case = _make_case_with_assignment(lawyer_b, "他人专属案件HTTP")
        lawyer_a = LawyerFactory()

        client = TestClient()
        client.force_login(lawyer_a)
        resp = client.get("/api/v1/search", {"q": "他人专属"})
        assert resp.status_code == 200
        assert resp.json()["cases"] == []

        client.force_login(lawyer_b)
        resp_b = client.get("/api/v1/search", {"q": "他人专属"})
        assert [item["id"] for item in resp_b.json()["cases"]] == [case.id]
