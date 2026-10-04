"""apps/core/llm/model_list_service.py 补充测试。

既有 test_model_list_service_coverage.py 已覆盖同步路径的基础分支，
本文件补齐异步路径（aget_result/aget_models/_amerge/_afetch）与
同步 get_result 的缓存半命中分支。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.core.llm.backends.base import OpenAIProviderConfig
from apps.core.llm.model_list_service import CACHE_KEY, CACHE_KEY_STATUS, ModelListResult, ModelListService


def _provider(name: str, models: list[str]) -> OpenAIProviderConfig:
    return OpenAIProviderConfig(
        name=name,
        base_url="http://x",
        api_keys=[],
        default_model=models[0] if models else "",
        extra_models=models[1:],
    )


class TestSyncGetResultCacheEdgeCases:
    def test_cached_models_without_status_refetches(self) -> None:
        """models 有缓存但 status 缺失时应重新 fetch 并回写缓存。"""
        svc = ModelListService(cache_ttl=60)
        api_models: list[dict[str, Any]] = []

        cache_mock = MagicMock()
        cache_mock.get.side_effect = lambda k: api_models if k == CACHE_KEY else None

        with (
            patch("apps.core.llm.model_list_service.cache", cache_mock),
            patch.object(
                svc,
                "_fetch_from_api",
                return_value=ModelListResult(models=api_models, is_fallback=True, error_message="baseline"),
            ) as mock_fetch,
            patch.object(ModelListService, "_merge_system_config_models", return_value=api_models),
        ):
            result = svc.get_result()

        assert result.is_fallback is True
        mock_fetch.assert_called_once()
        cache_mock.set.assert_any_call(CACHE_KEY_STATUS, {"is_fallback": True, "error_message": "baseline"}, 60)

    def test_cached_status_values_applied(self) -> None:
        svc = ModelListService(cache_ttl=120)
        models: list[dict[str, Any]] = [{"id": "m1"}]
        status = {"is_fallback": True, "error_message": "已降级"}

        cache_mock = MagicMock()
        cache_mock.get.side_effect = lambda k: models if k == CACHE_KEY else status

        with (
            patch("apps.core.llm.model_list_service.cache", cache_mock),
            patch.object(ModelListService, "_merge_system_config_models", return_value=models),
        ):
            result = svc.get_result()

        assert result.is_fallback is True
        assert result.error_message == "已降级"
        assert result.is_ok is False

    def test_fetch_from_api_returns_fallback_marker(self) -> None:
        svc = ModelListService()
        result = svc._fetch_from_api()
        assert result.is_fallback is True
        assert result.models == []
        assert "默认模型列表" in result.error_message

    def test_merge_prepends_new_models_before_api_models(self) -> None:
        api_models = [{"id": "api-1", "name": "api-1", "context_window": 1}]
        with patch("apps.core.llm.model_list_service.LLMConfig") as cfg:
            cfg._get_system_config.return_value = ""
            cfg.get_openai_compatible_model.return_value = "new-default"
            cfg._get_llm_providers.return_value = []
            result = ModelListService._merge_system_config_models(api_models)

        ids = [m["id"] for m in result]
        assert ids == ["new-default", "api-1"]

    def test_merge_includes_provider_models(self) -> None:
        with patch("apps.core.llm.model_list_service.LLMConfig") as cfg:
            cfg._get_system_config.return_value = ""
            cfg.get_openai_compatible_model.return_value = ""
            cfg._get_llm_providers.return_value = [_provider("p1", ["pm-1", "pm-2"]), _provider("p2", ["pm-1"])]
            result = ModelListService._merge_system_config_models([])

        ids = [m["id"] for m in result]
        assert ids == ["pm-1", "pm-2"]  # 跨平台去重


class TestAsyncGetResult:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_models(self) -> None:
        svc = ModelListService(cache_ttl=60)
        models: list[dict[str, Any]] = [{"id": "am-1"}]
        status = {"is_fallback": False, "error_message": ""}

        cache_mock = MagicMock()
        cache_mock.aget = AsyncMock(side_effect=lambda k: models if k == CACHE_KEY else status)
        cache_mock.aset = AsyncMock()

        with (
            patch("apps.core.llm.model_list_service.cache", cache_mock),
            patch.object(ModelListService, "_amerge_system_config_models", new_callable=AsyncMock, return_value=models),
        ):
            result = await svc.aget_result()

        assert result.models[0]["id"] == "am-1"
        assert result.is_fallback is False
        cache_mock.aset.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cache_miss_fetches_and_sets_cache(self) -> None:
        svc = ModelListService(cache_ttl=45)

        cache_mock = MagicMock()
        cache_mock.aget = AsyncMock(return_value=None)
        cache_mock.aset = AsyncMock()

        fallback_models: list[dict[str, Any]] = []
        with (
            patch("apps.core.llm.model_list_service.cache", cache_mock),
            patch.object(
                ModelListService,
                "_amerge_system_config_models",
                new_callable=AsyncMock,
                return_value=fallback_models,
            ),
        ):
            result = await svc.aget_result()

        assert result.is_fallback is True
        assert "默认模型列表" in result.error_message
        cache_mock.aset.assert_any_await(CACHE_KEY, [], 45)
        cache_mock.aset.assert_any_await(
            CACHE_KEY_STATUS, {"is_fallback": True, "error_message": result.error_message}, 45
        )

    @pytest.mark.asyncio
    async def test_cached_models_without_status_refetches(self) -> None:
        svc = ModelListService(cache_ttl=60)
        models: list[dict[str, Any]] = [{"id": "am-2"}]

        cache_mock = MagicMock()
        cache_mock.aget = AsyncMock(side_effect=lambda k: models if k == CACHE_KEY else None)
        cache_mock.aset = AsyncMock()

        with (
            patch("apps.core.llm.model_list_service.cache", cache_mock),
            patch.object(
                ModelListService,
                "_amerge_system_config_models",
                new_callable=AsyncMock,
                return_value=models,
            ) as mock_merge,
        ):
            result = await svc.aget_result()

        assert result.models[0]["id"] == "am-2"
        mock_merge.assert_awaited_once()
        cache_mock.aset.assert_awaited()

    @pytest.mark.asyncio
    async def test_aget_models_returns_list(self) -> None:
        svc = ModelListService()
        models: list[dict[str, Any]] = [{"id": "am-3"}]
        with (
            patch.object(
                svc,
                "aget_result",
                new_callable=AsyncMock,
                return_value=ModelListResult(models=models),
            ),
        ):
            result = await svc.aget_models()
        assert result == models


class TestAsyncMerge:
    @pytest.mark.asyncio
    async def test_merges_extra_default_and_providers(self) -> None:
        cfg = MagicMock()
        cfg._get_system_config_async = AsyncMock(
            side_effect=lambda k, d="": {"LLM_EXTRA_MODELS": " , ex-1 ,ex-2"}.get(k, d)
        )
        cfg.get_openai_compatible_model_async = AsyncMock(return_value="def-1")
        cfg._aget_llm_providers = AsyncMock(return_value=[_provider("p1", ["def-1", "pv-1"])])

        with patch("apps.core.llm.model_list_service.LLMConfig", cfg):
            result = await ModelListService._amerge_system_config_models([])

        ids = [m["id"] for m in result]
        assert ids == ["ex-1", "ex-2", "def-1", "pv-1"]

    @pytest.mark.asyncio
    async def test_nothing_to_merge_returns_api_models(self) -> None:
        cfg = MagicMock()
        cfg._get_system_config_async = AsyncMock(return_value="")
        cfg.get_openai_compatible_model_async = AsyncMock(return_value="")
        cfg._aget_llm_providers = AsyncMock(return_value=[])

        api_models = [{"id": "only-1"}]
        with patch("apps.core.llm.model_list_service.LLMConfig", cfg):
            result = await ModelListService._amerge_system_config_models(api_models)

        assert result == api_models


class TestAsyncFetchFromApi:
    @pytest.mark.asyncio
    async def test_afetch_returns_fallback_marker(self) -> None:
        svc = ModelListService()
        result = await svc._afetch_from_api()
        assert result.is_fallback is True
        assert result.models == []
