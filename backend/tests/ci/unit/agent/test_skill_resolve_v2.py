"""解析语义 v2：双轨正文、先滤偏好后级联、被遮蔽条目不消失、跨所隔离、稳定排序。

这组用例守的是**语义**而不是实现：每一条都对应一个「实现看起来没问题、但律师
会看到错东西」的场景。P0 的 ``visible_skills`` 在两条上都错过（列表吞掉被遮蔽
的所内技能；先去重再滤偏好导致停用个人版连所内版一起消失），所以这里逐条钉死。
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.agent.models import AgentSkill, AgentSkillPreference, AgentSkillRevision
from apps.agent.services.skills import flags, resolve
from apps.organization.models import LawFirm, Lawyer, Team

TEST_PASSWORD = "x-test-12345678"  # pragma: allowlist secret


def _firm(name: str) -> LawFirm:
    return LawFirm.objects.create(name=name)


def _lawyer(username: str, firm: LawFirm | None, *, is_admin: bool = False) -> Lawyer:
    return Lawyer.objects.create_user(
        username=username, password=TEST_PASSWORD, law_firm=firm, is_admin=is_admin
    )


def _team(firm: LawFirm, name: str = "诉讼一组") -> Team:
    return Team.objects.create(law_firm=firm, name=name, team_type="lawyer")


def _row(
    *,
    scope: str,
    name: str,
    body: str = "# 做法",
    lawyer: Lawyer | None = None,
    team: Team | None = None,
    firm: LawFirm | None = None,
    status: str = AgentSkill.Status.ACTIVE,
    enabled: bool = True,
) -> AgentSkill:
    return AgentSkill.objects.create(
        scope=scope,
        name=name,
        title=f"{name}-标题",
        description=f"{name} 的描述",
        body=body,
        lawyer=lawyer,
        team=team,
        law_firm=firm,
        status=status,
        enabled=enabled,
        created_by=lawyer,
    )


def _publish(skill: AgentSkill, *, version: int, body: str) -> AgentSkillRevision:
    """把一条共享技能「发布」到指定版本（模拟走完审批）。"""
    revision = AgentSkillRevision.objects.create(
        skill=skill,
        version=version,
        title=skill.title,
        description=skill.description,
        body=body,
        status=skill.status,
    )
    skill.published_revision = revision
    skill.save(update_fields=["published_revision"])
    return revision


@pytest.fixture
def firm(db: Any) -> LawFirm:
    return _firm("解析所")


@pytest.fixture
def lawyer(db: Any, firm: LawFirm) -> Lawyer:
    return _lawyer("resolve-v2", firm)


@pytest.mark.django_db
class TestSharedDelivery:
    """共享技能的运行时正文只认 ``published_revision``。"""

    def test_delivers_published_revision_not_workspace(self, lawyer: Lawyer, firm: LawFirm) -> None:
        skill = _row(scope=AgentSkill.Scope.LAW_FIRM, name="firm-rule", firm=firm, body="工作区草稿")
        _publish(skill, version=1, body="线上已批准版")
        skill.body = "工作区草稿"
        skill.version = 2
        skill.save(update_fields=["body", "version"])

        entry = next(item for item in resolve.resolve_for_user(lawyer.pk) if item["name"] == "firm-rule")
        assert entry["body"] == "线上已批准版"
        assert entry["version"] == 1
        assert entry["scope"] == "law_firm"
        assert entry["scope_weight"] == 2

    def test_unpublished_shared_skill_is_not_delivered(self, lawyer: Lawyer, firm: LawFirm) -> None:
        _row(scope=AgentSkill.Scope.LAW_FIRM, name="never-approved", firm=firm, status=AgentSkill.Status.DRAFT)
        names = [item["name"] for item in resolve.resolve_for_user(lawyer.pk)]
        assert "never-approved" not in names

    def test_team_skill_requires_membership(self, lawyer: Lawyer, firm: LawFirm) -> None:
        team = _team(firm)
        _publish(_row(scope=AgentSkill.Scope.TEAM, name="team-rule", team=team), version=1, body="团队规范")
        assert "team-rule" not in [item["name"] for item in resolve.resolve_for_user(lawyer.pk)]

        lawyer.lawyer_teams.add(team)
        assert "team-rule" in [item["name"] for item in resolve.resolve_for_user(lawyer.pk)]


@pytest.mark.django_db
class TestPreferenceBeforeCascade:
    """先滤偏好、再级联——停用个人版要能回落到所内版。"""

    def test_disabling_personal_falls_back_to_firm(self, lawyer: Lawyer, firm: LawFirm) -> None:
        personal = _row(scope=AgentSkill.Scope.LAWYER, name="contract-review", lawyer=lawyer, enabled=False)
        shared = _row(scope=AgentSkill.Scope.LAW_FIRM, name="contract-review", firm=firm, body="所内版")
        _publish(shared, version=1, body="所内版")

        delivered = [item for item in resolve.resolve_for_user(lawyer.pk) if item["name"] == "contract-review"]
        assert [item["key"] for item in delivered] == [f"skill:{shared.pk}"]
        assert delivered[0]["body"] == "所内版"
        assert f"skill:{personal.pk}" not in [item["key"] for item in resolve.resolve_for_user(lawyer.pk)]

    def test_personal_wins_when_enabled(self, lawyer: Lawyer, firm: LawFirm) -> None:
        personal = _row(scope=AgentSkill.Scope.LAWYER, name="contract-review", lawyer=lawyer, body="我的版")
        shared = _row(scope=AgentSkill.Scope.LAW_FIRM, name="contract-review", firm=firm)
        _publish(shared, version=1, body="所内版")

        delivered = next(item for item in resolve.resolve_for_user(lawyer.pk) if item["name"] == "contract-review")
        assert delivered["key"] == f"skill:{personal.pk}"
        assert delivered["body"] == "我的版"
        assert delivered["shadowed"] == [{"key": f"skill:{shared.pk}", "scope": "law_firm", "title": shared.title}]

    def test_disabling_shared_uses_preference_row(self, lawyer: Lawyer, firm: LawFirm) -> None:
        shared = _row(scope=AgentSkill.Scope.LAW_FIRM, name="firm-rule", firm=firm)
        _publish(shared, version=1, body="所内版")
        AgentSkillPreference.objects.create(user=lawyer, skill_key=f"skill:{shared.pk}", enabled=False)
        assert "firm-rule" not in [item["name"] for item in resolve.resolve_for_user(lawyer.pk)]


@pytest.mark.django_db
class TestListVisibleSkills:
    """管理面绝不吞掉被遮蔽条目，并给出 shadowed_by。"""

    def test_shadowed_firm_skill_still_listed(self, lawyer: Lawyer, firm: LawFirm) -> None:
        personal = _row(scope=AgentSkill.Scope.LAWYER, name="dup", lawyer=lawyer)
        shared = _row(scope=AgentSkill.Scope.LAW_FIRM, name="dup", firm=firm)
        _publish(shared, version=1, body="所内版")

        listed = {item["key"]: item for item in resolve.list_visible_skills(user_id=lawyer.pk)}
        assert f"skill:{shared.pk}" in listed, "被遮蔽的所内技能不能从清单里消失"
        assert listed[f"skill:{shared.pk}"]["effective"] is False
        assert listed[f"skill:{shared.pk}"]["shadowed_by"]["key"] == f"skill:{personal.pk}"
        assert listed[f"skill:{personal.pk}"]["effective"] is True

    def test_drafts_visible_to_author_only(self, lawyer: Lawyer, firm: LawFirm) -> None:
        other = _lawyer("other-author", firm)
        mine = _row(scope=AgentSkill.Scope.LAW_FIRM, name="my-draft", firm=firm, lawyer=None, status=AgentSkill.Status.DRAFT)
        AgentSkill.objects.filter(pk=mine.pk).update(created_by=lawyer)
        theirs = _row(scope=AgentSkill.Scope.LAW_FIRM, name="their-draft", firm=firm, status=AgentSkill.Status.DRAFT)
        AgentSkill.objects.filter(pk=theirs.pk).update(created_by=other)

        keys = {item["key"] for item in resolve.list_visible_skills(user_id=lawyer.pk)}
        assert f"skill:{mine.pk}" in keys
        assert f"skill:{theirs.pk}" not in keys

    def test_no_body_in_list(self, lawyer: Lawyer, firm: LawFirm) -> None:
        """列表不带 ``body``：60 条 × 32KB 会把抽屉的首屏响应拖成兆级。"""
        _row(scope=AgentSkill.Scope.LAWYER, name="big", lawyer=lawyer, body="x" * 5000)
        for item in resolve.list_visible_skills(user_id=lawyer.pk):
            assert "body" not in item


@pytest.mark.django_db
class TestIsolation:
    def test_other_firm_not_visible(self, lawyer: Lawyer) -> None:
        other_firm = _firm("别的所")
        _publish(_row(scope=AgentSkill.Scope.LAW_FIRM, name="other-rule", firm=other_firm), version=1, body="外所规范")
        assert "other-rule" not in [item["name"] for item in resolve.resolve_for_user(lawyer.pk)]

    def test_lawyer_without_firm_gets_no_shared(self, firm: LawFirm) -> None:
        homeless = _lawyer("no-firm", None)
        _publish(_row(scope=AgentSkill.Scope.LAW_FIRM, name="firm-rule", firm=firm), version=1, body="所内版")
        # law_firm_id=None 不能被当成一个「律所」去匹配所有无律所行
        _publish(_row(scope=AgentSkill.Scope.LAW_FIRM, name="ghost-rule", firm=firm), version=1, body="幽灵")
        names = [item["name"] for item in resolve.resolve_for_user(homeless.pk)]
        assert names == [skill["name"] for skill in resolve.resolve_for_user(None)]

    def test_none_user_gets_builtin_only(self) -> None:
        assert {item["scope"] for item in resolve.resolve_for_user(None)} == {"builtin"}


@pytest.mark.django_db
class TestOrdering:
    def test_stable_sort_by_scope_weight_then_name(self, lawyer: Lawyer, firm: LawFirm) -> None:
        _row(scope=AgentSkill.Scope.LAWYER, name="zz-personal", lawyer=lawyer)
        shared = _row(scope=AgentSkill.Scope.LAW_FIRM, name="aa-firm", firm=firm)
        _publish(shared, version=1, body="所内版")

        ordered = resolve.resolve_for_user(lawyer.pk)
        keys = [(item["scope_weight"], item["name"]) for item in ordered]
        assert keys == sorted(keys), "必须按 (scope_weight, name) 排序，否则系统提示前缀每轮都在变"
        # 内置在最前
        assert ordered[0]["scope"] == "builtin"


@pytest.mark.django_db
class TestFlagOff:
    def test_off_returns_builtin_only(self, lawyer: Lawyer, firm: LawFirm, monkeypatch: pytest.MonkeyPatch) -> None:
        _row(scope=AgentSkill.Scope.LAWYER, name="mine", lawyer=lawyer)
        shared = _row(scope=AgentSkill.Scope.LAW_FIRM, name="firm-rule", firm=firm)
        _publish(shared, version=1, body="所内版")
        monkeypatch.setenv(flags.ENV_VAR, "off")
        flags.reset_cache()
        assert [item["scope"] for item in resolve.resolve_for_user(lawyer.pk)] == ["builtin"] * len(
            resolve.resolve_for_user(None)
        )

    def test_dry_still_resolves(self, lawyer: Lawyer, monkeypatch: pytest.MonkeyPatch) -> None:
        _row(scope=AgentSkill.Scope.LAWYER, name="mine", lawyer=lawyer)
        monkeypatch.setenv(flags.ENV_VAR, "dry")
        flags.reset_cache()
        assert "mine" in [item["name"] for item in resolve.resolve_for_user(lawyer.pk)]

    def test_illegal_value_falls_back_to_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(flags.ENV_VAR, "of")  # 拼错一个字母
        flags.reset_cache()
        assert flags.user_skills_mode() == "on"
