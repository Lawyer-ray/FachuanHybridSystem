"""Tests for apps.core.llm.config — LLMConfig class methods."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestLLMConfigParseBool:
    """Test _parse_bool classmethod."""

    def _cls(self):
        from apps.core.llm.config import LLMConfig
        return LLMConfig

    def test_bool_passthrough(self) -> None:
        cls = self._cls()
        assert cls._parse_bool(True, False) is True
        assert cls._parse_bool(False, True) is False

    def test_string_truthy(self) -> None:
        cls = self._cls()
        for val in ("1", "true", "yes", "y", "on", "True", "YES"):
            assert cls._parse_bool(val, False) is True

    def test_string_falsy(self) -> None:
        cls = self._cls()
        for val in ("0", "false", "no", "n", "off", "False", "NO"):
            assert cls._parse_bool(val, True) is False

    def test_empty_returns_default(self) -> None:
        cls = self._cls()
        assert cls._parse_bool("", True) is True
        assert cls._parse_bool(None, False) is False

    def test_unknown_returns_default(self) -> None:
        cls = self._cls()
        assert cls._parse_bool("maybe", True) is True
        assert cls._parse_bool("xyz", False) is False


class TestLLMConfigParseInt:
    def _cls(self):
        from apps.core.llm.config import LLMConfig
        return LLMConfig

    def test_valid_int(self) -> None:
        cls = self._cls()
        assert cls._parse_int("42", 0) == 42

    def test_none_returns_default(self) -> None:
        cls = self._cls()
        assert cls._parse_int(None, 99) == 99

    def test_empty_returns_default(self) -> None:
        cls = self._cls()
        assert cls._parse_int("", 77) == 77

    def test_invalid_returns_default(self) -> None:
        cls = self._cls()
        assert cls._parse_int("abc", 55) == 55


class TestLLMConfigNormalizeMethods:
    def _cls(self):
        from apps.core.llm.config import LLMConfig
        return LLMConfig

    def test_normalize_api_key_strips_bearer(self) -> None:
        cls = self._cls()
        assert cls._normalize_api_key("Bearer sk-abc") == "sk-abc"

    def test_normalize_api_key_strips_whitespace(self) -> None:
        cls = self._cls()
        assert cls._normalize_api_key("  sk-abc  ") == "sk-abc"

    def test_normalize_api_key_empty(self) -> None:
        cls = self._cls()
        assert cls._normalize_api_key("") == ""

    def test_normalize_base_url_trailing_slashes(self) -> None:
        cls = self._cls()
        assert cls._normalize_base_url("http://example.com///") == "http://example.com"

    def test_normalize_base_url_no_trailing_slash(self) -> None:
        cls = self._cls()
        assert cls._normalize_base_url("http://example.com") == "http://example.com"

    def test_normalize_base_url_empty(self) -> None:
        cls = self._cls()
        assert cls._normalize_base_url("") == ""


class TestLLMConfigResolveBackendForModel:
    def _cls(self):
        from apps.core.llm.config import LLMConfig
        return LLMConfig

    def test_colon_model_returns_ollama(self) -> None:
        cls = self._cls()
        assert cls.resolve_backend_for_model("qwen3:0.6b") == "ollama"

    def test_no_colon_returns_openai_compatible(self) -> None:
        cls = self._cls()
        assert cls.resolve_backend_for_model("kimi26") == "openai_compatible"

    @patch("apps.core.llm.config.LLMConfig._get_system_config", return_value="")
    def test_empty_model_uses_default(self, mock_config: MagicMock) -> None:
        cls = self._cls()
        result = cls.resolve_backend_for_model("")
        assert result in ("ollama", "openai_compatible")

    def test_deep_slash_model(self) -> None:
        cls = self._cls()
        assert cls.resolve_backend_for_model("org/repo:model") == "ollama"


class TestLLMConfigConstants:
    def test_default_values(self) -> None:
        from apps.core.llm.config import LLMConfig

        assert LLMConfig.DEFAULT_OLLAMA_MODEL == "qwen3:0.6b"
        assert "localhost" in LLMConfig.DEFAULT_OLLAMA_BASE_URL
        assert LLMConfig.DEFAULT_OLLAMA_TIMEOUT == 300
        assert LLMConfig.DEFAULT_OPENAI_COMPATIBLE_MODEL == "kimi26"
        assert LLMConfig.DEFAULT_OPENAI_COMPATIBLE_TIMEOUT == 120
        assert "ollama" in LLMConfig._VALID_BACKENDS
        assert "openai_compatible" in LLMConfig._VALID_BACKENDS
