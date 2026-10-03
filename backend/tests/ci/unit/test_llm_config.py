"""Tests for apps.core.llm.config — LLMConfig class."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

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
    def test_openai_model(self):
        from apps.core.llm.config import LLMConfig

        assert LLMConfig.resolve_backend_for_model("kimi26") == "openai_compatible"

    def test_empty_model_uses_default(self):
        from apps.core.llm.config import LLMConfig

        # Ollama 下线：resolve 恒返 openai_compatible，不再读默认后端
        assert LLMConfig.resolve_backend_for_model("") == "openai_compatible"


class TestLLMConfigDefaults:
    def test_openai_compatible_timeout_default(self):
        from apps.core.llm.config import LLMConfig

        assert LLMConfig.get_openai_compatible_timeout() == LLMConfig.DEFAULT_OPENAI_COMPATIBLE_TIMEOUT

    def test_openai_compatible_model_unconfigured(self):
        from apps.core.llm.config import LLMConfig

        # 无 AI 平台（LLMProvider）时不返回默认常量，返回空表示未配置
        assert LLMConfig.get_openai_compatible_model() == ""

    def test_openai_compatible_base_url_unconfigured(self):
        from apps.core.llm.config import LLMConfig

        assert LLMConfig.get_openai_compatible_base_url() == ""

    def test_openai_compatible_embedding_unconfigured(self):
        from apps.core.llm.config import LLMConfig

        # 向量模型只读 AI 平台配置；无平台返回空（不启用向量），不再回退对话模型
        assert LLMConfig.get_openai_compatible_embedding_model() == ""


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
            # ollama 已下线，不在合法后端集合 → 回落
            assert LLMConfig.get_default_backend() == "openai_compatible"

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
                mock_s.LLM = {"DEFAULT_BACKEND": "openai_compatible"}
                assert LLMConfig.get_default_backend() == "openai_compatible"
