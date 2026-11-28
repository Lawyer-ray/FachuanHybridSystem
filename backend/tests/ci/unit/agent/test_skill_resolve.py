"""解析入口：内置 ∪ 个人 ∪ 共享、偏好过滤、级联遮蔽、archived、跨律师隔离。

两条出口口径必须一致，否则会出现「抽屉里有、模型没有」且用户无从解释的错位：

- ``resolve_for_user``：**运行时交付面**，只含「已生效 + 本人未停用」的赢家。
- ``list_visible_skills``：**管理抽屉面**，含被遮蔽者、草稿、待审、已下线；每条用
  ``effective`` 说明「本轮是否真的会交付」，用 ``shadowed_by`` 说明被谁顶掉。

P0 只有一个 ``visible_skills`` 且折叠成 winners-only，于是「被我的同名技能遮蔽的
所内技能」在抽屉里凭空消失——律师会以为所里根本没发过那条。所以这里的断言一律
按 ``effective`` 筛，而不是「可见集 == 赢家集」。
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.agent.models import AgentSkill, AgentSkillPreference, AgentSkillRevision
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


def _firm_skill(lawyer: Lawyer, name: str, **overrides: Any) -> AgentSkill:
    """已发布的所内技能（双轨：线上正文取 ``published_revision``）。"""
    defaults: dict[str, Any] = {
        "scope": AgentSkill.Scope.LAW_FIRM,
        "law_firm": lawyer.law_firm,
        "name": name,
        "title": f"所内-{name}",
        "description": f"{name} 的描述",
        "body": "# 所内正文",
        "status": AgentSkill.Status.ACTIVE,
        "enabled": True,
        "version": 1,
        "created_by": lawyer,
    }
    defaults.update(overrides)
    skill = AgentSkill.objects.create(**defaults)
    revision = AgentSkillRevision.objects.create(
        skill=skill,
        version=skill.version,
        title=skill.title,
        description=skill.description,
        body=skill.body,
        status=skill.status,
    )
    skill.published_revision = revision
    skill.save(update_fields=["published_revision"])
    return skill


def _visible(lawyer: Lawyer) -> list[dict]:
    return resolve.list_visible_skills(user_id=lawyer.pk)


def _by_key(lawyer: Lawyer) -> dict[str, dict]:
    return {entry["key"]: entry for entry in _visible(lawyer)}


def _by_name(lawyer: Lawyer, name: str) -> dict[str, dict]:
    """同名跨层是常态：按 name 取「这一层的」条目，而不是被级联折叠后的唯一赢家。"""
    return {entry["key"]: entry for entry in _visible(lawyer) if entry["name"] == name}


@pytest.mark.django_db
class TestListVisibleSkills:
    def test_merges_builtin_and_personal(self, lawyer: Lawyer) -> None:
        personal = _personal(lawyer, "contract-review")
        skills = _by_key(lawyer)
        assert "builtin:web-research" in skills
        entry = skills[f"skill:{personal.pk}"]
        assert entry["name"] == "contract-review"
        assert entry["source"] == "user"
        assert entry["scope"] == "lawyer"
        assert entry["scope_weight"] == 0
        assert entry["editable"] is True
        assert entry["version"] == 1
        assert entry["enabled"] is True
        assert entry["effective"] is True
        assert entry["shadowed_by"] is None
        assert entry["can_edit"] is True

    def test_builtin_entries_carry_contract_fields(self, lawyer: Lawyer) -> None:
        web = next(skill for skill in _visible(lawyer) if skill["name"] == "web-research")
        assert web["key"] == "builtin:web-research"
        assert web["source"] == "builtin"
        # 内置不再用空串表示作用域：前端要能只靠 ``scope`` 分 tab
        assert web["scope"] == "builtin"
        assert web["scope_weight"] == -1
        assert web["status"] == "active"
        assert web["review_status"] == "none"
        assert web["editable"] is False
        assert web["version"] == 0
        assert web["effective"] is True

    def test_shadowed_field_present_on_every_entry(self, lawyer: Lawyer) -> None:
        _personal(lawyer, "contract-review")
        assert all(skill["shadowed"] == [] for skill in _visible(lawyer))

    def test_builtin_wins_over_dirty_db_row_with_reserved_name(self, lawyer: Lawyer) -> None:
        """历史/脏数据绕过 service 校验时，内置仍必须赢（它随代码发布）。"""
        _personal(lawyer, "web-research")
        by_name = _by_name(lawyer, "web-research")
        web = by_name["builtin:web-research"]
        assert web["source"] == "builtin"
        assert web["effective"] is True
        assert len(web["shadowed"]) == 1
        assert web["shadowed"][0]["scope"] == "lawyer"
        assert web["shadowed"][0]["title"] == "web-research"
        assert web["shadowed"][0]["key"].startswith("skill:")

    def test_archived_personal_listed_but_never_effective(self, lawyer: Lawyer) -> None:
        """已下线的个人技能留在抽屉里（否则没有入口点「恢复」），但绝不交付。"""
        archived = _personal(lawyer, "archived-one", status=AgentSkill.Status.ARCHIVED)
        key = f"skill:{archived.pk}"
        entry = _by_key(lawyer)[key]
        assert entry["status"] == "archived"
        # ``effective`` 的语义是「本轮真的会交付给模型」，不是「在级联里赢了」：
        # 已归档条目赢了级联也不能算交付。
        assert entry["effective"] is False
        assert entry["can_restore"] is True
        # 交付面完全不认它：归档是「下线即刻生效」，而不是「下次部署才生效」
        assert all(skill["key"] != key for skill in resolve.resolve_for_user(lawyer.pk))

    def test_deterministic_order(self, lawyer: Lawyer) -> None:
        _personal(lawyer, "zzz-skill")
        _personal(lawyer, "aaa-skill")
        entries = _visible(lawyer)
        # 抽屉按「来源层级 → 名字」排（所内/团队在上，个人在下），内置最后
        assert entries == sorted(entries, key=lambda item: (-item["scope_weight"], item["name"]))

    def test_other_lawyers_skill_is_invisible(self, lawyer: Lawyer, db: Any) -> None:
        other = _lawyer("resolve-other", "技能解析所二")
        theirs = _personal(other, "others-skill")
        assert all(skill["key"] != f"skill:{theirs.pk}" for skill in _visible(lawyer))


@pytest.mark.django_db
class TestCascadeShadowing:
    def test_firm_version_shadowed_by_personal_and_reported(self, lawyer: Lawyer) -> None:
        """① 个人同名技能赢；② 被遮蔽的所内条目仍在清单里且 ``shadowed_by`` 指向赢家。"""
        firm = _firm_skill(lawyer, "contract-review")
        personal = _personal(lawyer, "contract-review")
        personal_key = f"skill:{personal.pk}"
        firm_key = f"skill:{firm.pk}"

        entries = _by_key(lawyer)
        assert entries[personal_key]["effective"] is True
        assert entries[personal_key]["scope_weight"] == 0
        assert firm_key in entries, "被遮蔽的所内条目不能从抽屉里消失"
        assert entries[firm_key]["effective"] is False
        assert entries[firm_key]["shadowed_by"] == {
            "key": personal_key,
            "scope": "lawyer",
            "title": personal.title,
        }
        # 运行时面只有个人那份的正文
        resolved = {entry["key"]: entry for entry in resolve.resolve_for_user(lawyer.pk)}
        assert set(resolved) & {personal_key, firm_key} == {personal_key}

    def test_disabling_personal_falls_back_to_firm_version(self, lawyer: Lawyer) -> None:
        """关掉自己的同名技能要能回落到所内版——先滤偏好、再级联去重的直接后果。"""
        firm = _firm_skill(lawyer, "contract-review")
        personal = _personal(lawyer, "contract-review", enabled=False)
        personal_key = f"skill:{personal.pk}"
        firm_key = f"skill:{firm.pk}"

        entries = _by_key(lawyer)
        assert entries[firm_key]["effective"] is True
        assert entries[firm_key]["shadowed"] == []
        # 停用的个人条目仍在清单里（要把开关打开），但它不遮蔽任何人
        assert entries[personal_key]["enabled"] is False
        assert entries[personal_key]["effective"] is False
        assert entries[personal_key]["shadowed_by"] is None

        resolved = {entry["key"]: entry for entry in resolve.resolve_for_user(lawyer.pk)}
        assert resolved[firm_key]["body"] == "# 所内正文"


@pytest.mark.django_db
class TestPreferenceFilter:
    def test_disabled_personal_listed_but_not_resolved(self, lawyer: Lawyer) -> None:
        skill = _personal(lawyer, "off-one", enabled=False)
        key = f"skill:{skill.pk}"
        assert any(entry["key"] == key and entry["enabled"] is False for entry in _visible(lawyer))
        assert all(entry["key"] != key for entry in resolve.resolve_for_user(lawyer.pk))

    def test_disabled_builtin_preference_hides_from_resolve(self, lawyer: Lawyer) -> None:
        AgentSkillPreference.objects.create(user=lawyer, skill_key="builtin:web-research", enabled=False)
        resolved = {skill["key"] for skill in resolve.resolve_for_user(lawyer.pk)}
        visible = _by_key(lawyer)
        assert "builtin:web-research" not in resolved
        assert visible["builtin:web-research"]["enabled"] is False
        assert visible["builtin:web-research"]["effective"] is False

    def test_preference_of_another_user_does_not_leak(self, lawyer: Lawyer, db: Any) -> None:
        other = _lawyer("resolve-pref-other", "技能解析所三")
        AgentSkillPreference.objects.create(user=other, skill_key="builtin:web-research", enabled=False)
        resolved = {skill["key"] for skill in resolve.resolve_for_user(lawyer.pk)}
        assert "builtin:web-research" in resolved
