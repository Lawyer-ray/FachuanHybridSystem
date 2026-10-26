"""skill_service 单测 —— 扫描、偏好合并、非法名拒绝、注入路径。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from apps.agent.models.agent import AgentSkillPreference
from apps.agent.services import skill_service

#: 仓库内真实技能库（4 份 SKILL.md 随代码发布）；测试不造假目录，直接用真的——
#: 顺带守住「技能库被误删/改名」这类部署事故。
REAL_ROOT = Path(skill_service.__file__).resolve().parents[1] / "pi" / "skills"


@pytest.fixture
def user(db: Any) -> Any:
    from apps.organization.models import LawFirm, Lawyer

    firm = LawFirm.objects.create(name="技能测试律所")
    return Lawyer.objects.create_user(
        username="skill-user", password="x-test-12345678", law_firm=firm  # pragma: allowlist secret
    )


class TestListSkills:
    def test_lists_repo_skills_with_frontmatter(self) -> None:
        skills = skill_service.list_skills()
        names = [s["name"] for s in skills]
        # 随代码发布的技能必须在列（名字即目录名，pi 侧 /skill: 补全依赖同名）
        assert "web-research" in names
        assert "deadline-queries" in names
        web = next(s for s in skills if s["name"] == "web-research")
        assert web["description"]  # frontmatter 的 description 必须解析出来

    def test_sorted_by_name(self) -> None:
        names = [s["name"] for s in skill_service.list_skills()]
        assert names == sorted(names)


class TestUserPreferences:
    def test_default_all_enabled(self, user: Any) -> None:
        """偏好只记差异：没写过偏好的用户看到的全是启用。"""
        for skill in skill_service.skills_for_user(user.pk):
            assert skill["enabled"] is True

    def test_disabled_only_affects_that_user(self, user: Any, db: Any) -> None:
        AgentSkillPreference.objects.create(user=user, skill_name="web-research", enabled=False)
        mine = {s["name"]: s["enabled"] for s in skill_service.skills_for_user(user.pk)}
        assert mine["web-research"] is False
        assert mine["deadline-queries"] is True

    def test_enabled_paths_exclude_disabled(self, user: Any) -> None:
        AgentSkillPreference.objects.create(user=user, skill_name="web-research", enabled=False)
        paths = skill_service.enabled_skill_paths(user.pk)
        assert paths, "至少还有其他技能在列"
        assert all(REAL_ROOT.as_posix() not in p or "web-research" not in p for p in paths)
        assert all(Path(p).is_dir() for p in paths), "注入路径必须真实存在（--skill 指向空目录只是静默无技能）"

    def test_set_skill_enabled_roundtrip(self, user: Any) -> None:
        result = skill_service.set_skill_enabled(user.pk, "web-research", False)
        assert result == {"name": "web-research", "enabled": False}
        # 幂等 upsert：再开一次不产生第二行
        skill_service.set_skill_enabled(user.pk, "web-research", True)
        assert AgentSkillPreference.objects.filter(user=user, skill_name="web-research").count() == 1


class TestValidation:
    @pytest.mark.parametrize("bad_name", ["../escape", "Web-Research", "a b", "", "x" * 65, "名"])
    def test_rejects_illegal_names(self, user: Any, bad_name: str) -> None:
        with pytest.raises(ValueError):
            skill_service.set_skill_enabled(user.pk, bad_name, True)

    def test_rejects_unknown_skill(self, user: Any) -> None:
        with pytest.raises(ValueError, match="未知技能"):
            skill_service.set_skill_enabled(user.pk, "not-in-library", True)
