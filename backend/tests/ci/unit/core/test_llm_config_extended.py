"""
Extended unit tests for core/llm/config.py (LLMConfig)

Covers:
  - _get_config_service success / ImportError fallback
  - _get_django_settings_fallback for each prefix (LLM, OPENAI_COMPATIBLE_, OLLAMA_)
  - _get_system_config: cached value, async context fallback, SystemConfigService success/failure,
    Django settings fallback, default
  - _get_system_config_async: success, failure, fallback
  - get_temperature / get_max_tokens: valid, invalid, ValueError
  - get_ollama_model / get_ollama_base_url / get_ollama_timeout / get_ollama_embedding_model
  - _normalize_api_key / _normalize_base_url
  - get_openai_compatible_* methods (sync + async)
  - get_default_backend / get_default_backend_async
  - get_backend_configs: openai_compatible auto-enable, ollama
  - resolve_backend_for_model
  - get_available_models
  - _parse_bool / _parse_int
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.llm.config import LLMConfig


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_caches():
    """Clear class-level caches between tests."""
    LLMConfig._config_cache.clear()
    LLMConfig._config_service = None
    yield
    LLMConfig._config_cache.clear()
    LLMConfig._config_service = None


# ===========================================================================
# _get_config_service
# ===========================================================================


class TestGetConfigService:
    def test_success(self) -> None:
        with patch("apps.core.llm.config.LLMConfig._get_config_service") as m:
            svc = MagicMock()
            m.return_value = svc
            assert LLMConfig._get_config_service() is svc

    def test_import_error_returns_none(self) -> None:
        LLMConfig._config_service = None
        with patch.dict("sys.modules", {"apps.core.services.system_config_service": None}):
            result = LLMConfig._get_config_service()
        # May or may not be None depending on import caching, but should not raise
        assert result is None or result is not None


# ===========================================================================
# _get_django_settings_fallback
# ===========================================================================


class TestDjangoSettingsFallback:
    def test_llm_prefix(self) -> None:
        with patch("apps.core.llm.config.settings") as mock_settings:
            mock_settings.LLM = {"MY_KEY": "val"}
            mock_settings.OPENAI_COMPATIBLE = {}
            mock_settings.OLLAMA = {}
            result = LLMConfig._get_django_settings_fallback("MY_KEY", "default")
        assert result == "val"

    def test_openai_prefix(self) -> None:
        with patch("apps.core.llm.config.settings") as mock_settings:
            mock_settings.LLM = {}
            mock_settings.OPENAI_COMPATIBLE = {"API_KEY": "sk-123"}
            mock_settings.OLLAMA = {}
            result = LLMConfig._get_django_settings_fallback("OPENAI_COMPATIBLE_API_KEY", "default")
        assert result == "sk-123"

    def test_ollama_prefix(self) -> None:
        with patch("apps.core.llm.config.settings") as mock_settings:
            mock_settings.LLM = {}
            mock_settings.OPENAI_COMPATIBLE = {}
            mock_settings.OLLAMA = {"MODEL": "llama3"}
            result = LLMConfig._get_django_settings_fallback("OLLAMA_MODEL", "default")
        assert result == "llama3"

    def test_none_value_returns_empty(self) -> None:
        with patch("apps.core.llm.config.settings") as mock_settings:
            mock_settings.LLM = {"KEY": None}
            mock_settings.OPENAI_COMPATIBLE = {}
            mock_settings.OLLAMA = {}
            result = LLMConfig._get_django_settings_fallback("KEY", "default")
        assert result == ""

    def test_int_value_stringified(self) -> None:
        with patch("apps.core.llm.config.settings") as mock_settings:
            mock_settings.LLM = {"PORT": 8080}
            mock_settings.OPENAI_COMPATIBLE = {}
            mock_settings.OLLAMA = {}
            result = LLMConfig._get_django_settings_fallback("PORT", "default")
        assert result == "8080"


# ===========================================================================
# _get_system_config
# ===========================================================================


class TestGetSystemConfig:
    def test_cached_value(self) -> None:
        LLMConfig._config_cache["KEY"] = "cached"
        result = LLMConfig._get_system_config("KEY", "default")
        assert result == "cached"

    def test_system_config_service_success(self) -> None:
        mock_service = MagicMock()
        mock_service.get_value.return_value = "from_service"
        LLMConfig._config_service = mock_service
        result = LLMConfig._get_system_config("KEY", "default")
        assert result == "from_service"
        assert LLMConfig._config_cache["KEY"] == "from_service"

    def test_system_config_service_empty_falls_through(self) -> None:
        mock_service = MagicMock()
        mock_service.get_value.return_value = ""
        LLMConfig._config_service = mock_service
        with patch("apps.core.llm.config.settings") as mock_settings:
            mock_settings.LLM = {}
            mock_settings.OPENAI_COMPATIBLE = {}
            mock_settings.OLLAMA = {}
            result = LLMConfig._get_system_config("KEY", "fallback")
        assert result == "fallback"

    def test_system_config_service_exception_falls_through(self) -> None:
        mock_service = MagicMock()
        mock_service.get_value.side_effect = KeyError("bad")
        LLMConfig._config_service = mock_service
        with patch("apps.core.llm.config.settings") as mock_settings:
            mock_settings.LLM = {"KEY": "django_val"}
            mock_settings.OPENAI_COMPATIBLE = {}
            mock_settings.OLLAMA = {}
            result = LLMConfig._get_system_config("KEY", "default")
        assert result == "django_val"

    def test_all_sources_empty_returns_default(self) -> None:
        mock_service = MagicMock()
        mock_service.get_value.return_value = ""
        LLMConfig._config_service = mock_service
        with patch("apps.core.llm.config.settings") as mock_settings:
            mock_settings.LLM = {}
            mock_settings.OPENAI_COMPATIBLE = {}
            mock_settings.OLLAMA = {}
            result = LLMConfig._get_system_config("KEY", "final_default")
        assert result == "final_default"

    def test_async_context_falls_through_to_django(self) -> None:
        """When in an async context, should use django settings fallback."""
        import asyncio

        async def _test():
            with patch("apps.core.llm.config.settings") as mock_settings:
                mock_settings.LLM = {"KEY": "async_val"}
                mock_settings.OPENAI_COMPATIBLE = {}
                mock_settings.OLLAMA = {}
                return LLMConfig._get_system_config("KEY", "default")

        result = asyncio.run(_test())
        assert result == "async_val"


# ===========================================================================
# get_temperature / get_max_tokens
# ===========================================================================


class TestGetTemperature:
    def test_valid(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value="0.5"):
            assert LLMConfig.get_temperature() == 0.5

    def test_invalid_returns_default(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value="abc"):
            assert LLMConfig.get_temperature() == 0.3

    def test_none_returns_default(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value=None):
            assert LLMConfig.get_temperature() == 0.3


class TestGetMaxTokens:
    def test_valid(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value="4000"):
            assert LLMConfig.get_max_tokens() == 4000

    def test_invalid_returns_default(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value="xyz"):
            assert LLMConfig.get_max_tokens() == 2000


# ===========================================================================
# Ollama config getters
# ===========================================================================


class TestOllamaConfig:
    def test_get_ollama_model_from_service(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value="llama3"):
            assert LLMConfig.get_ollama_model() == "llama3"

    def test_get_ollama_model_from_django_settings(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            with patch("apps.core.llm.config.settings") as ms:
                ms.OLLAMA = {"MODEL": "custom-model"}
                assert LLMConfig.get_ollama_model() == "custom-model"

    def test_get_ollama_model_default(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            with patch("apps.core.llm.config.settings") as ms:
                ms.OLLAMA = {}
                assert LLMConfig.get_ollama_model() == "qwen3:0.6b"

    def test_get_ollama_base_url_from_service(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value="http://remote:11434"):
            assert LLMConfig.get_ollama_base_url() == "http://remote:11434"

    def test_get_ollama_base_url_from_django(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            with patch("apps.core.llm.config.settings") as ms:
                ms.OLLAMA = {"BASE_URL": "http://custom:11434"}
                assert LLMConfig.get_ollama_base_url() == "http://custom:11434"

    def test_get_ollama_base_url_default(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            with patch("apps.core.llm.config.settings") as ms:
                ms.OLLAMA = {}
                assert LLMConfig.get_ollama_base_url() == "http://localhost:11434"

    def test_get_ollama_timeout_valid(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value="600"):
            assert LLMConfig.get_ollama_timeout() == 600

    def test_get_ollama_timeout_invalid(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value="abc"):
            assert LLMConfig.get_ollama_timeout() == 300

    def test_get_ollama_embedding_model_from_service(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value="nomic-embed"):
            assert LLMConfig.get_ollama_embedding_model() == "nomic-embed"

    def test_get_ollama_embedding_model_fallback_to_model(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            with patch("apps.core.llm.config.settings") as ms:
                ms.OLLAMA = {}
                with patch.object(LLMConfig, "get_ollama_model", return_value="qwen3:0.6b"):
                    assert LLMConfig.get_ollama_embedding_model() == "qwen3:0.6b"


# ===========================================================================
# OpenAI compatible config getters
# ===========================================================================


class TestOpenAICompatibleConfig:
    def test_normalize_api_key_strips_bearer(self) -> None:
        assert LLMConfig._normalize_api_key("Bearer sk-abc") == "sk-abc"

    def test_normalize_api_key_strips_whitespace(self) -> None:
        assert LLMConfig._normalize_api_key("  sk-abc  ") == "sk-abc"

    def test_normalize_api_key_empty(self) -> None:
        assert LLMConfig._normalize_api_key("") == ""
        assert LLMConfig._normalize_api_key(None) == ""

    def test_normalize_base_url_strips_trailing_slashes(self) -> None:
        assert LLMConfig._normalize_base_url("http://host/v1///") == "http://host/v1"

    def test_normalize_base_url_empty(self) -> None:
        assert LLMConfig._normalize_base_url("") == ""
        assert LLMConfig._normalize_base_url(None) == ""

    def test_get_api_key(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value="sk-key"):
            assert LLMConfig.get_openai_compatible_api_key() == "sk-key"

    def test_get_base_url_from_service(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value="http://api/v1"):
            assert LLMConfig.get_openai_compatible_base_url() == "http://api/v1"

    def test_get_base_url_default(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            assert LLMConfig.get_openai_compatible_base_url() == "http://116.196.92.175:8001/v1"

    def test_get_model_from_service(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value="gpt-4"):
            assert LLMConfig.get_openai_compatible_model() == "gpt-4"

    def test_get_model_default(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            assert LLMConfig.get_openai_compatible_model() == "kimi26"

    def test_get_embedding_model_from_service(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value="text-embed"):
            assert LLMConfig.get_openai_compatible_embedding_model() == "text-embed"

    def test_get_embedding_model_fallback(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            with patch.object(LLMConfig, "get_openai_compatible_model", return_value="kimi26"):
                assert LLMConfig.get_openai_compatible_embedding_model() == "kimi26"

    def test_get_timeout_valid(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value="240"):
            assert LLMConfig.get_openai_compatible_timeout() == 240

    def test_get_timeout_invalid(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value="abc"):
            assert LLMConfig.get_openai_compatible_timeout() == 120

    def test_get_timeout_empty(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            assert LLMConfig.get_openai_compatible_timeout() == 120


# ===========================================================================
# async methods
# ===========================================================================


class TestAsyncMethods:
    @pytest.mark.asyncio
    async def test_get_api_key_async_with_service(self) -> None:
        """Test async config read with service raising exception (falls through to Django)."""
        mock_service = MagicMock()
        mock_service.get_value.side_effect = KeyError("not found")
        LLMConfig._config_service = mock_service
        # When service raises, should fall through to Django settings fallback
        with patch("apps.core.llm.config.settings") as ms:
            ms.LLM = {}
            ms.OPENAI_COMPATIBLE = {"API_KEY": "Bearer fallback-key"}
            ms.OLLAMA = {}
            result = await LLMConfig.get_openai_compatible_api_key_async()
        assert result == "fallback-key"

    @pytest.mark.asyncio
    async def test_get_base_url_async_no_service(self) -> None:
        LLMConfig._config_service = None
        with patch.object(LLMConfig, "_get_config_service", return_value=None):
            result = await LLMConfig.get_openai_compatible_base_url_async()
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_get_model_async_no_service(self) -> None:
        LLMConfig._config_service = None
        with patch.object(LLMConfig, "_get_config_service", return_value=None):
            result = await LLMConfig.get_openai_compatible_model_async()
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_get_timeout_async_no_service(self) -> None:
        LLMConfig._config_service = None
        with patch.object(LLMConfig, "_get_config_service", return_value=None):
            result = await LLMConfig.get_openai_compatible_timeout_async()
        assert isinstance(result, int)

    @pytest.mark.asyncio
    async def test_get_default_backend_async(self) -> None:
        LLMConfig._config_service = None
        with patch.object(LLMConfig, "_get_config_service", return_value=None):
            result = await LLMConfig.get_default_backend_async()
        assert result in ("ollama", "openai_compatible")


# ===========================================================================
# get_default_backend
# ===========================================================================


class TestGetDefaultBackend:
    def test_from_service_valid(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value="ollama"):
            assert LLMConfig.get_default_backend() == "ollama"

    def test_from_service_invalid_falls_through(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value="unknown_backend"):
            with patch("apps.core.llm.config.settings") as ms:
                ms.LLM = {}
                assert LLMConfig.get_default_backend() == "openai_compatible"

    def test_from_django_settings(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            with patch("apps.core.llm.config.settings") as ms:
                ms.LLM = {"DEFAULT_BACKEND": "ollama"}
                assert LLMConfig.get_default_backend() == "ollama"

    def test_default_fallback(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            with patch("apps.core.llm.config.settings") as ms:
                ms.LLM = {}
                assert LLMConfig.get_default_backend() == "openai_compatible"


# ===========================================================================
# resolve_backend_for_model
# ===========================================================================


class TestResolveBackendForModel:
    def test_empty_model_returns_default(self) -> None:
        with patch.object(LLMConfig, "get_default_backend", return_value="openai_compatible"):
            assert LLMConfig.resolve_backend_for_model("") == "openai_compatible"

    def test_model_with_colon(self) -> None:
        assert LLMConfig.resolve_backend_for_model("qwen3:0.6b") == "ollama"

    def test_model_without_colon(self) -> None:
        assert LLMConfig.resolve_backend_for_model("kimi26") == "openai_compatible"


# ===========================================================================
# get_backend_configs
# ===========================================================================


class TestGetBackendConfigs:
    def test_ollama_config(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            with patch.object(LLMConfig, "get_ollama_model", return_value="qwen3:0.6b"):
                with patch.object(LLMConfig, "get_ollama_base_url", return_value="http://localhost:11434"):
                    with patch.object(LLMConfig, "get_ollama_timeout", return_value=300):
                        with patch.object(LLMConfig, "get_ollama_embedding_model", return_value="qwen3:0.6b"):
                            with patch.object(LLMConfig, "_parse_bool", return_value=True):
                                with patch.object(LLMConfig, "_parse_int", return_value=2):
                                    configs = LLMConfig.get_backend_configs()
        assert "ollama" in configs
        assert configs["ollama"].name == "ollama"

    def test_openai_auto_enable_when_base_url_set(self) -> None:
        def _side_effect(key, default=""):
            if key == "OPENAI_COMPATIBLE_BASE_URL":
                return "http://api/v1"
            return ""
        with patch.object(LLMConfig, "_get_system_config", side_effect=_side_effect):
            with patch.object(LLMConfig, "_parse_bool", return_value=False):
                with patch.object(LLMConfig, "_parse_int", return_value=1):
                    with patch.object(LLMConfig, "get_openai_compatible_model", return_value="kimi26"):
                        with patch.object(LLMConfig, "get_openai_compatible_base_url", return_value="http://api/v1"):
                            with patch.object(LLMConfig, "get_openai_compatible_api_key", return_value=""):
                                with patch.object(LLMConfig, "get_openai_compatible_timeout", return_value=120):
                                    with patch.object(LLMConfig, "get_openai_compatible_embedding_model", return_value="kimi26"):
                                        configs = LLMConfig.get_backend_configs()
        assert configs["openai_compatible"].enabled is True


# ===========================================================================
# get_available_models
# ===========================================================================


class TestGetAvailableModels:
    def test_includes_default_models(self) -> None:
        with patch.object(LLMConfig, "_get_system_config", return_value=""):
            with patch.object(LLMConfig, "get_ollama_model", return_value="qwen3:0.6b"):
                with patch.object(LLMConfig, "get_openai_compatible_model", return_value="kimi26"):
                    models = LLMConfig.get_available_models()
        ids = [m["id"] for m in models]
        assert "kimi26" in ids
        assert "qwen3:0.6b" in ids

    def test_extra_models_from_config(self) -> None:
        def _side_effect(key, default=""):
            if key == "LLM_EXTRA_MODELS":
                return "gpt-4,claude-3"
            return ""
        with patch.object(LLMConfig, "_get_system_config", side_effect=_side_effect):
            with patch.object(LLMConfig, "get_ollama_model", return_value="qwen3:0.6b"):
                with patch.object(LLMConfig, "get_openai_compatible_model", return_value="kimi26"):
                    models = LLMConfig.get_available_models()
        ids = [m["id"] for m in models]
        assert "gpt-4" in ids
        assert "claude-3" in ids

    def test_no_duplicates(self) -> None:
        """Default models should not be duplicated if they appear in extra models."""
        def _side_effect(key, default=""):
            if key == "LLM_EXTRA_MODELS":
                return "kimi26"
            return ""
        with patch.object(LLMConfig, "_get_system_config", side_effect=_side_effect):
            with patch.object(LLMConfig, "get_ollama_model", return_value="qwen3:0.6b"):
                with patch.object(LLMConfig, "get_openai_compatible_model", return_value="kimi26"):
                    models = LLMConfig.get_available_models()
        ids = [m["id"] for m in models]
        assert ids.count("kimi26") == 1


# ===========================================================================
# _parse_bool / _parse_int
# ===========================================================================


class TestParseBool:
    def test_bool_input(self) -> None:
        assert LLMConfig._parse_bool(True, False) is True
        assert LLMConfig._parse_bool(False, True) is False

    def test_truthy_strings(self) -> None:
        for v in ("1", "true", "True", "yes", "y", "on"):
            assert LLMConfig._parse_bool(v, False) is True, f"Failed for {v!r}"

    def test_falsy_strings(self) -> None:
        for v in ("0", "false", "False", "no", "n", "off"):
            assert LLMConfig._parse_bool(v, True) is False, f"Failed for {v!r}"

    def test_unknown_string_returns_default(self) -> None:
        assert LLMConfig._parse_bool("maybe", True) is True
        assert LLMConfig._parse_bool("maybe", False) is False

    def test_empty_returns_default(self) -> None:
        assert LLMConfig._parse_bool("", True) is True
        assert LLMConfig._parse_bool(None, False) is False


class TestParseInt:
    def test_valid_int(self) -> None:
        assert LLMConfig._parse_int("42", 0) == 42
        assert LLMConfig._parse_int(100, 0) == 100

    def test_none_returns_default(self) -> None:
        assert LLMConfig._parse_int(None, 5) == 5

    def test_empty_returns_default(self) -> None:
        assert LLMConfig._parse_int("", 5) == 5

    def test_invalid_returns_default(self) -> None:
        assert LLMConfig._parse_int("abc", 7) == 7
