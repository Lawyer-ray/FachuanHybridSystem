"""Tests for apps.core.llm.model_list_service — ModelListService + ModelListResult + _make_model."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.llm.model_list_service import ModelListResult, ModelListService, _make_model


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

    def test_get_fallback_models(self):
        result = ModelListService._get_fallback_models()
        assert isinstance(result, list)

    def test_merge_system_config_models(self):
        api_models = [{"id": "gpt-4o", "name": "gpt-4o", "context_window": 128000}]
        with patch("apps.core.llm.model_list_service.LLMConfig") as mock_cfg:
            mock_cfg._get_system_config.side_effect = lambda k, d="": {
                "LLM_EXTRA_MODELS": "extra-model-1,extra-model-2",
            }.get(k, d)
            mock_cfg.get_openai_compatible_model.return_value = "kimi26"
            result = ModelListService._merge_system_config_models(api_models)
            ids = [m["id"] for m in result]
            assert "extra-model-1" in ids
            assert "extra-model-2" in ids
            assert "kimi26" in ids

    def test_merge_system_config_models_empty_extra(self):
        api_models = [{"id": "gpt-4o", "name": "gpt-4o", "context_window": 100}]
        with patch("apps.core.llm.model_list_service.LLMConfig") as mock_cfg:
            mock_cfg._get_system_config.return_value = ""
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
