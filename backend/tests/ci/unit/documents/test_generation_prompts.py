"""文档生成 prompts 和占位符服务测试。"""

from __future__ import annotations

from apps.documents.services.generation.prompts import (
    PromptSpec,
    _SafeDict,
    COMPLAINT_PROMPT,
    DEFENSE_PROMPT,
)


class TestSafeDict:
    """_SafeDict 测试。"""

    def test_missing_key_returns_fallback(self) -> None:
        d = _SafeDict({"a": "1"})
        assert d["a"] == "1"
        assert d["missing"] == "/"


class TestPromptSpec:
    """PromptSpec 测试。"""

    def test_render_user_message_basic(self) -> None:
        spec = PromptSpec(
            system_prompt="系统提示",
            user_template="姓名:{name}, 地址:{address}",
            format_instructions="",
        )
        result = spec.render_user_message({"name": "张三", "address": "北京"})
        assert "张三" in result
        assert "北京" in result

    def test_render_user_message_missing_key(self) -> None:
        spec = PromptSpec(
            system_prompt="系统提示",
            user_template="姓名:{name}, 地址:{address}",
            format_instructions="",
        )
        result = spec.render_user_message({"name": "张三"})
        assert "张三" in result
        # 缺失的 address 应该被替换为兜底值
        assert "/" in result

    def test_render_user_message_none_value(self) -> None:
        spec = PromptSpec(
            system_prompt="系统提示",
            user_template="姓名:{name}",
            format_instructions="",
        )
        result = spec.render_user_message({"name": None})
        assert "/" in result

    def test_render_user_message_empty_values(self) -> None:
        spec = PromptSpec(
            system_prompt="系统提示",
            user_template="姓名:{name}",
            format_instructions="",
        )
        result = spec.render_user_message({})
        assert "/" in result

    def test_format_instructions_default(self) -> None:
        spec = PromptSpec(
            system_prompt="系统提示",
            user_template="内容:{format_instructions}",
            format_instructions="请使用JSON格式",
        )
        result = spec.render_user_message({})
        assert "请使用JSON格式" in result

    def test_complaint_prompt(self) -> None:
        """起诉状提示词。"""
        assert "起诉状" in COMPLAINT_PROMPT.user_template
        assert "cause_of_action" in COMPLAINT_PROMPT.user_template
        assert "plaintiff" in COMPLAINT_PROMPT.user_template
        assert "defendant" in COMPLAINT_PROMPT.user_template

    def test_defense_prompt(self) -> None:
        """答辩状提示词。"""
        assert "答辩状" in DEFENSE_PROMPT.user_template
        assert "defense_opinion" in DEFENSE_PROMPT.user_template

    def test_prompt_spec_frozen(self) -> None:
        """PromptSpec 是不可变的。"""
        spec = PromptSpec(
            system_prompt="test",
            user_template="test",
            format_instructions="test",
        )
        try:
            spec.system_prompt = "changed"  # type: ignore
            raise AssertionError("应抛出异常")
        except AttributeError:
            pass
