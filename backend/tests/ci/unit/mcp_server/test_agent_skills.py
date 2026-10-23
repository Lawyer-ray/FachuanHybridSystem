"""get_agent_skill 工具测试：技能供给、白名单与路径穿越防护。

技能包是随代码发布的静态文件（apps/agent/pi/skills/*/SKILL.md），
本工具是模型按需读取它们的唯一通道（pi 原生 Skills 需要 read 工具，
本系统不向模型声明任何文件读取工具，见模块 docstring）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mcp_server.tools.core.agent_skills import _DEFAULT_SKILLS_ROOT, available_skill_names, get_agent_skill

#: 与 AGENTS.md 路由表一致的四个技能（改名/删除要同步改 AGENTS.md 与本测试）
EXPECTED_SKILLS = {"deadline-queries", "list-projection", "materials-parsing", "web-research"}


class TestGetAgentSkill:
    def test_returns_content_for_each_expected_skill(self) -> None:
        for name in EXPECTED_SKILLS:
            result = get_agent_skill(name)
            assert result["name"] == name
            # SKILL.md 全文：frontmatter + 正文（含场景化指引）
            assert result["content"].startswith("---")
            assert "name:" in result["content"]
            assert len(result["content"]) > 100

    def test_content_matches_packaged_file(self) -> None:
        skill_file = _DEFAULT_SKILLS_ROOT / "deadline-queries" / "SKILL.md"
        assert skill_file.is_file(), "技能包未随代码发布"
        assert get_agent_skill("deadline-queries")["content"] == skill_file.read_text(encoding="utf-8")

    def test_name_normalized_trimmed(self) -> None:
        # 大小写与首尾空白归一（模型偶发传 " Web-Research " 这类）
        result = get_agent_skill(" Web-Research ")
        assert result["name"] == "web-research"

    def test_unknown_skill_lists_available(self) -> None:
        with pytest.raises(ValueError, match=r"未知技能.*可用技能"):
            get_agent_skill("nonexistent-skill")

    @pytest.mark.parametrize(
        "bad",
        [
            "../secrets",  # 穿越到上级
            "a/b",  # 路径分隔符
            "/etc/passwd",  # 绝对路径
            "..",  # 纯穿越
            "",  # 空
            "技能名",  # 非法字符（非规范字符集）
            "UPPER",  # 大写（归一后合法名仍必须存在——UPPER→upper 不存在）
        ],
    )
    def test_rejects_path_traversal_and_bad_names(self, bad: str) -> None:
        with pytest.raises(ValueError):
            get_agent_skill(bad)

    def test_available_names_match_expected(self) -> None:
        names = set(available_skill_names())
        assert names >= EXPECTED_SKILLS, f"技能包缺失: {EXPECTED_SKILLS - names}"


class TestSkillsPackagedWithCode:
    """技能包与 AGENTS.md 路由的一致性：路由表里的名字必须真实存在。"""

    def test_agents_md_routes_only_existing_skills(self) -> None:
        agents_md = (_DEFAULT_SKILLS_ROOT.parent / "AGENTS.md").read_text(encoding="utf-8")
        for name in EXPECTED_SKILLS:
            assert name in agents_md, f"AGENTS.md 路由表缺少技能 {name}"

    def test_each_skill_has_required_frontmatter(self) -> None:
        for skill_dir in sorted(Path(_DEFAULT_SKILLS_ROOT).iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            assert skill_file.is_file(), f"{skill_dir.name} 缺 SKILL.md"
            text = skill_file.read_text(encoding="utf-8")
            assert text.startswith("---"), f"{skill_dir.name} 缺 frontmatter"
            assert "description:" in text, f"{skill_dir.name} 缺 description（Agent Skills 规范必填）"
