"""Coverage tests for core.llm.model_list_service."""

from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.core.llm.model_list_service import (
    ModelListResult,
    ModelListService,
    _make_model,
)


class TestMakeModel:
    def test_basic(self):
        result = _make_model("test-model")
        assert result["id"] == "test-model"
        assert result["name"] == "test-model"

    def test_with_context_window(self):
        result = _make_model("model", 4096)
        assert result["context_window"] == 4096

    def test_known_context_window(self):
        result = _make_model("gpt-4o")
        assert result["context_window"] == 128000

    def test_slash_in_name(self):
        result = _make_model("org/model-name")
        assert result["name"] == "model-name"


class TestModelListResult:
    def test_defaults(self):
        r = ModelListResult()
        assert r.models == []
        assert r.is_fallback is False
        assert r.error_message == ""
        assert r.is_ok is True

    def test_is_ok_false(self):
        r = ModelListResult(is_fallback=True)
        assert r.is_ok is False


class TestModelListService:
    def _make(self):
        return ModelListService(cache_ttl=60)

    @patch("apps.core.llm.model_list_service.cache")
    def test_get_models_from_cache(self, mock_cache):
        svc = self._make()
        mock_cache.get.side_effect = lambda key: {
            "siliconflow_model_list": [{"id": "m1", "name": "m1", "context_window": 0}],
            "siliconflow_model_list_status": {"is_fallback": False, "error_message": ""},
        }.get(key)
        with patch.object(svc, "_merge_system_config_models", return_value=[{"id": "m1"}]):
            result = svc.get_models()
        assert len(result) > 0

    @patch("apps.core.llm.model_list_service.cache")
    def test_get_result_from_cache(self, mock_cache):
        svc = self._make()
        mock_cache.get.side_effect = lambda key: {
            "siliconflow_model_list": [{"id": "m1"}],
            "siliconflow_model_list_status": {"is_fallback": False, "error_message": ""},
        }.get(key)
        with patch.object(svc, "_merge_system_config_models", return_value=[]):
            result = svc.get_result()
        assert isinstance(result, ModelListResult)

    @patch("apps.core.llm.model_list_service.cache")
    def test_get_fallback_models(self, mock_cache):
        svc = self._make()
        mock_cache.get.return_value = None
        with patch.object(svc, "_fetch_from_api") as mock_fetch:
            mock_fetch.return_value = ModelListResult(models=[{"id": "x"}], is_fallback=False)
            with patch.object(ModelListService, "_merge_system_config_models", return_value=[{"id": "x"}]):
                result = svc.get_result()
        assert result.models

    @pytest.mark.django_db
    def test_merge_system_config_models_empty(self):
        result = ModelListService._merge_system_config_models([])
        assert isinstance(result, list)

    def test_get_fallback_models_empty(self):
        result = ModelListService._get_fallback_models()
        assert isinstance(result, list)

    @patch("apps.core.llm.model_list_service.LLMConfig")
    def test_fetch_from_api_all_disabled(self, mock_config):
        svc = self._make()
        mock_config.get_backend_configs.return_value = {}
        result = svc._fetch_from_api()
        assert result.is_fallback is True

    @patch("apps.core.llm.model_list_service.LLMConfig")
    @patch("apps.core.llm.model_list_service.httpx")
    def test_fetch_siliconflow_models_no_key(self, mock_httpx, mock_config):
        svc = self._make()
        mock_config.get_api_key.return_value = None
        result = svc._fetch_siliconflow_models()
        assert result == []

    @patch("apps.core.llm.model_list_service.LLMConfig")
    @patch("apps.core.llm.model_list_service.httpx")
    def test_fetch_ollama_models_no_config(self, mock_httpx, mock_config):
        mock_config.get_ollama_base_url.return_value = None
        mock_config.get_ollama_model.return_value = None
        result = ModelListService._fetch_ollama_models()
        assert result == []
