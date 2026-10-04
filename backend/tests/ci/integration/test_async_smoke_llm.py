"""Smoke tests for async LLM chat endpoint."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.django_db
class TestLLMChatSmoke:
    def test_chat_endpoint_exists(self, authenticated_client):
        """The LLM chat endpoint should be reachable."""
        resp = authenticated_client.post(
            "/api/v1/llm/chat",
            data=json.dumps({"message": "你好"}),
            content_type="application/json",
        )
        # Should return 200 or 401 (if auth not properly set up in test)
        # but NOT 404 (endpoint must exist)
        assert resp.status_code != 404, "LLM chat endpoint should exist"
        # 路由已注册且响应为 JSON：成功须带会话标识，失败须带错误信封
        body = resp.json()
        if resp.status_code == 200:
            assert body["response"] is not None
            assert body["session_id"]
        else:
            assert body["code"], "非 200 响应必须携带错误码信封"
            assert body["message"]
