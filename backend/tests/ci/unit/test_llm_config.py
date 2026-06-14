"""Tests for apps.core.llm.config — LLMConfig class."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest


@pytest.fixture(autouse=True)
def _clear_cache():
    """Reset LLMConfig caches between tests."""
    from apps.core.llm.config import LLMConfig
    LLMConfig._config_cache.clear()
    LLMConfig._config_service = None
    yield
    LLMConfig._config_cache.clear()
    LLMConfig._config_service = None


class TestLLMConfigParseBool:
    def test_true_values(self):
        from apps.core.llm.config import LLMConfig
        for v in [True, "1", "true", "yes", "y", "on", "True", "YES"]:
            assert LLMConfig._parse_bool(v, False) is True

    def test_false_values(self):
        from apps.core.llm.config import LLMConfig
        for v in ["0", "false", "no", "n", "off", "False"]:
            assert LLMConfig._parse_bool(v, True) is False

    def test_none_returns_default(self):
        from apps.core.llm.config import LLMConfig
        assert LLMConfig._parse_bool(None, True) is True

    def test_empty_string_returns_default(self):
        from apps.core.llm.config import LLMConfig
        assert LLMConfig._parse_bool("", False) is False

    def test_unknown_returns_default(self):
        from apps.core.llm.config import LLMConfig
        assert LLMConfig._parse_bool("maybe", True) is True


class TestLLMConfigParseInt:
    def test_valid(self):
        from apps.core.llm.config import LLMConfig
        assert LLMConfig._parse_int("42", 0) == 42

    def test_none_returns_default(self):
        from apps.core.llm.config import LLMConfig
        assert LLMConfig._parse_int(None, 99) == 99

    def test_empty_returns_default(self):
        from apps.core.llm.config import LLMConfig
        assert LLMConfig._parse_int("", 99) == 99

    def test_invalid_returns_default(self):
        from apps.core.llm.config import LLMConfig
        assert LLMConfig._parse_int("abc", 99) == 99


class TestLLMConfigNormalize:
    def test_normalize_api_key_strip(self):
        from apps.core.llm.config import LLMConfig
        assert LLMConfig._normalize_api_key("  sk-123  ") == "sk-123"

    def test_normalize_api_key_bearer_prefix(self):
        from apps.core.llm.config import LLMConfig
        assert LLMConfig._normalize_api_key("Bearer sk-123") == "sk-123"

    def test_normalize_base_url_strip_slash(self):
        from apps.core.llm.config import LLMConfig
        assert LLMConfig._normalize_base_url("http://example.com/") == "http://example.com"

    def test_normalize_base_url_multiple_slashes(self):
        from apps.core.llm.config import LLMConfig
        assert LLMConfig._normalize_base_url("http://example.com///") == "http://example.com"


class TestLLMConfigResolveBackend:
    def test_ollama_model(self):
        from apps.core.llm.config import LLMConfig
        assert LLMConfig.resolve_backend_for_model("qwen3:0.6b") == "ollama"

    def test_openai_model(self):
        from apps.core.llm.config import LLMConfig
        assert LLMConfig.resolve_backend_for_model("kimi26") == "openai_compatible"

    def test_empty_model_uses_default(self):
        from apps.core.llm.config import LLMConfig
        with patch.object(LLMConfig, "get_default_backend", return_value="ollama"):
            assert LLMConfig.resolve_backend_for_model("") == "ollama"


class TestLLMConfigGetTemperature:
    def test_default(self):
        from apps.core.llm.config import LLMConfig
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            assert LLMConfig.get_temperature() == 0.3

    def test_custom(self):
        from apps.core.llm.config import LLMConfig
        with patch.object(LLMConfig, "_get_system_config", return_value="0.7"):
            assert LLMConfig.get_temperature() == 0.7

    def test_invalid(self):
        from apps.core.llm.config import LLMConfig
        with patch.object(LLMConfig, "_get_system_config", return_value="abc"):
            assert LLMConfig.get_temperature() == 0.3


class TestLLMConfigGetMaxTokens:
    def test_default(self):
        from apps.core.llm.config import LLMConfig
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            assert LLMConfig.get_max_tokens() == 2000

    def test_custom(self):
        from apps.core.llm.config import LLMConfig
        with patch.object(LLMConfig, "_get_system_config", return_value="4096"):
            assert LLMConfig.get_max_tokens() == 4096


class TestLLMConfigDefaults:
    def test_ollama_model_default(self):
        from apps.core.llm.config import LLMConfig
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            with patch("apps.core.llm.config.settings") as mock_s:
                mock_s.OLLAMA = {}
                assert LLMConfig.get_ollama_model() == LLMConfig.DEFAULT_OLLAMA_MODEL

    def test_ollama_model_from_settings(self):
        from apps.core.llm.config import LLMConfig
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            with patch("apps.core.llm.config.settings") as mock_s:
                mock_s.OLLAMA = {"MODEL": "custom_model"}
                assert LLMConfig.get_ollama_model() == "custom_model"

    def test_ollama_base_url_default(self):
        from apps.core.llm.config import LLMConfig
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            with patch("apps.core.llm.config.settings") as mock_s:
                mock_s.OLLAMA = {}
                assert LLMConfig.get_ollama_base_url() == LLMConfig.DEFAULT_OLLAMA_BASE_URL

    def test_ollama_timeout_invalid_fallback(self):
        from apps.core.llm.config import LLMConfig
        with patch.object(LLMConfig, "_get_system_config", return_value="abc"):
            assert LLMConfig.get_ollama_timeout() == LLMConfig.DEFAULT_OLLAMA_TIMEOUT

    def test_openai_compatible_timeout_invalid(self):
        from apps.core.llm.config import LLMConfig
        with patch.object(LLMConfig, "_get_system_config", return_value="abc"):
            assert LLMConfig.get_openai_compatible_timeout() == LLMConfig.DEFAULT_OPENAI_COMPATIBLE_TIMEOUT

    def test_openai_compatible_model_default(self):
        from apps.core.llm.config import LLMConfig
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            assert LLMConfig.get_openai_compatible_model() == LLMConfig.DEFAULT_OPENAI_COMPATIBLE_MODEL

    def test_openai_compatible_base_url_default(self):
        from apps.core.llm.config import LLMConfig
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            assert LLMConfig.get_openai_compatible_base_url() == LLMConfig.DEFAULT_OPENAI_COMPATIBLE_BASE_URL

    def test_ollama_embedding_model_fallback_to_model(self):
        from apps.core.llm.config import LLMConfig
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            with patch("apps.core.llm.config.settings") as mock_s:
                mock_s.OLLAMA = {}
                assert LLMConfig.get_ollama_embedding_model() == LLMConfig.get_ollama_model()

    def test_openai_compatible_embedding_fallback_to_model(self):
        from apps.core.llm.config import LLMConfig
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            assert LLMConfig.get_openai_compatible_embedding_model() == LLMConfig.get_openai_compatible_model()


class TestLLMConfigGetDefaultBackend:
    def test_default(self):
        from apps.core.llm.config import LLMConfig
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            with patch("apps.core.llm.config.settings") as mock_s:
                mock_s.LLM = {}
                assert LLMConfig.get_default_backend() == "openai_compatible"

    def test_from_system_config(self):
        from apps.core.llm.config import LLMConfig
        with patch.object(LLMConfig, "_get_system_config", return_value="ollama"):
            assert LLMConfig.get_default_backend() == "ollama"

    def test_invalid_backend_from_config(self):
        from apps.core.llm.config import LLMConfig
        with patch.object(LLMConfig, "_get_system_config", return_value="invalid"):
            with patch("apps.core.llm.config.settings") as mock_s:
                mock_s.LLM = {}
                assert LLMConfig.get_default_backend() == "openai_compatible"

    def test_from_django_settings(self):
        from apps.core.llm.config import LLMConfig
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            with patch("apps.core.llm.config.settings") as mock_s:
                mock_s.LLM = {"DEFAULT_BACKEND": "ollama"}
                assert LLMConfig.get_default_backend() == "ollama"
