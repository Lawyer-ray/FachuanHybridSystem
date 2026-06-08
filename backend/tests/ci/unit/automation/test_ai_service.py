"""Tests for apps/automation/services/ai/ai_service.py — AIService."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestAIService:
    """AIService.chat_with_ollama 单元测试。"""

    def _make_service(self, llm_service: object | None = None):
        from apps.automation.services.ai.ai_service import AIService

        return AIService(llm_service=llm_service or MagicMock())

    def test_chat_with_ollama_returns_dict(self) -> None:
        """返回字典包含 backend/model/content/raw 键。"""
        mock_llm = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = "AI response"
        mock_llm.chat.return_value = mock_resp

        svc = self._make_service(mock_llm)
        result = svc.chat_with_ollama(model="qwen2", prompt="你是助手", text="你好")

        assert result["backend"] == "ollama"
        assert result["model"] == "qwen2"
        assert result["content"] == "AI response"
        assert result["raw"]["message"]["content"] == "AI response"

    def test_chat_with_ollama_passes_correct_messages(self) -> None:
        """传递给 llm_service.chat 的 messages 包含 system + user 两条。"""
        mock_llm = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = "ok"
        mock_llm.chat.return_value = mock_resp

        svc = self._make_service(mock_llm)
        svc.chat_with_ollama(model="m", prompt="sys_prompt", text="user_text")

        call_kwargs = mock_llm.chat.call_args[1]
        messages = call_kwargs["messages"]
        assert len(messages) == 2
        assert messages[0] == {"role": "system", "content": "sys_prompt"}
        assert messages[1] == {"role": "user", "content": "user_text"}
        assert call_kwargs["backend"] == "ollama"
        assert call_kwargs["model"] == "m"
        assert call_kwargs["fallback"] is False

    def test_chat_with_ollama_different_models(self) -> None:
        """不同 model 参数都被正确传递。"""
        mock_llm = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = "r"
        mock_llm.chat.return_value = mock_resp

        svc = self._make_service(mock_llm)
        for model_name in ["qwen2:7b", "llama3", "deepseek-v2"]:
            result = svc.chat_with_ollama(model=model_name, prompt="p", text="t")
            assert result["model"] == model_name

    def test_init_stores_llm_service(self) -> None:
        """构造函数存储 llm_service。"""
        mock_llm = MagicMock()
        svc = self._make_service(mock_llm)
        assert svc._llm_service is mock_llm
