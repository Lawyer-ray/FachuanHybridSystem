"""Tests for apps/automation/services/ai/ai_service.py — AIService."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestAIService:
    """AIService.chat_with_llm 单元测试。"""

    def _make_service(self, llm_service: object | None = None):
        from apps.automation.services.ai.ai_service import AIService

        return AIService(llm_service=llm_service or MagicMock())

    def test_chat_with_llm_returns_dict(self) -> None:
        """返回字典包含 backend/model/content/raw 键（backend/model 来自 LLM 响应）。"""
        mock_llm = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = "AI response"
        mock_resp.backend = "openai_compatible"
        mock_resp.model = "kimi-2.6"
        mock_llm.chat.return_value = mock_resp

        svc = self._make_service(mock_llm)
        result = svc.chat_with_llm(model="kimi-2.6", prompt="你是助手", text="你好")

        assert result["backend"] == "openai_compatible"
        assert result["model"] == "kimi-2.6"
        assert result["content"] == "AI response"
        assert result["raw"]["message"]["content"] == "AI response"

    def test_chat_with_llm_passes_correct_messages(self) -> None:
        """传递给 llm_service.chat 的 messages 包含 system + user 两条；不再硬编码后端。"""
        mock_llm = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = "ok"
        mock_llm.chat.return_value = mock_resp

        svc = self._make_service(mock_llm)
        svc.chat_with_llm(model="m", prompt="sys_prompt", text="user_text")

        call_kwargs = mock_llm.chat.call_args[1]
        messages = call_kwargs["messages"]
        assert len(messages) == 2
        assert messages[0] == {"role": "system", "content": "sys_prompt"}
        assert messages[1] == {"role": "user", "content": "user_text"}
        assert call_kwargs["model"] == "m"
        assert "backend" not in call_kwargs
        assert "fallback" not in call_kwargs

    def test_chat_with_llm_different_models(self) -> None:
        """不同 model 参数都被正确传递。"""
        mock_llm = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = "r"
        mock_llm.chat.return_value = mock_resp

        svc = self._make_service(mock_llm)
        for model_name in ["qwen2:7b", "llama3", "deepseek-v2"]:
            mock_resp.model = model_name
            result = svc.chat_with_llm(model=model_name, prompt="p", text="t")
            assert result["model"] == model_name

    def test_init_stores_llm_service(self) -> None:
        """构造函数存储 llm_service。"""
        mock_llm = MagicMock()
        svc = self._make_service(mock_llm)
        assert svc._llm_service is mock_llm
