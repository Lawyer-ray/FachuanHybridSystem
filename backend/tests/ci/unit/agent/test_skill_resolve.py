"""解析入口：内置 ∪ 个人、偏好过滤、archived、跨律师隔离、shadowed 结构。

``resolve_for_user`` 是注入面的唯一入口；``visible_skills`` 是它的「含禁用项」
版本（清单页要显示开关）。两者口径必须一致，否则会出现「清单里有、注入里没有」
且用户无从解释的错位。
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.agent.models import AgentSkill, AgentSkillPreference
from apps.agent.services.skills import resolve
from apps.organization.models import LawFirm, Lawyer

TEST_PASSWORD = "x-test-12345678"  # pragma: allowlist secret


def _lawyer(username: str, firm_name: str) -> Lawyer:
    firm = LawFirm.objects.create(name=firm_name)
    return Lawyer.objects.create_user(username=username, password=TEST_PASSWORD, law_firm=firm)


@pytest.fixture
def lawyer(db: Any) -> Lawyer:
    return _lawyer("resolve-user", "技能解析所")


def _personal(lawyer: Lawyer, name: str, **overrides: Any) -> AgentSkill:
    defaults: dict[str, Any] = {
        "scope": AgentSkill.Scope.LAWYER,
        "lawyer": lawyer,
        "name": name,
        "title": name,
        "description": f"{name} 的描述",
        "body": "# 做法",
        "status": AgentSkill.Status.ACTIVE,
        "enabled": True,
        "created_by": lawyer,
    }
    defaults.update(overrides)
    return AgentSkill.objects.create(**defaults)


@pytest.mark.django_db
class TestVisibleSkills:
    def test_merges_builtin_and_personal(self, lawyer: Lawyer) -> None:
        personal = _personal(lawyer, "contract-review")
        skills = {skill["key"]: skill for skill in resolve.visible_skills(lawyer.pk)}
        assert "builtin:web-research" in skills
        entry = skills[f"skill:{personal.pk}"]
        assert entry["name"] == "contract-review"
        assert entry["source"] == "user"
        assert entry["scope"] == "lawyer"
        assert entry["editable"] is True
        assert entry["version"] == 1
        assert entry["enabled"] is True

    def test_builtin_entries_carry_contract_fields(self, lawyer: Lawyer) -> None:
        web = next(skill for skill in resolve.visible_skills(lawyer.pk) if skill["name"] == "web-research")
        assert web["key"] == "builtin:web-research"
        assert web["source"] == "builtin"
        assert web["scope"] == ""
        assert web["editable"] is False
        assert web["version"] == 0

    def test_shadowed_field_present_on_every_entry(self, lawyer: Lawyer) -> None:
        _personal(lawyer, "contract-review")
        assert all(skill["shadowed"] == [] for skill in resolve.visible_skills(lawyer.pk))

    def test_builtin_wins_over_dirty_db_row_with_reserved_name(self, lawyer: Lawyer) -> None:
        """历史/脏数据绕过 service 校验时，内置仍必须赢（它随代码发布）。"""
        _personal(lawyer, "web-research")
        web = next(skill for skill in resolve.visible_skills(lawyer.pk) if skill["name"] == "web-research")
        assert web["source"] == "builtin"
        assert len(web["shadowed"]) == 1
        assert web["shadowed"][0]["scope"] == "lawyer"
        assert web["shadowed"][0]["title"] == "web-research"
        assert web["shadowed"][0]["key"].startswith("skill:")

    def test_archived_is_never_visible(self, lawyer: Lawyer) -> None:
        archived = _personal(lawyer, "archived-one", status=AgentSkill.Status.ARCHIVED)
        key = f"skill:{archived.pk}"
        assert all(skill["key"] != key for skill in resolve.visible_skills(lawyer.pk))
        assert all(skill["key"] != key for skill in resolve.resolve_for_user(lawyer.pk))

    def test_deterministic_order(self, lawyer: Lawyer) -> None:
        _personal(lawyer, "zzz-skill")
        _personal(lawyer, "aaa-skill")
        names = [skill["name"] for skill in resolve.visible_skills(lawyer.pk)]
        assert names == sorted(names)

    def test_other_lawyers_skill_is_invisible(self, lawyer: Lawyer, db: Any) -> None:
        other = _lawyer("resolve-other", "技能解析所二")
        theirs = _personal(other, "others-skill")
        assert all(skill["key"] != f"skill:{theirs.pk}" for skill in resolve.visible_skills(lawyer.pk))


@pytest.mark.django_db
class TestPreferenceFilter:
    def test_disabled_personal_listed_but_not_resolved(self, lawyer: Lawyer) -> None:
        skill = _personal(lawyer, "off-one", enabled=False)
        key = f"skill:{skill.pk}"
        assert any(entry["key"] == key and entry["enabled"] is False for entry in resolve.visible_skills(lawyer.pk))
        assert all(entry["key"] != key for entry in resolve.resolve_for_user(lawyer.pk))

    def test_disabled_builtin_preference_hides_from_resolve(self, lawyer: Lawyer) -> None:
        AgentSkillPreference.objects.create(user=lawyer, skill_key="builtin:web-research", enabled=False)
        resolved = {skill["key"] for skill in resolve.resolve_for_user(lawyer.pk)}
        visible = {skill["key"]: skill for skill in resolve.visible_skills(lawyer.pk)}
        assert "builtin:web-research" not in resolved
        assert visible["builtin:web-research"]["enabled"] is False

    def test_preference_of_another_user_does_not_leak(self, lawyer: Lawyer, db: Any) -> None:
        other = _lawyer("resolve-pref-other", "技能解析所三")
        AgentSkillPreference.objects.create(user=other, skill_key="builtin:web-research", enabled=False)
        resolved = {skill["key"] for skill in resolve.resolve_for_user(lawyer.pk)}
        assert "builtin:web-research" in resolved
