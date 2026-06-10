"""Tests for LLMConfig - targeting all uncovered branches."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestLLMConfigNormalizeApiKey:
    """Test _normalize_api_key."""

    def test_strips_whitespace(self):
        from apps.core.llm.config import LLMConfig

        assert LLMConfig._normalize_api_key("  sk-abc  ") == "sk-abc"

    def test_strips_bearer_prefix(self):
        from apps.core.llm.config import LLMConfig

        assert LLMConfig._normalize_api_key("Bearer sk-abc") == "sk-abc"
        assert LLMConfig._normalize_api_key("bearer sk-abc") == "sk-abc"

    def test_empty_string(self):
        from apps.core.llm.config import LLMConfig

        assert LLMConfig._normalize_api_key("") == ""
        assert LLMConfig._normalize_api_key(None) == ""  # type: ignore[arg-type]

    def test_bearer_without_space(self):
        from apps.core.llm.config import LLMConfig

        # "bearer" without space after should not strip
        result = LLMConfig._normalize_api_key("bearersk-abc")
        assert result == "bearersk-abc"


class TestLLMConfigNormalizeBaseUrl:
    """Test _normalize_base_url."""

    def test_strips_trailing_slashes(self):
        from apps.core.llm.config import LLMConfig

        assert LLMConfig._normalize_base_url("http://example.com///") == "http://example.com"

    def test_returns_default_on_empty(self):
        from apps.core.llm.config import LLMConfig

        assert LLMConfig._normalize_base_url("") == LLMConfig.DEFAULT_BASE_URL
        assert LLMConfig._normalize_base_url("   ") == LLMConfig.DEFAULT_BASE_URL

    def test_normal_url(self):
        from apps.core.llm.config import LLMConfig

        assert LLMConfig._normalize_base_url("http://localhost:8080") == "http://localhost:8080"


class TestLLMConfigParseBool:
    """Test _parse_bool."""

    def test_bool_values(self):
        from apps.core.llm.config import LLMConfig

        assert LLMConfig._parse_bool(True, False) is True
        assert LLMConfig._parse_bool(False, True) is False

    def test_truthy_strings(self):
        from apps.core.llm.config import LLMConfig

        for v in ("1", "true", "yes", "y", "on", "True", "YES", "ON"):
            assert LLMConfig._parse_bool(v, False) is True, f"Failed for {v!r}"

    def test_falsy_strings(self):
        from apps.core.llm.config import LLMConfig

        for v in ("0", "false", "no", "n", "off", "False", "NO", "OFF"):
            assert LLMConfig._parse_bool(v, True) is False, f"Failed for {v!r}"

    def test_unknown_string_returns_default(self):
        from apps.core.llm.config import LLMConfig

        assert LLMConfig._parse_bool("maybe", True) is True
        assert LLMConfig._parse_bool("maybe", False) is False

    def test_empty_string_returns_default(self):
        from apps.core.llm.config import LLMConfig

        assert LLMConfig._parse_bool("", True) is True
        assert LLMConfig._parse_bool(None, False) is False


class TestLLMConfigParseInt:
    """Test _parse_int."""

    def test_valid_int(self):
        from apps.core.llm.config import LLMConfig

        assert LLMConfig._parse_int("42", 0) == 42
        assert LLMConfig._parse_int(100, 0) == 100

    def test_none_returns_default(self):
        from apps.core.llm.config import LLMConfig

        assert LLMConfig._parse_int(None, 10) == 10

    def test_empty_string_returns_default(self):
        from apps.core.llm.config import LLMConfig

        assert LLMConfig._parse_int("", 10) == 10

    def test_invalid_string_returns_default(self):
        from apps.core.llm.config import LLMConfig

        assert LLMConfig._parse_int("abc", 10) == 10
        assert LLMConfig._parse_int("12.5", 10) == 10


class TestLLMConfigResolveBackend:
    """Test resolve_backend_for_model."""

    def test_siliconflow_for_slash(self):
        from apps.core.llm.config import LLMConfig

        assert LLMConfig.resolve_backend_for_model("Qwen/Qwen2.5-7B") == "siliconflow"

    def test_ollama_for_colon(self):
        from apps.core.llm.config import LLMConfig

        assert LLMConfig.resolve_backend_for_model("qwen3:0.6b") == "ollama"

    def test_openai_compatible_for_plain(self):
        from apps.core.llm.config import LLMConfig

        assert LLMConfig.resolve_backend_for_model("kimi26") == "openai_compatible"

    def test_empty_model_uses_default_backend(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "get_default_backend", return_value="siliconflow"):
            assert LLMConfig.resolve_backend_for_model("") == "siliconflow"
            assert LLMConfig.resolve_backend_for_model(None) == "siliconflow"  # type: ignore[arg-type]


class TestLLMConfigSystemConfig:
    """Test _get_system_config with various scenarios."""

    def test_config_service_returns_value(self):
        from apps.core.llm.config import LLMConfig

        mock_service = MagicMock()
        mock_service.get_value.return_value = "test-value"

        with patch.object(LLMConfig, "_get_config_service", return_value=mock_service):
            result = LLMConfig._get_system_config("TEST_KEY", "default")
            assert result == "test-value"
            mock_service.get_value.assert_called_once_with("TEST_KEY", default="")

    def test_config_service_returns_empty_falls_to_django(self):
        from apps.core.llm.config import LLMConfig

        mock_service = MagicMock()
        mock_service.get_value.return_value = ""

        with patch.object(LLMConfig, "_get_config_service", return_value=mock_service):
            with patch.object(LLMConfig, "_get_django_settings_fallback", return_value="django-val"):
                result = LLMConfig._get_system_config("TEST_KEY", "default")
                assert result == "django-val"

    def test_config_service_throws_key_error(self):
        from apps.core.llm.config import LLMConfig

        mock_service = MagicMock()
        mock_service.get_value.side_effect = KeyError("not found")

        with patch.object(LLMConfig, "_get_config_service", return_value=mock_service):
            with patch.object(LLMConfig, "_get_django_settings_fallback", return_value="fallback"):
                result = LLMConfig._get_system_config("TEST_KEY", "default")
                assert result == "fallback"

    def test_config_service_throws_attribute_error(self):
        from apps.core.llm.config import LLMConfig

        mock_service = MagicMock()
        mock_service.get_value.side_effect = AttributeError("attr error")

        with patch.object(LLMConfig, "_get_config_service", return_value=mock_service):
            with patch.object(LLMConfig, "_get_django_settings_fallback", return_value="fallback"):
                result = LLMConfig._get_system_config("TEST_KEY", "default")
                assert result == "fallback"

    def test_config_service_throws_type_error(self):
        from apps.core.llm.config import LLMConfig

        mock_service = MagicMock()
        mock_service.get_value.side_effect = TypeError("type error")

        with patch.object(LLMConfig, "_get_config_service", return_value=mock_service):
            with patch.object(LLMConfig, "_get_django_settings_fallback", return_value="fallback"):
                result = LLMConfig._get_system_config("TEST_KEY", "default")
                assert result == "fallback"

    def test_config_service_none_falls_to_django(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_config_service", return_value=None):
            with patch.object(LLMConfig, "_get_django_settings_fallback", return_value="django-val"):
                result = LLMConfig._get_system_config("TEST_KEY", "default")
                assert result == "django-val"

    def test_both_empty_returns_default(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_config_service", return_value=None):
            with patch.object(LLMConfig, "_get_django_settings_fallback", return_value=""):
                result = LLMConfig._get_system_config("TEST_KEY", "default-val")
                assert result == "default-val"


class TestLLMConfigDjangoFallback:
    """Test _get_django_settings_fallback."""

    def test_reads_from_siliconflow_config(self):
        from apps.core.llm.config import LLMConfig

        with patch("apps.core.llm.config.settings") as mock_settings:
            mock_settings.SILICONFLOW = {"API_KEY": "test-key"}
            result = LLMConfig._get_django_settings_fallback("SILICONFLOW_API_KEY", "")
            assert result == "test-key"

    def test_returns_default_for_missing_key(self):
        from apps.core.llm.config import LLMConfig

        with patch("apps.core.llm.config.settings") as mock_settings:
            mock_settings.SILICONFLOW = {}
            result = LLMConfig._get_django_settings_fallback("SILICONFLOW_MISSING", "def")
            assert result == "def"

    def test_non_string_value_converted(self):
        from apps.core.llm.config import LLMConfig

        with patch("apps.core.llm.config.settings") as mock_settings:
            mock_settings.SILICONFLOW = {"TIMEOUT": 120}
            result = LLMConfig._get_django_settings_fallback("SILICONFLOW_TIMEOUT", "")
            assert result == "120"

    def test_none_value_returns_empty(self):
        from apps.core.llm.config import LLMConfig

        with patch("apps.core.llm.config.settings") as mock_settings:
            mock_settings.SILICONFLOW = {"KEY": None}
            result = LLMConfig._get_django_settings_fallback("SILICONFLOW_KEY", "default")
            assert result == ""


class TestLLMConfigGetters:
    """Test all getter methods."""

    def test_get_api_key(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value="Bearer sk-123"):
            assert LLMConfig.get_api_key() == "sk-123"

    def test_get_base_url(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value="http://test.com/"):
            assert LLMConfig.get_base_url() == "http://test.com"

    def test_get_default_model_fallback(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            assert LLMConfig.get_default_model() == LLMConfig.DEFAULT_MODEL

    def test_get_default_model_from_config(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value="custom-model"):
            assert LLMConfig.get_default_model() == "custom-model"

    def test_get_embedding_model_from_config(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value="embed-model"):
            assert LLMConfig.get_embedding_model() == "embed-model"

    def test_get_embedding_model_falls_to_default(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            with patch.object(LLMConfig, "get_default_model", return_value="def-model"):
                assert LLMConfig.get_embedding_model() == "def-model"

    def test_get_timeout_valid(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value="120"):
            assert LLMConfig.get_timeout() == 120

    def test_get_timeout_invalid(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value="abc"):
            assert LLMConfig.get_timeout() == LLMConfig.DEFAULT_TIMEOUT

    def test_get_temperature_valid(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value="0.5"):
            assert LLMConfig.get_temperature() == 0.5

    def test_get_temperature_invalid(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value="abc"):
            assert LLMConfig.get_temperature() == 0.3

    def test_get_max_tokens_valid(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value="4096"):
            assert LLMConfig.get_max_tokens() == 4096

    def test_get_max_tokens_invalid(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value="abc"):
            assert LLMConfig.get_max_tokens() == 2000


class TestLLMConfigOllama:
    """Test Ollama config methods."""

    def test_get_ollama_model_from_config(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value="llama3"):
            assert LLMConfig.get_ollama_model() == "llama3"

    def test_get_ollama_model_from_django_settings(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            with patch("apps.core.llm.config.settings") as mock_settings:
                mock_settings.OLLAMA = {"MODEL": "mistral"}
                assert LLMConfig.get_ollama_model() == "mistral"

    def test_get_ollama_model_default(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            with patch("apps.core.llm.config.settings") as mock_settings:
                mock_settings.OLLAMA = {}
                assert LLMConfig.get_ollama_model() == LLMConfig.DEFAULT_OLLAMA_MODEL

    def test_get_ollama_base_url_from_config(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value="http://custom:11434"):
            assert LLMConfig.get_ollama_base_url() == "http://custom:11434"

    def test_get_ollama_base_url_from_django_settings(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            with patch("apps.core.llm.config.settings") as mock_settings:
                mock_settings.OLLAMA = {"BASE_URL": "http://remote:11434"}
                assert LLMConfig.get_ollama_base_url() == "http://remote:11434"

    def test_get_ollama_base_url_default(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            with patch("apps.core.llm.config.settings") as mock_settings:
                mock_settings.OLLAMA = {}
                assert LLMConfig.get_ollama_base_url() == LLMConfig.DEFAULT_OLLAMA_BASE_URL

    def test_get_ollama_timeout_valid(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value="600"):
            assert LLMConfig.get_ollama_timeout() == 600

    def test_get_ollama_timeout_invalid(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value="abc"):
            assert LLMConfig.get_ollama_timeout() == LLMConfig.DEFAULT_OLLAMA_TIMEOUT

    def test_get_ollama_embedding_model_from_config(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value="nomic-embed"):
            assert LLMConfig.get_ollama_embedding_model() == "nomic-embed"

    def test_get_ollama_embedding_model_from_django(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            with patch("apps.core.llm.config.settings") as mock_settings:
                mock_settings.OLLAMA = {"EMBEDDING_MODEL": "mxbai-embed"}
                assert LLMConfig.get_ollama_embedding_model() == "mxbai-embed"

    def test_get_ollama_embedding_model_falls_to_model(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            with patch("apps.core.llm.config.settings") as mock_settings:
                mock_settings.OLLAMA = {}
                with patch.object(LLMConfig, "get_ollama_model", return_value="qwen3:0.6b"):
                    assert LLMConfig.get_ollama_embedding_model() == "qwen3:0.6b"


class TestLLMConfigOpenAICompatible:
    """Test OpenAI-compatible config methods."""

    def test_get_api_key(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value="Bearer oc-key"):
            assert LLMConfig.get_openai_compatible_api_key() == "oc-key"

    def test_get_base_url_from_config(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value="http://custom:8001/v1"):
            assert LLMConfig.get_openai_compatible_base_url() == "http://custom:8001/v1"

    def test_get_base_url_default(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            assert LLMConfig.get_openai_compatible_base_url() == LLMConfig.DEFAULT_OPENAI_COMPATIBLE_BASE_URL

    def test_get_model_from_config(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value="custom-oc"):
            assert LLMConfig.get_openai_compatible_model() == "custom-oc"

    def test_get_model_default(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            assert LLMConfig.get_openai_compatible_model() == LLMConfig.DEFAULT_OPENAI_COMPATIBLE_MODEL

    def test_get_embedding_model_from_config(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value="oc-embed"):
            assert LLMConfig.get_openai_compatible_embedding_model() == "oc-embed"

    def test_get_embedding_model_falls_to_model(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            with patch.object(LLMConfig, "get_openai_compatible_model", return_value="kimi26"):
                assert LLMConfig.get_openai_compatible_embedding_model() == "kimi26"

    def test_get_timeout_valid(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value="300"):
            assert LLMConfig.get_openai_compatible_timeout() == 300

    def test_get_timeout_invalid(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value="abc"):
            assert LLMConfig.get_openai_compatible_timeout() == LLMConfig.DEFAULT_OPENAI_COMPATIBLE_TIMEOUT

    def test_get_timeout_empty(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            assert LLMConfig.get_openai_compatible_timeout() == LLMConfig.DEFAULT_OPENAI_COMPATIBLE_TIMEOUT


class TestLLMConfigDefaultBackend:
    """Test get_default_backend."""

    def test_from_system_config(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value="ollama"):
            assert LLMConfig.get_default_backend() == "ollama"

    def test_invalid_system_config_falls_to_django(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value="invalid_backend"):
            with patch("apps.core.llm.config.settings") as mock_settings:
                mock_settings.LLM = {"DEFAULT_BACKEND": "ollama"}
                assert LLMConfig.get_default_backend() == "ollama"

    def test_empty_system_config_falls_to_django(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            with patch("apps.core.llm.config.settings") as mock_settings:
                mock_settings.LLM = {"DEFAULT_BACKEND": "openai_compatible"}
                assert LLMConfig.get_default_backend() == "openai_compatible"

    def test_default_siliconflow(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            with patch("apps.core.llm.config.settings") as mock_settings:
                mock_settings.LLM = {}
                assert LLMConfig.get_default_backend() == "siliconflow"


class TestLLMConfigBackendConfigs:
    """Test get_backend_configs."""

    def test_returns_all_three_backends(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            configs = LLMConfig.get_backend_configs()
            assert "siliconflow" in configs
            assert "ollama" in configs
            assert "openai_compatible" in configs

    def test_siliconflow_enabled_by_default(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            configs = LLMConfig.get_backend_configs()
            assert configs["siliconflow"].enabled is True

    def test_openai_compatible_auto_enabled_with_base_url(self):
        from apps.core.llm.config import LLMConfig

        def mock_get(key, default=""):
            if key == "OPENAI_COMPATIBLE_BASE_URL":
                return "http://test:8001/v1"
            return ""

        with patch.object(LLMConfig, "_get_system_config", side_effect=mock_get):
            configs = LLMConfig.get_backend_configs()
            assert configs["openai_compatible"].enabled is True

    def test_explicit_disabled_overrides(self):
        from apps.core.llm.config import LLMConfig

        def mock_get(key, default=""):
            if key == "LLM_BACKEND_OPENAI_COMPATIBLE_ENABLED":
                return "false"
            if key == "OPENAI_COMPATIBLE_BASE_URL":
                return "http://test:8001/v1"
            return ""

        with patch.object(LLMConfig, "_get_system_config", side_effect=mock_get):
            configs = LLMConfig.get_backend_configs()
            assert configs["openai_compatible"].enabled is False


class TestLLMConfigGetAvailableModels:
    """Test get_available_models."""

    def test_returns_default_models(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            models = LLMConfig.get_available_models()
            model_ids = [m["id"] for m in models]
            assert "Qwen/Qwen2.5-7B-Instruct" in model_ids

    def test_extra_models_included(self):
        from apps.core.llm.config import LLMConfig

        def mock_get(key, default=""):
            if key == "LLM_EXTRA_MODELS":
                return "custom-model-1,custom-model-2"
            return ""

        with patch.object(LLMConfig, "_get_system_config", side_effect=mock_get):
            models = LLMConfig.get_available_models()
            model_ids = [m["id"] for m in models]
            assert "custom-model-1" in model_ids
            assert "custom-model-2" in model_ids

    def test_extra_models_deduped(self):
        from apps.core.llm.config import LLMConfig

        def mock_get(key, default=""):
            if key == "LLM_EXTRA_MODELS":
                return "Qwen/Qwen2.5-7B-Instruct"
            return ""

        with patch.object(LLMConfig, "_get_system_config", side_effect=mock_get):
            models = LLMConfig.get_available_models()
            qwen_count = sum(1 for m in models if m["id"] == "Qwen/Qwen2.5-7B-Instruct")
            assert qwen_count == 1

    def test_backend_annotation(self):
        from apps.core.llm.config import LLMConfig

        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            models = LLMConfig.get_available_models()
            for m in models:
                assert "backend" in m
                assert m["backend"] in ("siliconflow", "ollama", "openai_compatible")
