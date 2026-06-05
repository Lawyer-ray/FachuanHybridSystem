"""Admin 行级权限控制测试.

覆盖场景：
1. is_admin 用户看到全部记录
2. 普通律师只看到团队分配的记录
3. 无分配的律师看到空列表
4. CaseAccessGrant 提供额外访问
5. 合同的案件路径过滤
6. perm_open_access 全局放行
"""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client, RequestFactory
from django.urls import reverse

from apps.cases.models import Case, CaseAssignment, CaseAccessGrant
from apps.cases.services.case.case_access_policy import CaseAccessPolicy
from apps.contracts.models import Contract, ContractAssignment
from apps.contracts.services.contract.domain.access_policy import ContractAccessPolicy
from apps.core.security.admin_access import apply_admin_access_filter
from apps.organization.models import Lawyer, Team, TeamType
from apps.testing.factories import CaseFactory, ContractFactory, LawyerFactory


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_team(name: str, law_firm: Any = None) -> Team:
    if law_firm is None:
        from apps.organization.models import LawFirm

        law_firm = LawFirm.objects.create(name=f"firm-{name}")
    return Team.objects.create(name=name, team_type=TeamType.LAWYER, law_firm=law_firm)


def _make_request(user: Lawyer, org_access: dict | None = None, perm_open_access: bool = False):
    """构造带 org_access 的模拟 request."""
    factory = RequestFactory()
    request = factory.get("/admin/")
    request.user = user
    request.org_access = org_access
    request.perm_open_access = perm_open_access
    return request


def _make_org_access(user: Lawyer) -> dict:
    """手动构造 org_access dict（模拟 OrgAccessComputationService）."""
    team_ids = set(user.lawyer_teams.values_list("id", flat=True))
    lawyers = (
        set(Lawyer.objects.filter(lawyer_teams__id__in=team_ids).values_list("id", flat=True).distinct())
        if team_ids
        else set()
    )
    if not lawyers:
        lawyers.add(user.id)
    extra_cases = set(CaseAccessGrant.objects.filter(grantee=user).values_list("case_id", flat=True))
    return {"lawyers": lawyers, "team_ids": team_ids, "extra_cases": extra_cases}


def _count_cases(user: Lawyer, org_access: dict | None = None) -> int:
    """通过 apply_admin_access_filter 统计用户可见案件数."""
    from django.db.models import QuerySet

    qs: QuerySet[Case] = Case.objects.all()
    request = _make_request(user, org_access=org_access)
    qs = apply_admin_access_filter(request, qs, CaseAccessPolicy())
    return qs.count()


def _count_contracts(user: Lawyer, org_access: dict | None = None) -> int:
    """通过 apply_admin_access_filter 统计用户可见合同数."""
    from django.db.models import QuerySet

    qs: QuerySet[Contract] = Contract.objects.all()
    request = _make_request(user, org_access=org_access)
    qs = apply_admin_access_filter(request, qs, ContractAccessPolicy())
    return qs.count()


# ── 场景 1: is_admin 用户看到全部 ──────────────────────────────────────────────


@pytest.mark.django_db
class TestAdminUserSeesAll:
    """is_admin=True 的用户看到所有案件和合同."""

    def test_admin_sees_all_cases(self) -> None:
        admin = LawyerFactory(is_admin=True)
        team = _make_team("t1")
        other_lawyer = LawyerFactory()
        other_lawyer.lawyer_teams.add(team)

        case1 = CaseFactory()
        case2 = CaseFactory()
        CaseAssignment.objects.create(case=case1, lawyer=other_lawyer)
        CaseAssignment.objects.create(case=case2, lawyer=other_lawyer)

        org_access = _make_org_access(admin)
        assert _count_cases(admin, org_access) == 2

    def test_admin_sees_all_contracts(self) -> None:
        admin = LawyerFactory(is_admin=True)
        other_lawyer = LawyerFactory()

        c1 = ContractFactory()
        c2 = ContractFactory()
        ContractAssignment.objects.create(contract=c1, lawyer=other_lawyer)
        ContractAssignment.objects.create(contract=c2, lawyer=other_lawyer)

        org_access = _make_org_access(admin)
        assert _count_contracts(admin, org_access) == 2


# ── 场景 2: 普通律师只看团队相关记录 ──────────────────────────────────────────


@pytest.mark.django_db
class TestRegularLawyerSeesTeamRecords:
    """普通律师只能看到自己团队分配的案件和合同."""

    def setup_method(self) -> None:
        self.firm = _make_team("t1").law_firm
        self.team = _make_team("team_a", self.firm)
        self.lawyer_a = LawyerFactory(law_firm=self.firm)
        self.lawyer_a.lawyer_teams.add(self.team)
        self.lawyer_b = LawyerFactory(law_firm=self.firm)
        self.lawyer_b.lawyer_teams.add(self.team)

        # 其他团队的律师
        self.other_team = _make_team("team_b", self.firm)
        self.other_lawyer = LawyerFactory(law_firm=self.firm)
        self.other_lawyer.lawyer_teams.add(self.other_team)

    def test_lawyer_a_sees_team_cases(self) -> None:
        """lawyer_a 看到 team_a 中任一律师被分配的案件."""
        case1 = CaseFactory()
        case2 = CaseFactory()
        case3 = CaseFactory()  # 分配给其他团队
        CaseAssignment.objects.create(case=case1, lawyer=self.lawyer_a)
        CaseAssignment.objects.create(case=case2, lawyer=self.lawyer_b)
        CaseAssignment.objects.create(case=case3, lawyer=self.other_lawyer)

        org_access = _make_org_access(self.lawyer_a)
        assert _count_cases(self.lawyer_a, org_access) == 2

    def test_lawyer_a_sees_team_contracts(self) -> None:
        """lawyer_a 看到 team_a 中任一律师被分配的合同."""
        c1 = ContractFactory()
        c2 = ContractFactory()
        c3 = ContractFactory()
        ContractAssignment.objects.create(contract=c1, lawyer=self.lawyer_a)
        ContractAssignment.objects.create(contract=c2, lawyer=self.lawyer_b)
        ContractAssignment.objects.create(contract=c3, lawyer=self.other_lawyer)

        org_access = _make_org_access(self.lawyer_a)
        assert _count_contracts(self.lawyer_a, org_access) == 2

    def test_lawyer_b_also_sees_lawyer_a_cases(self) -> None:
        """同团队的 lawyer_b 也能看到 lawyer_a 的案件."""
        case1 = CaseFactory()
        CaseAssignment.objects.create(case=case1, lawyer=self.lawyer_a)

        org_access = _make_org_access(self.lawyer_b)
        assert _count_cases(self.lawyer_b, org_access) == 1


# ── 场景 3: 无分配的律师看到空列表 ──────────────────────────────────────────


@pytest.mark.django_db
class TestNoAssignmentSeesNothing:
    """没有任何团队或分配的律师看到空列表."""

    def test_lone_lawyer_sees_own_cases_only(self) -> None:
        lawyer = LawyerFactory()
        case1 = CaseFactory()
        case2 = CaseFactory()
        CaseAssignment.objects.create(case=case1, lawyer=lawyer)
        CaseAssignment.objects.create(case=case2, lawyer=LawyerFactory())

        org_access = _make_org_access(lawyer)
        assert _count_cases(lawyer, org_access) == 1

    def test_lone_lawyer_with_no_assignments(self) -> None:
        lawyer = LawyerFactory()
        CaseFactory()
        CaseFactory()

        org_access = _make_org_access(lawyer)
        assert _count_cases(lawyer, org_access) == 0


# ── 场景 4: CaseAccessGrant 提供额外访问 ──────────────────────────────────────


@pytest.mark.django_db
class TestCaseAccessGrant:
    """CaseAccessGrant 显式授权的案件叠加到可见列表."""

    def test_grant_provides_access(self) -> None:
        lawyer = LawyerFactory()
        case1 = CaseFactory()
        case2 = CaseFactory()  # 无分配但有授权
        CaseAssignment.objects.create(case=case1, lawyer=lawyer)
        CaseAccessGrant.objects.create(case=case2, grantee=lawyer)

        org_access = _make_org_access(lawyer)
        assert _count_cases(lawyer, org_access) == 2

    def test_grant_for_other_lawyer_not_visible(self) -> None:
        lawyer = LawyerFactory()
        other = LawyerFactory()
        case1 = CaseFactory()
        CaseAccessGrant.objects.create(case=case1, grantee=other)

        org_access = _make_org_access(lawyer)
        assert _count_cases(lawyer, org_access) == 0


# ── 场景 5: 合同的案件路径过滤 ──────────────────────────────────────────────


@pytest.mark.django_db
class TestContractCasePath:
    """合同过滤包含案件路径：用户被分配了关联案件也能看到该合同."""

    def test_case_assignment_grants_contract_access(self) -> None:
        lawyer = LawyerFactory()
        contract = ContractFactory()
        case = CaseFactory(contract=contract)
        CaseAssignment.objects.create(case=case, lawyer=lawyer)
        # 合同本身未分配给该律师

        org_access = _make_org_access(lawyer)
        assert _count_contracts(lawyer, org_access) == 1

    def test_case_assignment_does_not_grant_other_contracts(self) -> None:
        lawyer = LawyerFactory()
        contract1 = ContractFactory()
        contract2 = ContractFactory()
        case = CaseFactory(contract=contract1)
        CaseAssignment.objects.create(case=case, lawyer=lawyer)
        # contract2 无关联

        org_access = _make_org_access(lawyer)
        assert _count_contracts(lawyer, org_access) == 1


# ── 场景 6: perm_open_access 全局放行 ────────────────────────────────────────


@pytest.mark.django_db
class TestPermOpenAccess:
    """perm_open_access=True 跳过所有过滤."""

    def test_open_access_sees_all_cases(self) -> None:
        lawyer = LawyerFactory()
        CaseFactory()
        CaseFactory()

        request = _make_request(lawyer, perm_open_access=True)
        qs = apply_admin_access_filter(request, Case.objects.all(), CaseAccessPolicy())
        assert qs.count() == 2

    def test_open_access_sees_all_contracts(self) -> None:
        lawyer = LawyerFactory()
        ContractFactory()
        ContractFactory()

        request = _make_request(lawyer, perm_open_access=True)
        qs = apply_admin_access_filter(request, Contract.objects.all(), ContractAccessPolicy())
        assert qs.count() == 2


# ── HTTP 集成测试：Admin 列表页 ──────────────────────────────────────────────


@pytest.mark.django_db
class TestAdminChangelistAccess:
    """通过 HTTP 请求测试 admin changelist 页面的行级过滤."""

    @staticmethod
    def _login(user: Lawyer) -> Client:
        client = Client()
        client.force_login(user)
        return client

    @staticmethod
    def _make_staff(user: Lawyer) -> None:
        """赋予 staff 权限和模型权限，使其能访问 admin."""
        from django.contrib.auth.models import Permission

        user.is_staff = True
        user.save(update_fields=["is_staff"])
        perms = Permission.objects.filter(
            content_type__app_label__in=["cases", "contracts"],
            codename__startswith="view_",
        )
        user.user_permissions.add(*perms)

    def test_admin_changelist_sees_all(self) -> None:
        admin = LawyerFactory(is_admin=True, is_staff=True, is_superuser=True)
        CaseFactory()
        CaseFactory()
        client = self._login(admin)

        response = client.get(
            reverse("admin:cases_case_changelist"),
            {"status__exact": "active"},
            HTTP_HOST="localhost",
        )
        assert response.status_code == 200

    def test_regular_lawyer_changelist_filtered(self) -> None:
        """普通律师能正常访问 changelist 页面（不报 403）."""
        lawyer = LawyerFactory()
        self._make_staff(lawyer)
        team = _make_team("t1")
        lawyer.lawyer_teams.add(team)

        case1 = CaseFactory()
        CaseAssignment.objects.create(case=case1, lawyer=lawyer)

        client = self._login(lawyer)
        response = client.get(
            reverse("admin:cases_case_changelist"),
            {"status__exact": "active"},
            HTTP_HOST="localhost",
        )
        assert response.status_code == 200

    def test_contract_changelist_filtered(self) -> None:
        """普通律师能正常访问合同 changelist 页面."""
        lawyer = LawyerFactory()
        self._make_staff(lawyer)
        team = _make_team("t2")
        lawyer.lawyer_teams.add(team)

        c1 = ContractFactory()
        ContractAssignment.objects.create(contract=c1, lawyer=lawyer)

        client = self._login(lawyer)
        response = client.get(
            reverse("admin:contracts_contract_changelist"),
            {"status__exact": "active"},
            HTTP_HOST="localhost",
            follow=True,
        )
        assert response.status_code == 200
