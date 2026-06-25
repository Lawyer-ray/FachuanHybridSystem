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
