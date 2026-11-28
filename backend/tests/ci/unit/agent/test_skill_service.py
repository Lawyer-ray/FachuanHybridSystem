"""skill_service 门面单测 —— 内置库扫描、偏好合并、非法名拒绝、零磁盘副作用。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from apps.agent.models import AgentSkillPreference
from apps.agent.services import skill_service


@pytest.fixture
def user(db: Any) -> Any:
    from apps.organization.models import LawFirm, Lawyer

    firm = LawFirm.objects.create(name="技能测试律所")
    return Lawyer.objects.create_user(
        username="skill-user",
        password="x-test-12345678",  # pragma: allowlist secret
        law_firm=firm,
    )


class TestListSkills:
    def test_lists_repo_skills_with_frontmatter(self) -> None:
        skills = skill_service.list_skills()
        names = [s["name"] for s in skills]
        # 随代码发布的技能必须在列（名字即目录名，``/skill:`` 补全与 MCP 按名读取依赖同名）
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
        AgentSkillPreference.objects.create(user=user, skill_key="builtin:web-research", enabled=False)
        mine = {s["name"]: s["enabled"] for s in skill_service.skills_for_user(user.pk)}
        assert mine["web-research"] is False
        assert mine["deadline-queries"] is True

    def test_enabled_skill_paths_is_empty_and_writes_nothing(
        self, user: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """方案 A：技能不再物化到磁盘，``enabled_skill_paths`` 恒空且零写盘。

        把技能库根指到空目录再调一次：如果函数还残留任何目录创建/拷贝，这里就会
        看到新文件。``--skill <dir>`` 在 pi 1.6.0 既带不来自主发现，也压不住案件页
        前置的 ``[当前业务：…]`` 锚点，所以它连「兼容保留」的价值都没有。
        """
        monkeypatch.setenv("FACHUAN_AGENT_SKILLS_DIR", str(tmp_path))
        AgentSkillPreference.objects.create(user=user, skill_key="builtin:web-research", enabled=False)
        assert skill_service.enabled_skill_paths(user.pk) == []
        assert list(tmp_path.rglob("*")) == []

    def test_set_skill_enabled_roundtrip(self, user: Any) -> None:
        result = skill_service.set_skill_enabled(user.pk, "web-research", False)
        assert result == {"key": "builtin:web-research", "enabled": False}
        # 幂等 upsert：再开一次不产生第二行
        skill_service.set_skill_enabled(user.pk, "web-research", True)
        assert AgentSkillPreference.objects.filter(user=user, skill_key="builtin:web-research").count() == 1


class TestValidation:
    @pytest.mark.parametrize("bad_name", ["../escape", "Web-Research", "a b", "", "x" * 65, "名"])
    def test_rejects_illegal_names(self, user: Any, bad_name: str) -> None:
        with pytest.raises(ValueError):
            skill_service.set_skill_enabled(user.pk, bad_name, True)

    def test_rejects_unknown_skill(self, user: Any) -> None:
        with pytest.raises(ValueError, match="未知技能"):
            skill_service.set_skill_enabled(user.pk, "not-in-library", True)
