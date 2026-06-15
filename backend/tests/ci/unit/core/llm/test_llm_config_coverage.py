"""Tests for apps.core.llm.config — LLMConfig (sync methods + helpers)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.llm.config import LLMConfig


class TestNormalizeApiKey:
    def test_empty(self):
        assert LLMConfig._normalize_api_key("") == ""

    def test_none(self):
        assert LLMConfig._normalize_api_key(None) == ""

    def test_bearer_prefix_stripped(self):
        assert LLMConfig._normalize_api_key("Bearer sk-abc") == "sk-abc"

    def test_bearer_lowercase(self):
        assert LLMConfig._normalize_api_key("bearer sk-xyz") == "sk-xyz"

    def test_no_bearer(self):
        assert LLMConfig._normalize_api_key("sk-plain") == "sk-plain"

    def test_whitespace(self):
        assert LLMConfig._normalize_api_key("  sk-x  ") == "sk-x"


class TestNormalizeBaseUrl:
    def test_empty(self):
        assert LLMConfig._normalize_base_url("") == ""

    def test_none(self):
        assert LLMConfig._normalize_base_url(None) == ""

    def test_strip_trailing_slashes(self):
        assert LLMConfig._normalize_base_url("http://x.com///") == "http://x.com"

    def test_no_trailing_slash(self):
        assert LLMConfig._normalize_base_url("http://x.com") == "http://x.com"

    def test_whitespace(self):
        assert LLMConfig._normalize_base_url("  http://x.com/  ") == "http://x.com"


class TestGetOllamaModel:
    def test_from_system_config(self):
        with patch.object(LLMConfig, "_get_system_config", return_value="custom:model"):
            assert LLMConfig.get_ollama_model() == "custom:model"

    def test_fallback_default(self):
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            result = LLMConfig.get_ollama_model()
            assert result == LLMConfig.DEFAULT_OLLAMA_MODEL


class TestGetOllamaBaseUrl:
    def test_from_system_config(self):
        with patch.object(LLMConfig, "_get_system_config", return_value="http://custom:11434"):
            assert LLMConfig.get_ollama_base_url() == "http://custom:11434"

    def test_fallback_default(self):
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            assert LLMConfig.get_ollama_base_url() == LLMConfig.DEFAULT_OLLAMA_BASE_URL


class TestGetOllamaTimeout:
    def test_from_system_config(self):
        with patch.object(LLMConfig, "_get_system_config", return_value="600"):
            assert LLMConfig.get_ollama_timeout() == 600

    def test_invalid_value(self):
        with patch.object(LLMConfig, "_get_system_config", return_value="not_a_number"):
            assert LLMConfig.get_ollama_timeout() == LLMConfig.DEFAULT_OLLAMA_TIMEOUT

    def test_empty_value(self):
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            assert LLMConfig.get_ollama_timeout() == LLMConfig.DEFAULT_OLLAMA_TIMEOUT


class TestGetOllamaEmbeddingModel:
    def test_from_system_config(self):
        with patch.object(LLMConfig, "_get_system_config", return_value="emb-model"):
            assert LLMConfig.get_ollama_embedding_model() == "emb-model"

    def test_fallback_to_ollama_model(self):
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            with patch.object(LLMConfig, "get_ollama_model", return_value="fallback-m"):
                assert LLMConfig.get_ollama_embedding_model() == "fallback-m"


class TestGetOpenAICompatibleApiKey:
    def test_from_system_config(self):
        with patch.object(LLMConfig, "_get_system_config", return_value="Bearer sk-test"):
            assert LLMConfig.get_openai_compatible_api_key() == "sk-test"


class TestGetOpenAICompatibleBaseUrl:
    def test_from_system_config(self):
        with patch.object(LLMConfig, "_get_system_config", return_value="http://custom/v1/"):
            assert LLMConfig.get_openai_compatible_base_url() == "http://custom/v1"

    def test_fallback_default(self):
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            assert LLMConfig.get_openai_compatible_base_url() == LLMConfig.DEFAULT_OPENAI_COMPATIBLE_BASE_URL


class TestGetOpenAICompatibleModel:
    def test_from_system_config(self):
        with patch.object(LLMConfig, "_get_system_config", return_value="custom-model"):
            assert LLMConfig.get_openai_compatible_model() == "custom-model"

    def test_fallback_default(self):
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            assert LLMConfig.get_openai_compatible_model() == LLMConfig.DEFAULT_OPENAI_COMPATIBLE_MODEL

    def test_whitespace_only(self):
        with patch.object(LLMConfig, "_get_system_config", return_value="   "):
            assert LLMConfig.get_openai_compatible_model() == LLMConfig.DEFAULT_OPENAI_COMPATIBLE_MODEL


class TestGetOpenAICompatibleEmbeddingModel:
    def test_from_system_config(self):
        with patch.object(LLMConfig, "_get_system_config", return_value="emb-oc"):
            assert LLMConfig.get_openai_compatible_embedding_model() == "emb-oc"

    def test_fallback_to_oc_model(self):
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            with patch.object(LLMConfig, "get_openai_compatible_model", return_value="fallback"):
                assert LLMConfig.get_openai_compatible_embedding_model() == "fallback"


class TestGetOpenAICompatibleTimeout:
    def test_from_system_config(self):
        with patch.object(LLMConfig, "_get_system_config", return_value="90"):
            assert LLMConfig.get_openai_compatible_timeout() == 90

    def test_empty_value(self):
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            assert LLMConfig.get_openai_compatible_timeout() == LLMConfig.DEFAULT_OPENAI_COMPATIBLE_TIMEOUT

    def test_invalid_value(self):
        with patch.object(LLMConfig, "_get_system_config", return_value="abc"):
            assert LLMConfig.get_openai_compatible_timeout() == LLMConfig.DEFAULT_OPENAI_COMPATIBLE_TIMEOUT


class TestGetDefaultBackend:
    def test_from_system_config(self):
        with patch.object(LLMConfig, "_get_system_config", return_value="ollama"):
            assert LLMConfig.get_default_backend() == "ollama"

    def test_invalid_value_falls_back(self):
        with patch.object(LLMConfig, "_get_system_config", return_value="invalid"):
            assert LLMConfig.get_default_backend() == "openai_compatible"

    def test_empty_value(self):
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            assert LLMConfig.get_default_backend() == "openai_compatible"


class TestResolveBackendForModel:
    def test_empty_model(self):
        with patch.object(LLMConfig, "get_default_backend", return_value="def"):
            assert LLMConfig.resolve_backend_for_model("") == "def"

    def test_ollama_model(self):
        assert LLMConfig.resolve_backend_for_model("qwen3:0.6b") == "ollama"

    def test_openai_model(self):
        assert LLMConfig.resolve_backend_for_model("kimi26") == "openai_compatible"


class TestGetTemperature:
    def test_from_config(self):
        with patch.object(LLMConfig, "_get_system_config", return_value="0.7"):
            assert LLMConfig.get_temperature() == 0.7

    def test_invalid(self):
        with patch.object(LLMConfig, "_get_system_config", return_value="bad"):
            assert LLMConfig.get_temperature() == 0.3


class TestGetMaxTokens:
    def test_from_config(self):
        with patch.object(LLMConfig, "_get_system_config", return_value="4096"):
            assert LLMConfig.get_max_tokens() == 4096

    def test_invalid(self):
        with patch.object(LLMConfig, "_get_system_config", return_value="bad"):
            assert LLMConfig.get_max_tokens() == 2000


class TestParseBool:
    def test_bool_passthrough(self):
        assert LLMConfig._parse_bool(True, False) is True
        assert LLMConfig._parse_bool(False, True) is False

    def test_empty(self):
        assert LLMConfig._parse_bool("", True) is True

    def test_truthy_strings(self):
        for v in ("1", "true", "yes", "y", "on", "TRUE", "Yes"):
            assert LLMConfig._parse_bool(v, False) is True

    def test_falsy_strings(self):
        for v in ("0", "false", "no", "n", "off", "FALSE"):
            assert LLMConfig._parse_bool(v, True) is False

    def test_unknown_string_returns_default(self):
        assert LLMConfig._parse_bool("maybe", True) is True


class TestParseInt:
    def test_valid(self):
        assert LLMConfig._parse_int("42", 0) == 42

    def test_none(self):
        assert LLMConfig._parse_int(None, 10) == 10

    def test_empty(self):
        assert LLMConfig._parse_int("", 5) == 5

    def test_invalid(self):
        assert LLMConfig._parse_int("abc", 7) == 7


class TestGetBackendConfigs:
    def test_returns_dict(self):
        with patch.object(LLMConfig, "_get_system_config", return_value=""), \
             patch.object(LLMConfig, "get_ollama_model", return_value="qwen3:0.6b"), \
             patch.object(LLMConfig, "get_ollama_base_url", return_value="http://localhost:11434"), \
             patch.object(LLMConfig, "get_ollama_timeout", return_value=300), \
             patch.object(LLMConfig, "get_ollama_embedding_model", return_value="emb"), \
             patch.object(LLMConfig, "get_openai_compatible_model", return_value="kimi26"), \
             patch.object(LLMConfig, "get_openai_compatible_base_url", return_value="http://x"), \
             patch.object(LLMConfig, "get_openai_compatible_api_key", return_value=""), \
             patch.object(LLMConfig, "get_openai_compatible_timeout", return_value=120), \
             patch.object(LLMConfig, "get_openai_compatible_embedding_model", return_value="emb2"):
            result = LLMConfig.get_backend_configs()
            assert "ollama" in result
            assert "openai_compatible" in result
            assert result["ollama"].enabled is True
            assert result["openai_compatible"].enabled is True

    def test_oc_auto_enabled_when_base_url_set(self):
        """openai_compatible auto-enables when base_url is set but enabled not explicitly."""
        def fake_get_config(key: str, default: str = "") -> str:
            mapping = {
                "LLM_BACKEND_OLLAMA_ENABLED": "false",
                "LLM_BACKEND_OLLAMA_PRIORITY": "2",
                "LLM_BACKEND_OPENAI_COMPATIBLE_ENABLED": "",
                "LLM_BACKEND_OPENAI_COMPATIBLE_PRIORITY": "1",
                "OPENAI_COMPATIBLE_BASE_URL": "http://custom-v1",
            }
            return mapping.get(key, default)

        with patch.object(LLMConfig, "_get_system_config", side_effect=fake_get_config), \
             patch.object(LLMConfig, "get_ollama_model", return_value="m"), \
             patch.object(LLMConfig, "get_ollama_base_url", return_value=""), \
             patch.object(LLMConfig, "get_ollama_timeout", return_value=300), \
             patch.object(LLMConfig, "get_ollama_embedding_model", return_value=""), \
             patch.object(LLMConfig, "get_openai_compatible_model", return_value="kimi"), \
             patch.object(LLMConfig, "get_openai_compatible_base_url", return_value="http://custom-v1"), \
             patch.object(LLMConfig, "get_openai_compatible_api_key", return_value=""), \
             patch.object(LLMConfig, "get_openai_compatible_timeout", return_value=120), \
             patch.object(LLMConfig, "get_openai_compatible_embedding_model", return_value=""):
            result = LLMConfig.get_backend_configs()
            assert result["ollama"].enabled is False
            assert result["openai_compatible"].enabled is True
