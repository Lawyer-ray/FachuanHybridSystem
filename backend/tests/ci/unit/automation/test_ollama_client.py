"""Tests for apps/automation/services/ai/ollama_client.py — chat() function."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestOllamaClientChat:
    """ollama_client.chat() 单元测试。"""

    @patch("apps.automation.services.ai.ollama_client.ServiceLocator")
    def test_chat_returns_expected_dict(self, mock_locator: MagicMock) -> None:
        """chat() 返回包含 model/message/backend/prompt_eval_count/eval_count 的字典。"""
        mock_llm = MagicMock()
        mock_resp = MagicMock()
        mock_resp.model = "qwen2:7b"
        mock_resp.content = "Hello there"
        mock_resp.backend = "ollama"
        mock_resp.prompt_tokens = 15
        mock_resp.completion_tokens = 8
        mock_llm.chat.return_value = mock_resp
        mock_locator.get_llm_service.return_value = mock_llm

        from apps.automation.services.ai.ollama_client import chat

        result = chat(model="qwen2:7b", messages=[{"role": "user", "content": "hi"}])

        assert result["model"] == "qwen2:7b"
        assert result["message"]["content"] == "Hello there"
        assert result["backend"] == "ollama"
        assert result["prompt_eval_count"] == 15
        assert result["eval_count"] == 8

    @patch("apps.automation.services.ai.ollama_client.ServiceLocator")
    def test_chat_passes_correct_params(self, mock_locator: MagicMock) -> None:
        """chat() 正确传递 model、messages、backend=ollama、fallback=False。"""
        mock_llm = MagicMock()
        mock_resp = MagicMock()
        mock_resp.model = "m"
        mock_resp.content = "c"
        mock_resp.backend = "ollama"
        mock_resp.prompt_tokens = 0
        mock_resp.completion_tokens = 0
        mock_llm.chat.return_value = mock_resp
        mock_locator.get_llm_service.return_value = mock_llm

        from apps.automation.services.ai.ollama_client import chat

        messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}]
        chat(model="llama3", messages=messages, base_url="http://ignored")

        mock_llm.chat.assert_called_once_with(
            messages=messages, backend="ollama", model="llama3", fallback=False
        )

    @patch("apps.automation.services.ai.ollama_client.ServiceLocator")
    def test_chat_ignores_base_url(self, mock_locator: MagicMock) -> None:
        """base_url 参数被保留但不使用（兼容旧接口）。"""
        mock_llm = MagicMock()
        mock_resp = MagicMock()
        mock_resp.model = "m"
        mock_resp.content = "c"
        mock_resp.backend = "ollama"
        mock_resp.prompt_tokens = 0
        mock_resp.completion_tokens = 0
        mock_llm.chat.return_value = mock_resp
        mock_locator.get_llm_service.return_value = mock_llm

        from apps.automation.services.ai.ollama_client import chat

        # Should not raise even with base_url
        result = chat(model="m", messages=[], base_url="http://whatever:11434")
        assert "model" in result

    @patch("apps.automation.services.ai.ollama_client.ServiceLocator")
    def test_chat_empty_messages(self, mock_locator: MagicMock) -> None:
        """空消息列表也能正常工作。"""
        mock_llm = MagicMock()
        mock_resp = MagicMock()
        mock_resp.model = "m"
        mock_resp.content = ""
        mock_resp.backend = "ollama"
        mock_resp.prompt_tokens = 0
        mock_resp.completion_tokens = 0
        mock_llm.chat.return_value = mock_resp
        mock_locator.get_llm_service.return_value = mock_llm

        from apps.automation.services.ai.ollama_client import chat

        result = chat(model="m", messages=[])
        assert result["message"]["content"] == ""
