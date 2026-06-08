"""文本工具和 LLM 格式化器测试。"""

from __future__ import annotations

from apps.automation.utils.text_utils import TextUtils
from apps.wechat_mp.services.llm_formatter import _FORMATTING_SYSTEM_PROMPT


class TestTextUtils:
    """TextUtils 测试。"""

    def test_normalize_case_number_standard(self) -> None:
        """标准化案号。"""
        result = TextUtils.normalize_case_number("（2025）粤0604民初12345号")
        assert result == "（2025）粤0604民初12345号"

    def test_normalize_case_number_half_width_parens(self) -> None:
        """半角括号转全角。"""
        result = TextUtils.normalize_case_number("(2025)粤0604民初12345号")
        assert result.startswith("（")
        assert "）" in result

    def test_normalize_case_number_square_brackets(self) -> None:
        """方括号转全角括号。"""
        result = TextUtils.normalize_case_number("[2025]粤0604民初12345号")
        assert result.startswith("（")
        assert "）" in result

    def test_normalize_case_number_empty(self) -> None:
        """空案号。"""
        assert TextUtils.normalize_case_number("") == ""

    def test_normalize_case_number_add_hao(self) -> None:
        """自动补全"号"字。"""
        result = TextUtils.normalize_case_number("（2025）粤0604民初12345")
        assert result.endswith("号")

    def test_normalize_case_number_remove_spaces(self) -> None:
        """删除空格。"""
        result = TextUtils.normalize_case_number("（2025）粤 0604 民初 12345 号")
        assert " " not in result

    def test_clean_text_basic(self) -> None:
        """基本文本清洗。"""
        result = TextUtils.clean_text("  hello   world  ")
        assert result == "hello world"

    def test_clean_text_empty(self) -> None:
        """空文本。"""
        assert TextUtils.clean_text("") == ""

    def test_clean_text_control_chars(self) -> None:
        """删除控制字符。"""
        result = TextUtils.clean_text("hello\x00\x01world")
        assert result == "helloworld"

    def test_clean_text_newlines(self) -> None:
        """换行符替换为空格。"""
        result = TextUtils.clean_text("hello\nworld")
        assert result == "hello world"

    def test_extract_case_numbers_basic(self) -> None:
        """提取案号。"""
        text = "案号：（2025）粤0604民初12345号"
        result = TextUtils.extract_case_numbers(text)
        assert len(result) >= 1
        assert any("12345" in n for n in result)

    def test_extract_case_numbers_empty(self) -> None:
        """空文本。"""
        assert TextUtils.extract_case_numbers("") == []

    def test_extract_case_numbers_no_match(self) -> None:
        """无案号。"""
        result = TextUtils.extract_case_numbers("这是一段普通文本")
        assert result == []

    def test_case_number_pattern_match(self) -> None:
        """案号正则匹配。"""
        assert TextUtils.CASE_NUMBER_PATTERN.search("（2025）粤0604民初12345号") is not None
        assert TextUtils.CASE_NUMBER_PATTERN.search("普通文本") is None

    def test_date_pattern_match(self) -> None:
        """日期正则匹配。"""
        assert TextUtils.DATE_PATTERN.search("2025年1月1日") is not None
        assert TextUtils.DATE_PATTERN.search("2025年12月31号") is not None
        assert TextUtils.DATE_PATTERN.search("普通文本") is None


class TestLLMFormatterConstants:
    """LLM 格式化器常量测试。"""

    def test_system_prompt_not_empty(self) -> None:
        assert len(_FORMATTING_SYSTEM_PROMPT) > 0

    def test_system_prompt_contains_rules(self) -> None:
        assert "只输出 HTML" in _FORMATTING_SYSTEM_PROMPT
        assert "内联" in _FORMATTING_SYSTEM_PROMPT

    def test_system_prompt_contains_tags(self) -> None:
        assert "section" in _FORMATTING_SYSTEM_PROMPT
        assert "blockquote" in _FORMATTING_SYSTEM_PROMPT
