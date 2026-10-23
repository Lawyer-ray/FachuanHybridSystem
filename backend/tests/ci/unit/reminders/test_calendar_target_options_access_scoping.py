"""reminders admin「日历关联目标」权限过滤测试。

覆盖安全审计修复：``calendar_target_options_view`` 曾用裸 ``objects.all()``
返回全所合同/案件/案件日志，绕过 ``ContractAccessPolicy`` / ``CaseAccessPolicy``。
现统一复用 ``get_target_options(ctx=...)``，与 REST 入口口径一致。

验证四类语义（对应业务要求）：
1. A 团队律师可见本团队全部律师的案件/合同
2. A 团队律师**看不到** B 团队律师的案件/合同
3. B 团队把 A 律师加进某案件（CaseAssignment / CaseAccessGrant）后，A 可见该案件
4. 管理员可见本所全部（含其他团队）
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from apps.cases.models import CaseAssignment
from apps.contracts.models import ContractAssignment
from apps.organization.models import LawFirm, Lawyer, Team, TeamType
from apps.reminders.admin.reminder_admin import ReminderAdmin
from apps.testing.factories import CaseFactory, CaseLogFactory, ContractFactory, LawyerFactory


def _make_admin() -> ReminderAdmin:
    admin = ReminderAdmin.__new__(ReminderAdmin)
    admin.has_add_permission = MagicMock(return_value=True)  # type: ignore[method-assign]
    return admin


def _make_request(user: Lawyer, *, keyword: str = "") -> Any:
    """构造带 org_access 的请求，模拟 OrgAccessMiddleware 的挂载结果。"""
    from apps.organization.services.wiring import build_org_access_computation_service

    org_access = build_org_access_computation_service().compute(user)

    request = MagicMock()
    request.method = "GET"
    request.GET = {"q": keyword}
    request.user = user
    request.org_access = org_access
    request.perm_open_access = False
    return request


def _ids_by_group(response: Any) -> dict[str, set[int]]:
    payload = json.loads(response.content)
    out: dict[str, set[int]] = {"case": set(), "contract": set(), "case_log": set()}
    for group in payload["groups"]:
        for item in group["items"]:
            out[group["key"]].add(item["id"])
    return out


@pytest.mark.django_db
class TestCalendarTargetOptionsAccessScoping:
    def test_team_member_sees_teammate_targets_but_not_other_team(self) -> None:
        """语义 1+2：A 团队看得到本团队，看不到 B 团队。"""
        firm = LawFirm.objects.create(name=f"firm-{'t1'}")
        team_a = Team.objects.create(name="team-A", team_type=TeamType.LAWYER, law_firm=firm)
        team_b = Team.objects.create(name="team-B", team_type=TeamType.LAWYER, law_firm=firm)

        lawyer_a1 = LawyerFactory(law_firm=firm)
        lawyer_a2 = LawyerFactory(law_firm=firm)
        lawyer_b1 = LawyerFactory(law_firm=firm)
        lawyer_a1.lawyer_teams.add(team_a)
        lawyer_a2.lawyer_teams.add(team_a)
        lawyer_b1.lawyer_teams.add(team_b)

        case_a = CaseFactory()
        case_b = CaseFactory()
        CaseAssignment.objects.create(case=case_a, lawyer=lawyer_a2)
        CaseAssignment.objects.create(case=case_b, lawyer=lawyer_b1)
        contract_a = ContractFactory()
        contract_b = ContractFactory()
        ContractAssignment.objects.create(contract=contract_a, lawyer=lawyer_a2)
        ContractAssignment.objects.create(contract=contract_b, lawyer=lawyer_b1)

        ids = _ids_by_group(_make_admin().calendar_target_options_view(_make_request(lawyer_a1)))

        assert case_a.id in ids["case"], "A 团队应可见本团队律师的案件"
        assert contract_a.id in ids["contract"], "A 团队应可见本团队律师的合同"
        assert case_b.id not in ids["case"], "A 团队不应可见 B 团队的案件"
        assert contract_b.id not in ids["contract"], "A 团队不应可见 B 团队的合同"

    def test_cross_team_case_assignment_grants_visibility(self) -> None:
        """语义 3：B 团队把 A 律师加入案件后，A 可见该案件。"""
        firm = LawFirm.objects.create(name="firm-t2")
        team_a = Team.objects.create(name="team-A2", team_type=TeamType.LAWYER, law_firm=firm)
        team_b = Team.objects.create(name="team-B2", team_type=TeamType.LAWYER, law_firm=firm)

        lawyer_a = LawyerFactory(law_firm=firm)
        lawyer_b = LawyerFactory(law_firm=firm)
        lawyer_a.lawyer_teams.add(team_a)
        lawyer_b.lawyer_teams.add(team_b)

        case_b = CaseFactory()
        CaseAssignment.objects.create(case=case_b, lawyer=lawyer_b)
        log_b = CaseLogFactory(case=case_b)

        # 断言前：不可见
        ids_before = _ids_by_group(_make_admin().calendar_target_options_view(_make_request(lawyer_a)))
        assert case_b.id not in ids_before["case"]
        assert log_b.id not in ids_before["case_log"]

        # B 团队把 A 律师加进该案件
        CaseAssignment.objects.create(case=case_b, lawyer=lawyer_a)

        ids_after = _ids_by_group(_make_admin().calendar_target_options_view(_make_request(lawyer_a)))
        assert case_b.id in ids_after["case"], "被加入案件后应可见该案件"
        assert log_b.id in ids_after["case_log"], "案件可见后其日志也应可见"

    def test_admin_sees_all_firm_targets(self) -> None:
        """语义 4：管理员可见本所全部案件/合同（含其他团队）。"""
        firm = LawFirm.objects.create(name="firm-t3")
        team_b = Team.objects.create(name="team-B3", team_type=TeamType.LAWYER, law_firm=firm)

        admin_user = LawyerFactory(law_firm=firm, is_admin=True)
        lawyer_b = LawyerFactory(law_firm=firm)
        lawyer_b.lawyer_teams.add(team_b)

        case_b = CaseFactory()
        CaseAssignment.objects.create(case=case_b, lawyer=lawyer_b)

        ids = _ids_by_group(_make_admin().calendar_target_options_view(_make_request(admin_user)))
        assert case_b.id in ids["case"], "管理员应可见本所（含其他团队）的案件"

    def test_unauthenticated_request_is_forbidden(self) -> None:
        """防御：无 user 时不退化为全量，直接 403。"""
        request = MagicMock()
        request.method = "GET"
        request.GET = {"q": ""}
        request.user = None
        request.org_access = None
        request.perm_open_access = False

        response = _make_admin().calendar_target_options_view(request)
        assert response.status_code == 403
        assert json.loads(response.content) == {"items": [], "groups": []}

    def test_keyword_filter_still_applies(self) -> None:
        """关键字过滤在新链路下仍然生效。"""
        firm = LawFirm.objects.create(name="firm-t5")
        lawyer = LawyerFactory(law_firm=firm)
        case_hit = CaseFactory(name="关键词命中案件")
        case_miss = CaseFactory(name="其他案件")
        CaseAssignment.objects.create(case=case_hit, lawyer=lawyer)
        CaseAssignment.objects.create(case=case_miss, lawyer=lawyer)

        ids = _ids_by_group(_make_admin().calendar_target_options_view(_make_request(lawyer, keyword="关键词命中")))
        assert case_hit.id in ids["case"]
        assert case_miss.id not in ids["case"]
