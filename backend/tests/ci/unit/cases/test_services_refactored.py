"""Tests for refactored pure functions from cases/services/."""

from __future__ import annotations

import pytest

from apps.cases.services.chat.chat_name_config_service import ChatNameConfigService


class TestChatNameConfigServiceConstants:
    """Tests for ChatNameConfigService constants."""

    def test_config_key_template(self):
        assert ChatNameConfigService.CONFIG_KEY_TEMPLATE == "CASE_CHAT_NAME_TEMPLATE"

    def test_config_key_default_stage(self):
        assert ChatNameConfigService.CONFIG_KEY_DEFAULT_STAGE == "CASE_CHAT_DEFAULT_STAGE"

    def test_default_template(self):
        assert ChatNameConfigService.DEFAULT_TEMPLATE == "【{stage}】{case_name}"

    def test_default_stage(self):
        assert ChatNameConfigService.DEFAULT_STAGE == "待定"

    def test_default_max_length(self):
        assert ChatNameConfigService.DEFAULT_MAX_LENGTH == 60

    def test_valid_placeholders(self):
        assert "stage" in ChatNameConfigService.VALID_PLACEHOLDERS
        assert "case_name" in ChatNameConfigService.VALID_PLACEHOLDERS
        assert "case_type" in ChatNameConfigService.VALID_PLACEHOLDERS


class TestRenderTemplate:
    """Tests for _render_template method."""

    def setup_method(self):
        self.service = ChatNameConfigService()

    def test_basic_render(self):
        result = self.service._render_template("【{stage}】{case_name}", "一审", "Test案", "")
        assert result == "【一审】Test案"

    def test_with_case_type(self):
        result = self.service._render_template("{case_name} - {case_type}", "一审", "Test案", "合同纠纷")
        assert result == "Test案 - 合同纠纷"

    def test_empty_stage(self):
        result = self.service._render_template("【{stage}】{case_name}", "", "Test案", "")
        assert result == "【】Test案"

    def test_empty_case_name(self):
        result = self.service._render_template("【{stage}】{case_name}", "一审", "", "")
        assert result == "【一审】"

    def test_no_placeholders(self):
        result = self.service._render_template("plain text", "一审", "Test案", "")
        assert result == "plain text"

    def test_invalid_placeholder_preserved(self):
        result = self.service._render_template("{invalid}", "一审", "Test案", "")
        assert result == "{invalid}"

    def test_multiple_same_placeholder(self):
        result = self.service._render_template("{case_name} vs {case_name}", "一审", "A", "")
        assert result == "A vs A"


class TestTruncateChatName:
    """Tests for _truncate_chat_name method."""

    def setup_method(self):
        self.service = ChatNameConfigService()

    def test_no_truncation_needed(self):
        # Note: _truncate_chat_name always adds ellipsis, it's called when truncation is needed
        result = self.service._truncate_chat_name("【一审】Test案", 60, "【{stage}】{case_name}", "一审", "Test案", "")
        assert "【一审】" in result

    def test_truncate_with_stage_prefix(self):
        long_name = "【一审】" + "A" * 100
        result = self.service._truncate_chat_name(long_name, 60, "【{stage}】{case_name}", "一审", "A" * 100, "")
        assert len(result) <= 60
        assert result.startswith("【一审】")
        assert result.endswith("...")

    def test_truncate_without_stage_prefix(self):
        long_name = "A" * 100
        result = self.service._truncate_chat_name(long_name, 60, "{case_name}", "一审", "A" * 100, "")
        assert len(result) <= 60
        assert result.endswith("...")

    def test_stage_prefix_exceeds_max_length(self):
        long_stage = "A" * 70
        long_name = f"【{long_stage}】Test案"
        result = self.service._truncate_chat_name(long_name, 60, "【{stage}】{case_name}", long_stage, "Test案", "")
        assert len(result) <= 60
        assert result.endswith("...")


class TestGetMaxLength:
    """Tests for get_max_length method."""

    def setup_method(self):
        self.service = ChatNameConfigService()

    def test_returns_60(self):
        assert self.service.get_max_length() == 60
