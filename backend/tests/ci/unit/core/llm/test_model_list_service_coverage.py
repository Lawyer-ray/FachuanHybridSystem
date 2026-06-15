"""Tests for apps.core.llm.model_list_service — ModelListService + ModelListResult + _make_model."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.llm.model_list_service import (
    ModelListResult,
    ModelListService,
    _make_model,
)


class TestMakeModel:
    def test_basic(self):
        m = _make_model("gpt-4o")
        assert m["id"] == "gpt-4o"
        assert m["name"] == "gpt-4o"
        assert m["context_window"] == 128000

    def test_unknown_model_no_context(self):
        m = _make_model("unknown-model")
        assert m["context_window"] == 0

    def test_explicit_context_window(self):
        m = _make_model("m", context_window=999)
        assert m["context_window"] == 999

    def test_slash_model_name(self):
        m = _make_model("org/model-name")
        assert m["name"] == "model-name"

    def test_colon_model_name(self):
        m = _make_model("qwen3:0.6b")
        assert m["name"] == "0.6b"


class TestModelListResult:
    def test_is_ok_when_not_fallback(self):
        r = ModelListResult(models=[], is_fallback=False)
        assert r.is_ok is True

    def test_is_ok_when_fallback(self):
        r = ModelListResult(models=[], is_fallback=True)
        assert r.is_ok is False

    def test_defaults(self):
        r = ModelListResult()
        assert r.models == []
        assert r.is_fallback is False
        assert r.error_message == ""


class TestModelListService:
    def test_get_models_from_cache(self):
        svc = ModelListService(cache_ttl=60)
        cached_models = [{"id": "m1", "name": "m1", "context_window": 100}]
        cached_status = {"is_fallback": False, "error_message": ""}
        with patch("apps.core.llm.model_list_service.cache") as mock_cache, \
             patch.object(ModelListService, "_merge_system_config_models", return_value=cached_models):
            mock_cache.get.side_effect = lambda k: cached_models if k == "llm_model_list" else cached_status
            result = svc.get_result()
            assert result.models[0]["id"] == "m1"

    def test_get_models_fetches_from_api(self):
        svc = ModelListService(cache_ttl=60)
        api_models = [{"id": "api-m", "name": "api-m", "context_window": 0}]
        with (
            patch("apps.core.llm.model_list_service.cache") as mock_cache,
            patch.object(svc, "_fetch_from_api", return_value=ModelListResult(models=api_models)),
            patch.object(ModelListService, "_merge_system_config_models", return_value=api_models),
        ):
            mock_cache.get.return_value = None
            result = svc.get_result()
            assert result.models[0]["id"] == "api-m"

    def test_get_models_returns_list(self):
        svc = ModelListService(cache_ttl=60)
        models = [{"id": "x", "name": "x", "context_window": 0}]
        with (
            patch("apps.core.llm.model_list_service.cache") as mock_cache,
            patch.object(svc, "_fetch_from_api", return_value=ModelListResult(models=models)),
            patch.object(ModelListService, "_merge_system_config_models", return_value=models),
        ):
            mock_cache.get.return_value = None
            result = svc.get_models()
            assert isinstance(result, list)

    def test_fetch_from_api_ollama_enabled(self):
        svc = ModelListService()
        with patch("apps.core.llm.model_list_service.LLMConfig") as mock_cfg:
            mock_cfg.get_backend_configs.return_value = {"ollama": MagicMock(enabled=True)}
            with patch.object(svc, "_fetch_ollama_models", return_value=[{"id": "oll"}]):
                result = svc._fetch_from_api()
                assert result.models[0]["id"] == "oll"

    def test_fetch_from_api_all_unavailable(self):
        svc = ModelListService()
        with patch("apps.core.llm.model_list_service.LLMConfig") as mock_cfg:
            mock_cfg.get_backend_configs.return_value = {"ollama": MagicMock(enabled=False)}
            with patch.object(svc, "_get_fallback_models", return_value=[{"id": "fb"}]):
                result = svc._fetch_from_api()
                assert result.is_fallback is True

    def test_fetch_from_api_empty_backends(self):
        svc = ModelListService()
        with patch("apps.core.llm.model_list_service.LLMConfig") as mock_cfg:
            mock_cfg.get_backend_configs.return_value = {}
            with patch.object(svc, "_get_fallback_models", return_value=[]):
                result = svc._fetch_from_api()
                assert result.is_fallback is True

    def test_fetch_ollama_models_no_url(self):
        with patch("apps.core.llm.model_list_service.LLMConfig") as mock_cfg:
            mock_cfg.get_ollama_base_url.return_value = ""
            mock_cfg.get_ollama_model.return_value = ""
            result = ModelListService._fetch_ollama_models()
            assert result == []

    def test_fetch_ollama_models_with_context_length(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"model_info": {"ctx.context_length": 4096}}
        mock_resp.raise_for_status = MagicMock()
        with patch("apps.core.llm.model_list_service.LLMConfig") as mock_cfg, \
             patch("apps.core.llm.model_list_service.httpx") as mock_httpx:
            mock_cfg.get_ollama_base_url.return_value = "http://localhost:11434"
            mock_cfg.get_ollama_model.return_value = "qwen3:0.6b"
            mock_httpx.post.return_value = mock_resp
            mock_httpx.ConnectError = ConnectionError
            mock_httpx.TimeoutException = TimeoutError
            result = ModelListService._fetch_ollama_models()
            assert len(result) == 1
            assert result[0]["id"] == "qwen3:0.6b"

    def test_fetch_ollama_models_connection_error(self):
        with patch("apps.core.llm.model_list_service.LLMConfig") as mock_cfg, \
             patch("apps.core.llm.model_list_service.httpx") as mock_httpx:
            mock_cfg.get_ollama_base_url.return_value = "http://localhost:11434"
            mock_cfg.get_ollama_model.return_value = "qwen3:0.6b"
            mock_httpx.ConnectError = type("ConnectError", (Exception,), {})
            mock_httpx.TimeoutException = type("TimeoutException", (Exception,), {})
            mock_httpx.post.side_effect = mock_httpx.ConnectError()
            result = ModelListService._fetch_ollama_models()
            assert result == []

    def test_get_fallback_models(self):
        result = ModelListService._get_fallback_models()
        assert isinstance(result, list)

    def test_fetch_ollama_generic_exception_pass(self):
        """Generic exception in /api/show: caught by bare except, ctx_window stays 0,
        returns model list with default context_window=0."""
        with patch("apps.core.llm.model_list_service.LLMConfig") as mock_cfg, \
             patch("apps.core.llm.model_list_service.httpx") as mock_httpx:
            mock_cfg.get_ollama_base_url.return_value = "http://localhost:11434"
            mock_cfg.get_ollama_model.return_value = "qwen3:0.6b"
            mock_httpx.ConnectError = ConnectionError
            mock_httpx.TimeoutException = TimeoutError
            mock_httpx.post.side_effect = ValueError("bad json")
            result = ModelListService._fetch_ollama_models()
            # The generic except block just passes, so the model is still returned
            assert len(result) == 1
            assert result[0]["context_window"] == 0

    def test_fetch_ollama_no_model(self):
        with patch("apps.core.llm.model_list_service.LLMConfig") as mock_cfg:
            mock_cfg.get_ollama_base_url.return_value = "http://localhost:11434"
            mock_cfg.get_ollama_model.return_value = ""
            result = ModelListService._fetch_ollama_models()
            assert result == []

    def test_merge_system_config_models(self):
        api_models = [{"id": "gpt-4o", "name": "gpt-4o", "context_window": 128000}]
        with patch("apps.core.llm.model_list_service.LLMConfig") as mock_cfg:
            mock_cfg._get_system_config.side_effect = lambda k, d="": {
                "LLM_EXTRA_MODELS": "extra-model-1,extra-model-2",
            }.get(k, d)
            mock_cfg.get_ollama_model.return_value = "qwen3:0.6b"
            mock_cfg.get_openai_compatible_model.return_value = "kimi26"
            result = ModelListService._merge_system_config_models(api_models)
            ids = [m["id"] for m in result]
            assert "extra-model-1" in ids
            assert "extra-model-2" in ids
            assert "qwen3:0.6b" in ids

    def test_merge_system_config_models_empty_extra(self):
        api_models = [{"id": "gpt-4o", "name": "gpt-4o", "context_window": 100}]
        with patch("apps.core.llm.model_list_service.LLMConfig") as mock_cfg:
            mock_cfg._get_system_config.return_value = ""
            mock_cfg.get_ollama_model.return_value = ""
            mock_cfg.get_openai_compatible_model.return_value = ""
            result = ModelListService._merge_system_config_models(api_models)
            assert len(result) == 1

    def test_merge_deduplicates(self):
        api_models = [{"id": "gpt-4o", "name": "gpt-4o", "context_window": 100}]
        with patch("apps.core.llm.model_list_service.LLMConfig") as mock_cfg:
            mock_cfg._get_system_config.side_effect = lambda k, d="": {
                "LLM_EXTRA_MODELS": "gpt-4o",
            }.get(k, d)
            mock_cfg.get_ollama_model.return_value = ""
            mock_cfg.get_openai_compatible_model.return_value = ""
            result = ModelListService._merge_system_config_models(api_models)
            assert len(result) == 1

    def test_merge_system_config_whitespace_in_model_id(self):
        api_models = []
        with patch("apps.core.llm.model_list_service.LLMConfig") as mock_cfg:
            mock_cfg._get_system_config.side_effect = lambda k, d="": {
                "LLM_EXTRA_MODELS": "  , , model-x ",
            }.get(k, d)
            mock_cfg.get_ollama_model.return_value = ""
            mock_cfg.get_openai_compatible_model.return_value = ""
            result = ModelListService._merge_system_config_models(api_models)
            ids = [m["id"] for m in result]
            assert "model-x" in ids
            assert "" not in ids
