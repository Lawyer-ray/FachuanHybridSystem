"""ollama_protocol + http_error_summary 补充覆盖测试。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
import httpx

from apps.core.llm.exceptions import LLMAPIError


# ── build_ollama_chat_payload ─────────────────────────────────────

class TestBuildOllamaChatPayload:
    def test_basic_payload(self):
        from apps.core.llm.backends.ollama_protocol import build_ollama_chat_payload

        result = build_ollama_chat_payload(
            messages=[{"role": "user", "content": "Hi"}],
            model="llama3",
        )
        assert result["model"] == "llama3"
        assert result["stream"] is False
        assert "options" not in result
        assert "think" not in result

    def test_with_options(self):
        from apps.core.llm.backends.ollama_protocol import build_ollama_chat_payload

        result = build_ollama_chat_payload(
            messages=[{"role": "user", "content": "Hi"}],
            model="llama3",
            options={"temperature": 0.5},
        )
        assert result["options"] == {"temperature": 0.5}

    def test_with_think(self):
        from apps.core.llm.backends.ollama_protocol import build_ollama_chat_payload

        result = build_ollama_chat_payload(
            messages=[{"role": "user", "content": "Hi"}],
            model="qwq",
            think=True,
        )
        assert result["think"] is True

    def test_with_options_and_think(self):
        from apps.core.llm.backends.ollama_protocol import build_ollama_chat_payload

        result = build_ollama_chat_payload(
            messages=[{"role": "user", "content": "Hi"}],
            model="qwq",
            options={"num_predict": 100},
            think=True,
        )
        assert result["options"] == {"num_predict": 100}
        assert result["think"] is True


# ── parse_ollama_chat_response ────────────────────────────────────

class TestParseOllamaChatResponse:
    def test_valid_json(self):
        from apps.core.llm.backends.ollama_protocol import parse_ollama_chat_response

        resp = MagicMock()
        resp.json.return_value = {"message": {"content": "Hello"}}
        result = parse_ollama_chat_response(resp=resp, model="llama3")
        assert result["message"]["content"] == "Hello"

    def test_json_decode_error_with_valid_lines(self):
        from apps.core.llm.backends.ollama_protocol import parse_ollama_chat_response

        resp = MagicMock()
        resp.json.side_effect = json.JSONDecodeError("err", "", 0)
        resp.text = '{"message": {"content": "Line 1"}}\n{"message": {"content": "Line 2"}}'
        result = parse_ollama_chat_response(resp=resp, model="llama3")
        assert result["message"]["content"] == "Line 2"

    def test_json_decode_error_with_invalid_lines(self):
        from apps.core.llm.backends.ollama_protocol import parse_ollama_chat_response

        resp = MagicMock()
        resp.json.side_effect = json.JSONDecodeError("err", "", 0)
        resp.text = "not json\nalso not json"
        with pytest.raises(LLMAPIError):
            parse_ollama_chat_response(resp=resp, model="llama3")

    def test_json_decode_error_empty_response(self):
        from apps.core.llm.backends.ollama_protocol import parse_ollama_chat_response

        resp = MagicMock()
        resp.json.side_effect = json.JSONDecodeError("err", "", 0)
        resp.text = ""
        with pytest.raises(LLMAPIError):
            parse_ollama_chat_response(resp=resp, model="llama3")

    def test_json_decode_error_no_message_key(self):
        from apps.core.llm.backends.ollama_protocol import parse_ollama_chat_response

        resp = MagicMock()
        resp.json.side_effect = json.JSONDecodeError("err", "", 0)
        resp.text = '{"other_key": "value"}'
        with pytest.raises(LLMAPIError):
            parse_ollama_chat_response(resp=resp, model="llama3")

    def test_json_decode_error_mixed_valid_invalid(self):
        from apps.core.llm.backends.ollama_protocol import parse_ollama_chat_response

        resp = MagicMock()
        resp.json.side_effect = json.JSONDecodeError("err", "", 0)
        resp.text = 'not json\n{"message": {"content": "found"}}\nalso not json'
        result = parse_ollama_chat_response(resp=resp, model="llama3")
        assert result["message"]["content"] == "found"


# ── http_error_summary ────────────────────────────────────────────

class TestHttpErrorSummary:
    def test_summarize_http_error(self):
        from apps.core.llm.backends.http_error_summary import summarize_http_error_response

        resp = MagicMock()
        resp.status_code = 500
        resp.text = "Internal Server Error"
        resp.headers = {"content-type": "text/plain"}

        result = summarize_http_error_response(resp)
        assert isinstance(result, dict)
        assert "status_code" in result

    def test_summarize_with_json_body(self):
        from apps.core.llm.backends.http_error_summary import summarize_http_error_response

        resp = MagicMock()
        resp.status_code = 400
        resp.text = '{"error": "bad request"}'
        resp.headers = {"content-type": "application/json"}

        result = summarize_http_error_response(resp)
        assert isinstance(result, dict)


# ── LLMUsage ─────────────────────────────────────────────────────

class TestLLMUsage:
    def test_basic_usage(self):
        from apps.core.llm.backends.base import LLMUsage

        usage = LLMUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        assert usage.prompt_tokens == 10
        assert usage.completion_tokens == 5
        assert usage.total_tokens == 15


# ── LLMResponse ──────────────────────────────────────────────────

class TestLLMResponse:
    def test_basic_response(self):
        from apps.core.llm.backends.base import LLMResponse

        resp = LLMResponse(
            content="Hello",
            model="gpt-4o",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            duration_ms=100.0,
            backend="openai",
        )
        assert resp.content == "Hello"
        assert resp.model == "gpt-4o"


# ── LLMStreamChunk ────────────────────────────────────────────────

class TestLLMStreamChunk:
    def test_content_chunk(self):
        from apps.core.llm.backends.base import LLMStreamChunk

        chunk = LLMStreamChunk(content="Hello", model="gpt-4o", backend="openai")
        assert chunk.content == "Hello"
        assert chunk.usage is None

    def test_usage_chunk(self):
        from apps.core.llm.backends.base import LLMStreamChunk, LLMUsage

        usage = LLMUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        chunk = LLMStreamChunk(usage=usage, model="gpt-4o", backend="openai")
        assert chunk.usage is not None
        assert chunk.usage.prompt_tokens == 10
