"""Tests for LLMConfig helpers and resolve_backend_for_model."""

from __future__ import annotations

import pytest
from unittest.mock import patch

from apps.core.llm.config import LLMConfig


# ---------------------------------------------------------------------------
# _parse_bool
# ---------------------------------------------------------------------------


class TestParseBool:
    def test_true_values(self):
        assert LLMConfig._parse_bool("true", False) is True
        assert LLMConfig._parse_bool("1", False) is True
        assert LLMConfig._parse_bool("yes", False) is True
        assert LLMConfig._parse_bool("y", False) is True
        assert LLMConfig._parse_bool("on", False) is True
        assert LLMConfig._parse_bool("TRUE", False) is True

    def test_false_values(self):
        assert LLMConfig._parse_bool("false", True) is False
        assert LLMConfig._parse_bool("0", True) is False
        assert LLMConfig._parse_bool("no", True) is False
        assert LLMConfig._parse_bool("n", True) is False
        assert LLMConfig._parse_bool("off", True) is False

    def test_empty_returns_default(self):
        assert LLMConfig._parse_bool("", True) is True
        assert LLMConfig._parse_bool("", False) is False

    def test_none_returns_default(self):
        assert LLMConfig._parse_bool(None, True) is True

    def test_bool_passthrough(self):
        assert LLMConfig._parse_bool(True, False) is True
        assert LLMConfig._parse_bool(False, True) is False

    def test_unknown_returns_default(self):
        assert LLMConfig._parse_bool("unknown", False) is False


# ---------------------------------------------------------------------------
# _parse_int
# ---------------------------------------------------------------------------


class TestParseInt:
    def test_valid(self):
        assert LLMConfig._parse_int("42", 0) == 42
        assert LLMConfig._parse_int(42, 0) == 42

    def test_empty(self):
        assert LLMConfig._parse_int("", 10) == 10

    def test_none(self):
        assert LLMConfig._parse_int(None, 10) == 10

    def test_invalid(self):
        assert LLMConfig._parse_int("abc", 10) == 10


# ---------------------------------------------------------------------------
# _normalize_api_key
# ---------------------------------------------------------------------------


class TestNormalizeApiKey:
    def test_strips_bearer(self):
        assert LLMConfig._normalize_api_key("Bearer sk-123") == "sk-123"

    def test_strips_whitespace(self):
        assert LLMConfig._normalize_api_key("  sk-123  ") == "sk-123"

    def test_empty(self):
        assert LLMConfig._normalize_api_key("") == ""

    def test_no_bearer(self):
        assert LLMConfig._normalize_api_key("sk-123") == "sk-123"


# ---------------------------------------------------------------------------
# _normalize_base_url
# ---------------------------------------------------------------------------


class TestNormalizeBaseUrl:
    def test_strip_trailing_slash(self):
        assert LLMConfig._normalize_base_url("http://localhost/") == "http://localhost"

    def test_strip_multiple_slashes(self):
        assert LLMConfig._normalize_base_url("http://localhost///") == "http://localhost"

    def test_no_trailing_slash(self):
        assert LLMConfig._normalize_base_url("http://localhost") == "http://localhost"

    def test_empty(self):
        assert LLMConfig._normalize_base_url("") == ""


# ---------------------------------------------------------------------------
# resolve_backend_for_model
# ---------------------------------------------------------------------------


class TestResolveBackendForModel:
    def test_ollama_model(self):
        assert LLMConfig.resolve_backend_for_model("qwen3:0.6b") == "ollama"

    def test_openai_compatible_model(self):
        assert LLMConfig.resolve_backend_for_model("kimi26") == "openai_compatible"

    def test_empty_model(self):
        with patch.object(LLMConfig, "get_default_backend", return_value="openai_compatible"):
            result = LLMConfig.resolve_backend_for_model("")
            assert result == "openai_compatible"
