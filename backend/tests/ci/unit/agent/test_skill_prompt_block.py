"""索引块：块首形状（pi 不把它当文件路径）、两轮裁剪、预算、标签、开关。

预算裁剪是这块最容易悄悄坏的地方：一个 ``for + break`` 就能让「所内技能太多」变成
「后面的个人技能全部消失」，而模型只是「想不起来还有这个技能」——没有任何报错。
所以这里同时钉死「30 条都进得去」「超预算的进 not_injected 而不是被吞」两件事。
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.agent.services.skills import prompt_block

LONG_DESCRIPTION = "审阅合同时使用的三段式规范，逐条核对主体资格、价款与违约责任" * 12


def _skill(name: str, *, scope: str = "lawyer", title: str = "", description: str = "") -> dict[str, Any]:
    """一条 ``resolve_for_user`` 形状的技能条目（只填渲染块用得到的字段）。"""
    return {
        "key": f"skill:{name}",
        "name": name,
        "title": title or name,
        "description": description or f"{name} 的描述",
        "scope": scope,
        "source": "builtin" if scope == "builtin" else "user",
        "enabled": True,
        "version": 1,
        "body": f"# {name} 正文",
    }


def _firm_skill(name: str, *, scope: str = "law_firm") -> dict[str, Any]:
    return _skill(name, scope=scope)


@pytest.fixture(autouse=True)
def _block_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认把总开关按「开」摆好：开发机 ``.env`` 里若配成 dry/off 会让整组假红。"""
    monkeypatch.delenv(prompt_block._USER_SKILLS_ENV, raising=False)


class TestBlockShape:
    def test_empty_skills_returns_empty(self) -> None:
        assert prompt_block.render_skill_block([]) == ("", [])

    def test_heading_is_the_first_line(self) -> None:
        """块首必须是 markdown 标题：pi 的 ``existsSync`` 分支只对路径形态的参数触发。"""
        block, _ = prompt_block.render_skill_block([_firm_skill("contract-review")])
        first_line = block.splitlines()[0]
        assert first_line == prompt_block.BLOCK_HEADING
        assert first_line == "## 可用技能（法穿）"
        assert not block.startswith("/")
        assert "get_agent_skill" in block

    def test_full_line_format(self) -> None:
        entry = _skill("contract-review", scope="law_firm", title="合同审查三段式", description="审阅合同时使用")
        block, _ = prompt_block.render_skill_block([entry])
        assert "- [所内] contract-review：《合同审查三段式》——审阅合同时使用" in block

    def test_scope_labels(self) -> None:
        entries = [_skill(f"skill-{scope}", scope=scope) for scope in ("builtin", "lawyer", "team", "law_firm")]
        block, _ = prompt_block.render_skill_block(entries)
        for label in ("[内置]", "[我的]", "[团队]", "[所内]"):
            assert label in block

    def test_entry_without_description_keeps_a_line(self) -> None:
        block, _ = prompt_block.render_skill_block([_skill("quiet", description="  ")])
        assert "- [我的] quiet：《quiet》" in block
        assert "——" not in block


class TestDescription:
    def test_whitespace_collapsed_to_one_line(self) -> None:
        entry = _skill("multiline", description="第一行\n第二行\t带   多空格")
        block, _ = prompt_block.render_skill_block([entry])
        item_lines = [line for line in block.splitlines() if line.startswith("- [")]
        assert len(item_lines) == 1
        assert "第一行 第二行 带 多空格" in item_lines[0]

    def test_truncated_to_budget_with_ellipsis(self) -> None:
        block, _ = prompt_block.render_skill_block([_skill("long", description=LONG_DESCRIPTION)])
        rendered = block.split("——", 1)[1].strip()
        assert rendered.endswith("…")
        assert len(rendered) == prompt_block.PER_ITEM_DESCRIPTION_MAX + 1

    def test_short_description_not_truncated(self) -> None:
        block, _ = prompt_block.render_skill_block([_skill("short", description="审阅合同时使用")])
        assert block.split("——", 1)[1].strip() == "审阅合同时使用"


class TestBudget:
    def test_thirty_items_all_injected_in_two_rounds(self) -> None:
        """第一轮吃饱完整行，剩余降级成「只留名字」——**一条都不能丢**。"""
        entries = [_skill(f"skill-{index:02d}", description=LONG_DESCRIPTION) for index in range(30)]
        block, not_injected = prompt_block.render_skill_block(entries)
        assert not_injected == []
        assert len(block) <= prompt_block.SKILL_INDEX_BUDGET
        names = [entry["name"] for entry in entries]
        assert [name for name in names if name not in block] == []
        # 前排是完整行（带描述），尾部只剩名字
        assert "- [我的] skill-00：《skill-00》——" in block
        assert "- [我的] skill-29" in block.splitlines()
        assert "——" not in "- [我的] skill-29"

    def test_overflow_lands_in_not_injected_not_swallowed(self) -> None:
        entries = [_skill(f"skill-{index:03d}", description=LONG_DESCRIPTION) for index in range(400)]
        block, not_injected = prompt_block.render_skill_block(entries)
        assert len(block) <= prompt_block.SKILL_INDEX_BUDGET
        assert not_injected
        injected = [line.split("] ", 1)[1].split("：", 1)[0] for line in block.splitlines() if line.startswith("- [")]
        # 注入的 + 未注入的 = 全部入参，且顺序一致（既没吞尾也没打乱优先级）
        assert injected + [entry["name"] for entry in not_injected] == [entry["name"] for entry in entries]

    def test_not_injected_carries_no_body(self) -> None:
        entries = [_skill(f"skill-{index:03d}", description=LONG_DESCRIPTION) for index in range(400)]
        _, not_injected = prompt_block.render_skill_block(entries)
        assert not_injected[0]["key"] and not_injected[0]["title"]
        assert all("body" not in entry for entry in not_injected)

    def test_order_is_input_order(self) -> None:
        entries = [_firm_skill(f"a{index}", scope="law_firm" if index % 2 else "team") for index in range(5)]
        block, _ = prompt_block.render_skill_block(entries)
        positions = [block.index(entry["name"]) for entry in entries]
        assert positions == sorted(positions)

    def test_budget_too_small_for_heading_injects_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(prompt_block, "SKILL_INDEX_BUDGET", 10)
        block, not_injected = prompt_block.render_skill_block([_skill("a"), _skill("b")])
        assert block == ""
        assert [entry["name"] for entry in not_injected] == ["a", "b"]


class TestSwitch:
    def test_env_off_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(prompt_block._USER_SKILLS_ENV, "off")
        assert prompt_block.render_skill_block([_skill("a")]) == ("", [])

    def test_env_dry_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``dry`` 与 ``on`` 等价但不注入提示块（只记日志）。"""
        monkeypatch.setenv(prompt_block._USER_SKILLS_ENV, "dry")
        assert prompt_block.render_skill_block([_skill("a")]) == ("", [])

    def test_env_on_injects(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(prompt_block._USER_SKILLS_ENV, "on")
        block, _ = prompt_block.render_skill_block([_skill("a")])
        assert block.startswith(prompt_block.BLOCK_HEADING)

    def test_flags_module_wins_when_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CORE lane 的 ``flags.prompt_block_enabled()`` 一旦就位就必须生效，环境变量退居兜底。"""
        monkeypatch.setenv(prompt_block._USER_SKILLS_ENV, "on")
        monkeypatch.setattr(prompt_block, "_flag_function", lambda name: lambda: False)
        assert prompt_block.render_skill_block([_skill("a")]) == ("", [])
