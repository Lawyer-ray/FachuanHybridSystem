"""Tests for core.llm.backends.ollama_protocol."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from apps.core.llm.backends.ollama_protocol import (
    build_ollama_chat_payload,
    parse_ollama_chat_response,
)
from apps.core.llm.exceptions import LLMAPIError


class TestBuildOllamaChatPayload:
    def test_basic(self) -> None:
        result = build_ollama_chat_payload(
            messages=[{"role": "user", "content": "hello"}],
            model="qwen3:0.6b",
        )
        assert result["model"] == "qwen3:0.6b"
        assert result["messages"] == [{"role": "user", "content": "hello"}]
        assert result["stream"] is False
        assert "options" not in result
        assert "think" not in result

    def test_with_options(self) -> None:
        options = {"temperature": 0.5, "num_predict": 100}
        result = build_ollama_chat_payload(
            messages=[{"role": "user", "content": "hi"}],
            model="m",
            options=options,
        )
        assert result["options"] == options

    def test_with_think(self) -> None:
        result = build_ollama_chat_payload(
            messages=[{"role": "user", "content": "hi"}],
            model="m",
            think=True,
        )
        assert result["think"] is True

    def test_think_none_excluded(self) -> None:
        result = build_ollama_chat_payload(
            messages=[{"role": "user", "content": "hi"}],
            model="m",
            think=None,
        )
        assert "think" not in result

    def test_empty_options_excluded(self) -> None:
        result = build_ollama_chat_payload(
            messages=[{"role": "user", "content": "hi"}],
            model="m",
            options=None,
        )
        assert "options" not in result


class TestParseOllamaChatResponse:
    def test_valid_json(self) -> None:
        resp = MagicMock()
        resp.json.return_value = {"message": {"content": "hello"}, "done": True}
        result = parse_ollama_chat_response(resp=resp, model="m")
        assert result["message"]["content"] == "hello"

    def test_json_decode_error_with_valid_lines(self) -> None:
        resp = MagicMock()
        resp.json.side_effect = json.JSONDecodeError("", "", 0)
        resp.text = '{"message": {"content": "line1"}}\n{"message": {"content": "line2"}}'
        result = parse_ollama_chat_response(resp=resp, model="m")
        assert result["message"]["content"] == "line2"

    def test_json_decode_error_no_valid_lines(self) -> None:
        resp = MagicMock()
        resp.json.side_effect = json.JSONDecodeError("", "", 0)
        resp.text = "not json at all"
        with pytest.raises(LLMAPIError, match="无法解析"):
            parse_ollama_chat_response(resp=resp, model="m")

    def test_json_decode_error_empty_text(self) -> None:
        resp = MagicMock()
        resp.json.side_effect = json.JSONDecodeError("", "", 0)
        resp.text = ""
        with pytest.raises(LLMAPIError):
            parse_ollama_chat_response(resp=resp, model="m")

    def test_json_decode_error_with_mixed_lines(self) -> None:
        resp = MagicMock()
        resp.json.side_effect = json.JSONDecodeError("", "", 0)
        resp.text = 'not json\n{"message": {"content": "ok"}}\nalso not json'
        result = parse_ollama_chat_response(resp=resp, model="m")
        assert result["message"]["content"] == "ok"

    def test_json_decode_error_no_message_key(self) -> None:
        resp = MagicMock()
        resp.json.side_effect = json.JSONDecodeError("", "", 0)
        resp.text = '{"done": true}'
        with pytest.raises(LLMAPIError):
            parse_ollama_chat_response(resp=resp, model="m")
