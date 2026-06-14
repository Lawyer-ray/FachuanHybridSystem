"""Tests for apps.core.llm.model_list_service."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.llm.model_list_service import (
    ModelListResult,
    ModelListService,
    _make_model,
    _KNOWN_CONTEXT_WINDOWS,
)


class TestMakeModel:
    def test_basic_model(self) -> None:
        result = _make_model("kimi26")
        assert result["id"] == "kimi26"
        assert result["name"] == "kimi26"
        assert result["context_window"] == _KNOWN_CONTEXT_WINDOWS.get("kimi26", 0)

    def test_model_with_slash(self) -> None:
        result = _make_model("org/repo:model")
        assert result["name"] == "model"

    def test_explicit_context_window(self) -> None:
        result = _make_model("unknown", context_window=42)
        assert result["context_window"] == 42

    def test_known_model_context_window(self) -> None:
        result = _make_model("gpt-4o")
        assert result["context_window"] == 128000


class TestModelListResult:
    def test_is_ok_when_not_fallback(self) -> None:
        result = ModelListResult(models=[{"id": "x"}], is_fallback=False)
        assert result.is_ok is True

    def test_is_not_ok_when_fallback(self) -> None:
        result = ModelListResult(models=[], is_fallback=True, error_message="down")
        assert result.is_ok is False

    def test_defaults(self) -> None:
        result = ModelListResult()
        assert result.models == []
        assert result.is_fallback is False
        assert result.error_message == ""


class TestModelListService:
    def setup_method(self) -> None:
        self.svc = ModelListService(cache_ttl=10)

    @patch("apps.core.llm.model_list_service.cache")
    def test_get_result_uses_cache(self, mock_cache: MagicMock) -> None:
        cached_models = [{"id": "cached"}]
        cached_status = {"is_fallback": False, "error_message": ""}
        mock_cache.get.side_effect = lambda k: cached_models if k == "llm_model_list" else cached_status
        with patch.object(self.svc, "_merge_system_config_models", return_value=cached_models) as merge_mock:
            result = self.svc.get_result()
            assert result.models == cached_models
            merge_mock.assert_called_once()

    @patch("apps.core.llm.model_list_service.cache")
    def test_get_result_fetches_when_no_cache(self, mock_cache: MagicMock) -> None:
        mock_cache.get.return_value = None
        fallback = ModelListResult(models=[], is_fallback=True)
        with patch.object(self.svc, "_fetch_from_api", return_value=fallback):
            with patch.object(self.svc, "_merge_system_config_models", return_value=[]) as merge_mock:
                result = self.svc.get_result()
                assert result.is_fallback is True
                merge_mock.assert_called_once()

    @patch("apps.core.llm.model_list_service.cache")
    def test_get_models_returns_list(self, mock_cache: MagicMock) -> None:
        cached_models = [{"id": "m1"}]
        cached_status = {"is_fallback": False, "error_message": ""}
        mock_cache.get.side_effect = lambda k: cached_models if k == "llm_model_list" else cached_status
        with patch.object(self.svc, "_merge_system_config_models", return_value=cached_models):
            models = self.svc.get_models()
            assert models == cached_models

    @patch("apps.core.llm.model_list_service.LLMConfig")
    def test_fetch_from_api_ollama_enabled(self, mock_llm: MagicMock) -> None:
        mock_config = MagicMock()
        mock_config.enabled = True
        mock_llm.get_backend_configs.return_value = {"ollama": mock_config}
        with patch.object(
            self.svc, "_fetch_ollama_models", return_value=[{"id": "qwen3:0.6b"}]
        ):
            result = self.svc._fetch_from_api()
            assert len(result.models) == 1
            assert result.is_fallback is False

    @patch("apps.core.llm.model_list_service.LLMConfig")
    def test_fetch_from_api_all_disabled_fallback(self, mock_llm: MagicMock) -> None:
        mock_llm.get_backend_configs.return_value = {"ollama": MagicMock(enabled=False)}
        result = self.svc._fetch_from_api()
        assert result.is_fallback is True
        assert result.error_message != ""

    def test_get_fallback_models(self) -> None:
        result = ModelListService._get_fallback_models()
        assert isinstance(result, list)

    @patch("apps.core.llm.model_list_service.LLMConfig")
    def test_fetch_ollama_empty_url(self, mock_llm: MagicMock) -> None:
        mock_llm.get_ollama_base_url.return_value = ""
        mock_llm.get_ollama_model.return_value = ""
        result = ModelListService._fetch_ollama_models()
        assert result == []

    def test_known_context_windows_not_empty(self) -> None:
        assert len(_KNOWN_CONTEXT_WINDOWS) > 0
        assert "kimi26" in _KNOWN_CONTEXT_WINDOWS
