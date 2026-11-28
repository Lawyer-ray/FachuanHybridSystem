"""物化落盘：原子写、幂等、prune、缺失目录时注入跳过。

目录布局 ``$FACHUAN_AGENT_HOME/skills/<user_id>/<name>/SKILL.md`` 是 pi 的
``--skill`` 输入，路径必须真实存在——缺失时静默跳过会让「技能不生效」变成
「模型说没有这个技能」，所以这里同时守住「缺失时跳过并告警」的分支。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from apps.agent.models import AgentSkill
from apps.agent.services import skill_service
from apps.agent.services.skills import store
from apps.agent.services.skills.render import render_skill_md

TEST_PASSWORD = "x-test-12345678"  # pragma: allowlist secret


@pytest.fixture(autouse=True)
def _agent_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """把物化根目录指到临时目录，绝不碰真实的 ~/.fachuan-agent。"""
    monkeypatch.setenv("FACHUAN_AGENT_HOME", str(tmp_path))
    return tmp_path


def _skill(name: str = "mine", *, lawyer_id: int = 7, body: str = "# 做法") -> AgentSkill:
    """未保存的模型实例即可：write_skill 只读四个字段。"""
    return AgentSkill(lawyer_id=lawyer_id, name=name, description="我的技能", body=body)


@pytest.mark.django_db
class TestWrite:
    def test_writes_rendered_skill_md(self) -> None:
        directory = store.write_skill(_skill())
        assert directory == store.root_for(7) / "mine"
        assert (directory / "SKILL.md").read_text(encoding="utf-8") == render_skill_md("mine", "我的技能", "# 做法")

    def test_second_write_with_same_bytes_does_not_replace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store.write_skill(_skill())
        calls: list[tuple[str, str]] = []
        real_replace = os.replace

        def counting_replace(src: Any, dst: Any) -> None:
            calls.append((str(src), str(dst)))
            real_replace(src, dst)

        monkeypatch.setattr(os, "replace", counting_replace)
        store.write_skill(_skill())
        assert calls == [], "字节未变不应重写（多栏并答会重复调用）"

    def test_changed_bytes_replace_atomically(self) -> None:
        store.write_skill(_skill(body="v1"))
        store.write_skill(_skill(body="v2"))
        target = store.root_for(7) / "mine" / "SKILL.md"
        assert "v2" in target.read_text(encoding="utf-8")
        assert list(target.parent.glob("*.tmp")) == [], "临时文件必须已被 os.replace 收走"

    def test_file_mode_is_0600(self) -> None:
        directory = store.write_skill(_skill())
        assert (directory / "SKILL.md").stat().st_mode & 0o777 == 0o600

    def test_rejects_path_traversal_name(self) -> None:
        with pytest.raises(ValueError):
            store.write_skill(_skill(name="../evil"))


@pytest.mark.django_db
class TestPruneAndRemove:
    def test_prune_removes_dirs_outside_keep(self) -> None:
        store.write_skill(_skill("keep-me"))
        store.write_skill(_skill("drop-me"))
        assert store.prune(7, {"keep-me"}) == ["drop-me"]
        assert store.list_dirs(7) == ["keep-me"]

    def test_remove_skill_is_idempotent(self) -> None:
        store.write_skill(_skill())
        assert store.remove_skill(7, "mine") is True
        assert store.remove_skill(7, "mine") is False


@pytest.mark.django_db
class TestEnabledSkillPaths:
    def _lawyer(self, username: str) -> Any:
        from apps.organization.models import LawFirm, Lawyer

        firm = LawFirm.objects.create(name=f"物化测试所-{username}")
        return Lawyer.objects.create_user(username=username, password=TEST_PASSWORD, law_firm=firm)

    def _personal_skill(self, lawyer: Any, name: str = "mine") -> AgentSkill:
        return AgentSkill.objects.create(
            scope=AgentSkill.Scope.LAWYER,
            lawyer=lawyer,
            name=name,
            title="我的技能",
            description="我的技能描述",
            body="# 做法",
            status=AgentSkill.Status.ACTIVE,
            enabled=True,
            created_by=lawyer,
        )

    def test_missing_personal_dir_is_skipped(self) -> None:
        lawyer = self._lawyer("store-missing")
        skill = self._personal_skill(lawyer)
        paths = skill_service.enabled_skill_paths(lawyer.pk)
        assert all(not path.endswith(f"/{skill.name}") for path in paths), "目录缺失时必须跳过（不是注入空目录）"

    def test_existing_personal_dir_is_injected(self) -> None:
        lawyer = self._lawyer("store-present")
        skill = self._personal_skill(lawyer)
        store.write_skill(skill)
        paths = skill_service.enabled_skill_paths(lawyer.pk)
        assert any(path.endswith(f"/{skill.name}") for path in paths)
        assert all(Path(path).is_dir() for path in paths)

    def test_disabled_personal_skill_not_injected(self) -> None:
        lawyer = self._lawyer("store-disabled")
        skill = self._personal_skill(lawyer)
        store.write_skill(skill)
        skill.enabled = False
        skill.save(update_fields=["enabled"])
        assert all(not path.endswith(f"/{skill.name}") for path in skill_service.enabled_skill_paths(lawyer.pk))
