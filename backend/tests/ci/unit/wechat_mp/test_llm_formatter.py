"""Tests for wechat_mp.services.llm_formatter."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.wechat_mp.services.llm_formatter import (
    _FORMATTING_SYSTEM_PROMPT,
    _build_user_prompt,
    llm_format_article,
)


class TestBuildUserPrompt:
    def test_auto_style(self) -> None:
        prompt = _build_user_prompt("# Hello", style="auto")
        assert "# Hello" in prompt
        assert "自动选择" in prompt

    def test_professional_style(self) -> None:
        prompt = _build_user_prompt("content", style="professional")
        assert "专业严肃" in prompt

    def test_creative_style(self) -> None:
        prompt = _build_user_prompt("content", style="creative")
        assert "创意活泼" in prompt

    def test_minimal_style(self) -> None:
        prompt = _build_user_prompt("content", style="minimal")
        assert "极简优雅" in prompt

    def test_colorful_style(self) -> None:
        prompt = _build_user_prompt("content", style="colorful")
        assert "色彩丰富" in prompt

    def test_unknown_style_defaults_to_auto(self) -> None:
        prompt = _build_user_prompt("content", style="unknown")
        assert "自动选择" in prompt

    def test_content_included(self) -> None:
        prompt = _build_user_prompt("这是测试内容", style="auto")
        assert "这是测试内容" in prompt


class TestFormattingSystemPrompt:
    def test_contains_rules(self) -> None:
        assert "只输出 HTML" in _FORMATTING_SYSTEM_PROMPT
        assert "内联" in _FORMATTING_SYSTEM_PROMPT

    def test_contains_layout_elements(self) -> None:
        assert "卡片" in _FORMATTING_SYSTEM_PROMPT
        assert "时间线" in _FORMATTING_SYSTEM_PROMPT


@pytest.mark.asyncio
class TestLlmFormatArticle:
    @patch("apps.core.llm.get_llm_service")
    async def test_success(self, mock_get_llm: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.content = '<section style="color:red"><p>Hello</p></section>'
        mock_response.model = "gpt-4"

        mock_service = MagicMock()
        mock_service.achat = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_service

        result = await llm_format_article("# Hello", style="auto")
        assert result is not None
        assert "<section" in result

    @patch("apps.core.llm.get_llm_service")
    async def test_strips_html_code_block(self, mock_get_llm: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.content = '```html\n<section><p>Content</p></section>\n```'
        mock_response.model = "gpt-4"

        mock_service = MagicMock()
        mock_service.achat = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_service

        result = await llm_format_article("content")
        assert result is not None
        assert "```" not in result

    @patch("apps.core.llm.get_llm_service")
    async def test_strips_generic_code_block(self, mock_get_llm: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.content = '```\n<section><p>Content</p></section>\n```'
        mock_response.model = "gpt-4"

        mock_service = MagicMock()
        mock_service.achat = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_service

        result = await llm_format_article("content")
        assert result is not None
        assert "<section" in result

    @patch("apps.core.llm.get_llm_service")
    async def test_invalid_output_retries(self, mock_get_llm: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.content = "just plain text, no HTML"
        mock_response.model = "gpt-4"

        mock_service = MagicMock()
        mock_service.achat = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_service

        result = await llm_format_article("content", max_retries=0)
        assert result is None

    @patch("apps.core.llm.get_llm_service")
    async def test_exception_returns_none(self, mock_get_llm: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.achat = AsyncMock(side_effect=Exception("LLM error"))
        mock_get_llm.return_value = mock_service

        result = await llm_format_article("content", max_retries=0)
        assert result is None

    @patch("apps.core.llm.get_llm_service")
    async def test_p_tag_validates(self, mock_get_llm: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.content = "<p>Simple paragraph</p>"
        mock_response.model = "gpt-4"

        mock_service = MagicMock()
        mock_service.achat = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_service

        result = await llm_format_article("content")
        assert result is not None

    @patch("apps.core.llm.get_llm_service")
    async def test_with_model_param(self, mock_get_llm: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.content = "<section><p>OK</p></section>"
        mock_response.model = "claude-3"

        mock_service = MagicMock()
        mock_service.achat = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_service

        result = await llm_format_article("content", model="claude-3")
        assert result is not None
