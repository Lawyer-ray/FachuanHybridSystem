"""权限矩阵：跨所隔离、无律所律师、未知作用域 fail-closed、单管理员律所不卡死。

这组用例的立项目的不是覆盖率，而是**把越权写死**。``services/memory/scopes.py``
的 ``can_curate_scope`` 曾出现「``is_admin`` 即放行、不看团队归属、未知 scope 返回
True」三连，本文件逐条对着这三条写负向用例——技能是行为指令，一次跨所发布会让
外所的 AI 按别家的流程办事且当事人无从察觉。
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.agent.models import AgentSkill
from apps.agent.services.skills import permissions
from apps.organization.models import LawFirm, Lawyer, Team

TEST_PASSWORD = "x-test-12345678"  # pragma: allowlist secret


def _lawyer(username: str, firm: LawFirm | None, *, is_admin: bool = False) -> Lawyer:
    return Lawyer.objects.create_user(
        username=username, password=TEST_PASSWORD, law_firm=firm, is_admin=is_admin
    )


def _team(firm: LawFirm, name: str = "诉讼一组") -> Team:
    return Team.objects.create(law_firm=firm, name=name, team_type="lawyer")


def _row(scope: str, *, lawyer: Lawyer | None = None, team: Team | None = None, firm: LawFirm | None = None,
         status: str = AgentSkill.Status.ACTIVE) -> AgentSkill:
    return AgentSkill.objects.create(
        scope=scope,
        name=f"n-{scope}"[:40],
        title="标题",
        description="描述",
        body="正文",
        lawyer=lawyer,
        team=team,
        law_firm=firm,
        status=status,
        created_by=lawyer,
    )


@pytest.fixture
def firm(db: Any) -> LawFirm:
    return LawFirm.objects.create(name="本所")


@pytest.fixture
def other_firm(db: Any) -> LawFirm:
    return LawFirm.objects.create(name="外所")


@pytest.mark.django_db
class TestCrossFirm:
    def test_other_firm_admin_cannot_review(self, firm: LawFirm, other_firm: LawFirm) -> None:
        """**核心负向用例**：他所管理员即使 ``is_admin=True`` 也不能碰本所技能。"""
        outsider = _lawyer("outsider-admin", other_firm, is_admin=True)
        target = _row(AgentSkill.Scope.LAW_FIRM, firm=firm)
        assert permissions.can_review(outsider, target) is False
        assert permissions.can_edit(outsider, target) is False
        assert permissions.can_archive(outsider, target) is False
        assert permissions.can_view(outsider, target) is False

    def test_other_firm_admin_cannot_review_team(self, firm: LawFirm, other_firm: LawFirm) -> None:
        outsider = _lawyer("outsider-team", other_firm, is_admin=True)
        target = _row(AgentSkill.Scope.TEAM, team=_team(firm))
        assert permissions.can_review(outsider, target) is False

    def test_same_firm_admin_can_review(self, firm: LawFirm) -> None:
        admin = _lawyer("firm-admin", firm, is_admin=True)
        target = _row(AgentSkill.Scope.LAW_FIRM, firm=firm)
        assert permissions.can_review(admin, target) is True

    def test_plain_lawyer_cannot_review(self, firm: LawFirm) -> None:
        plain = _lawyer("plain", firm)
        target = _row(AgentSkill.Scope.LAW_FIRM, firm=firm)
        assert permissions.can_review(plain, target) is False
        # 但本所全员可以编辑工作区（改完必走审批，所以放开编辑不等于放开生效）
        assert permissions.can_edit(plain, target) is True


@pytest.mark.django_db
class TestNoFirm:
    def test_lawyer_without_firm_fails_closed(self, firm: LawFirm) -> None:
        homeless = _lawyer("homeless", None)
        target = _row(AgentSkill.Scope.LAW_FIRM, firm=firm)
        for action in (
            permissions.can_edit,
            permissions.can_submit,
            permissions.can_review,
            permissions.can_archive,
            permissions.can_restore,
            permissions.can_view,
        ):
            assert action(homeless, target) is False, action.__name__
        assert permissions.can_create_firm(homeless) is False
        assert permissions.can_create_team(homeless, _team(firm)) is False

    def test_unknown_scope_fails_closed(self, firm: LawFirm) -> None:
        admin = _lawyer("unknown-scope-admin", firm, is_admin=True)
        target = _row(AgentSkill.Scope.LAW_FIRM, firm=firm)
        target.scope = "galaxy"  # 模拟脏数据 / 未来新增的作用域
        assert permissions.can_view(admin, target) is False
        assert permissions.can_edit(admin, target) is False
        assert permissions.can_review(admin, target) is False
        assert permissions.can_archive(admin, target) is False

    def test_none_inputs_fail_closed(self, firm: LawFirm) -> None:
        admin = _lawyer("none-input", firm, is_admin=True)
        assert permissions.can_view(None, None) is False
        assert permissions.can_review(None, _row(AgentSkill.Scope.LAW_FIRM, firm=firm)) is False
        assert permissions.can_review(admin, None) is False


@pytest.mark.django_db
class TestTeamScope:
    def test_biz_team_is_not_a_skill_scope(self, firm: LawFirm) -> None:
        """业务团队（``biz``）不是人员组织单元，不能承载技能作用域。"""
        member = _lawyer("biz-member", firm)
        biz = Team.objects.create(law_firm=firm, name="业务一组", team_type="biz")
        member.lawyer_teams.add(biz)
        target = _row(AgentSkill.Scope.TEAM, team=biz)
        assert permissions.can_edit(member, target) is False
        assert permissions.can_view(member, target) is False

    def test_member_of_other_team_cannot_edit(self, firm: LawFirm) -> None:
        member = _lawyer("team-a", firm)
        member.lawyer_teams.add(_team(firm, "A 组"))
        target = _row(AgentSkill.Scope.TEAM, team=_team(firm, "B 组"))
        assert permissions.can_edit(member, target) is False
        # 管理员跨团队可以（所内管理员对本所全部技能有审批权）
        admin = _lawyer("team-admin", firm, is_admin=True)
        assert permissions.can_edit(admin, target) is True

    def test_member_of_team_can_edit(self, firm: LawFirm) -> None:
        member = _lawyer("team-member", firm)
        team = _team(firm)
        member.lawyer_teams.add(team)
        target = _row(AgentSkill.Scope.TEAM, team=team)
        assert permissions.can_edit(member, target) is True
        assert permissions.can_submit(member, target) is True


@pytest.mark.django_db
class TestPersonalAndLifecycle:
    def test_personal_only_owner(self, firm: LawFirm) -> None:
        owner = _lawyer("owner", firm)
        other = _lawyer("other", firm)
        personal = _row(AgentSkill.Scope.LAWYER, lawyer=owner)
        assert permissions.can_edit(owner, personal) is True
        assert permissions.can_view(other, personal) is False
        # 个人技能不需要提审
        assert permissions.can_submit(owner, personal) is False

    def test_archived_cannot_be_submitted(self, firm: LawFirm) -> None:
        admin = _lawyer("arch-admin", firm, is_admin=True)
        target = _row(AgentSkill.Scope.LAW_FIRM, firm=firm, status=AgentSkill.Status.ARCHIVED)
        assert permissions.can_submit(admin, target) is False
        assert permissions.can_restore(admin, target) is True

    def test_restore_only_from_archived(self, firm: LawFirm) -> None:
        admin = _lawyer("restore-admin", firm, is_admin=True)
        target = _row(AgentSkill.Scope.LAW_FIRM, firm=firm, status=AgentSkill.Status.ACTIVE)
        assert permissions.can_restore(admin, target) is False

    def test_pending_blocks_resubmit(self, firm: LawFirm) -> None:
        plain = _lawyer("resubmit", firm)
        target = _row(AgentSkill.Scope.LAW_FIRM, firm=firm)
        assert permissions.can_submit(plain, target) is True
        target.review_status = AgentSkill.ReviewStatus.PENDING
        assert permissions.can_submit(plain, target) is False


@pytest.mark.django_db
class TestSingleAdminFirm:
    def test_single_admin_can_self_publish_with_ack(self, firm: LawFirm) -> None:
        """生产存在只有 1 名管理员的律所：不允许双人会签把这类律所卡死。"""
        admin = _lawyer("solo-admin", firm, is_admin=True)
        target = _row(AgentSkill.Scope.LAW_FIRM, firm=firm)
        AgentSkill.objects.filter(pk=target.pk).update(created_by=admin)
        target.refresh_from_db()
        assert permissions.can_review(admin, target) is True
        # 自审自发需要显式勾选「已确认全所生效」
        assert permissions.requires_firm_wide_ack(admin, target) is True
        assert permissions.requires_firm_wide_ack(_lawyer("other-admin", firm, is_admin=True), target) is False

    def test_admin_self_publish_succeeds(self, firm: LawFirm) -> None:
        admin = _lawyer("solo-admin-2", firm, is_admin=True)
        target = _row(AgentSkill.Scope.LAW_FIRM, firm=firm)
        AgentSkill.objects.filter(pk=target.pk).update(created_by=admin)
        target.refresh_from_db()
        assert permissions.can_edit(admin, target) is True
