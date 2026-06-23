from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx
from django.core.cache import cache

from apps.core.llm.config import LLMConfig

logger = logging.getLogger(__name__)

CACHE_KEY = "llm_model_list"
CACHE_KEY_STATUS = "llm_model_list_status"
DEFAULT_CACHE_TTL = 3600

# 预置默认模型列表（API 不可用时降级）
_FALLBACK_MODELS: list[dict[str, Any]] = []

# 已知模型的上下文窗口大小（API 未返回时的兜底）
_KNOWN_CONTEXT_WINDOWS: dict[str, int] = {
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4-turbo": 128000,
    "gpt-4": 8192,
    "gpt-3.5-turbo": 16385,
    "claude-sonnet-4": 200000,
    "claude-haiku-4-5": 200000,
    "deepseek-chat": 65536,
    "deepseek-reasoner": 65536,
    "kimi26": 262144,
}


def _make_model(model_id: str, context_window: int = 0) -> dict[str, Any]:
    """构建标准模型字典"""
    ctx = context_window or _KNOWN_CONTEXT_WINDOWS.get(model_id, 0)
    return {
        "id": model_id,
        "name": model_id.split("/")[-1].split(":")[-1],
        "context_window": ctx,
    }


@dataclass
class ModelListResult:
    """模型列表获取结果"""

    models: list[dict[str, Any]] = field(default_factory=list)
    is_fallback: bool = False
    error_message: str = ""

    @property
    def is_ok(self) -> bool:
        return not self.is_fallback


class ModelListService:
    """模型列表公共服务（OpenAI-compatible + Ollama）"""

    def __init__(self, cache_ttl: int = DEFAULT_CACHE_TTL) -> None:
        self._cache_ttl = cache_ttl

    def get_models(self) -> list[dict[str, Any]]:
        """获取可用模型列表，优先从缓存读取"""
        result = self.get_result()
        return result.models

    def get_result(self) -> ModelListResult:
        """获取模型列表及连接状态，优先从缓存读取。

        自动合并 SystemConfig 中配置的额外模型（LLM_EXTRA_MODELS 等），
        确保所有消费者都能看到完整模型列表。
        """
        cached: list[dict[str, Any]] | None = cache.get(CACHE_KEY)
        cached_status: dict[str, Any] | None = cache.get(CACHE_KEY_STATUS)
        if cached is not None and cached_status is not None:
            result = ModelListResult(
                models=cached,
                is_fallback=cached_status.get("is_fallback", False),
                error_message=cached_status.get("error_message", ""),
            )
        else:
            result = self._fetch_from_api()
            cache.set(CACHE_KEY, result.models, self._cache_ttl)
            cache.set(
                CACHE_KEY_STATUS,
                {"is_fallback": result.is_fallback, "error_message": result.error_message},
                self._cache_ttl,
            )

        # 合并 SystemConfig 中的模型（LLM_EXTRA_MODELS 等）
        result.models = self._merge_system_config_models(result.models)
        return result

    @staticmethod
    def _merge_system_config_models(api_models: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """将 SystemConfig 中用户显式配置的模型合并到 API 模型列表中."""
        seen: set[str] = {m.get("id", "") for m in api_models}
        merged: list[dict[str, Any]] = []

        def _add(model_id: str) -> None:
            mid = model_id.strip()
            if mid and mid not in seen:
                seen.add(mid)
                merged.append(_make_model(mid))

        # 1. LLM_EXTRA_MODELS（用户在 SystemConfig 中配置的额外模型）
        extra_raw = LLMConfig._get_system_config("LLM_EXTRA_MODELS", "")
        if extra_raw:
            for part in extra_raw.split(","):
                _add(part)

        # 2. 各后端的默认模型（用户在 SystemConfig 中配置的默认模型）
        for default_model in [
            LLMConfig.get_ollama_model(),
            LLMConfig.get_openai_compatible_model(),
        ]:
            if default_model:
                _add(default_model)

        return merged + api_models

    def _fetch_from_api(self) -> ModelListResult:
        """从各后端获取模型列表，合并结果"""
        configs = LLMConfig.get_backend_configs()
        all_models: list[dict[str, Any]] = []

        if configs.get("ollama") and configs["ollama"].enabled:
            all_models.extend(self._fetch_ollama_models())

        if all_models:
            return ModelListResult(models=all_models)

        return ModelListResult(
            models=self._get_fallback_models(),
            is_fallback=True,
            error_message="所有后端均不可用，使用默认模型列表",
        )

    @staticmethod
    def _fetch_ollama_models() -> list[dict[str, Any]]:
        """获取 Ollama 模型的 context_window

        只查询 SystemConfig 中配置的 Ollama 模型，不自动发现所有模型。
        通过 /api/show 获取 context_length。
        """
        ollama_url = LLMConfig.get_ollama_base_url()
        ollama_model = LLMConfig.get_ollama_model()
        if not ollama_url or not ollama_model:
            return []

        # 查询 /api/show 获取 context_length
        ctx_window = 0
        try:
            resp = httpx.post(
                f"{ollama_url}/api/show",
                json={"name": ollama_model},
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            for key, val in data.get("model_info", {}).items():
                if key.endswith(".context_length"):
                    ctx_window = int(val)
                    break
        except (httpx.ConnectError, httpx.TimeoutException):
            return []
        except Exception:
            pass

        return [_make_model(ollama_model, ctx_window)]

    @staticmethod
    async def _afetch_ollama_models() -> list[dict[str, Any]]:
        """异步版本。获取 Ollama 模型的 context_window。

        只查询 SystemConfig 中配置的 Ollama 模型，不自动发现所有模型。
        通过 /api/show 获取 context_length。
        """
        ollama_url = LLMConfig.get_ollama_base_url()
        ollama_model = LLMConfig.get_ollama_model()
        if not ollama_url or not ollama_model:
            return []

        # 查询 /api/show 获取 context_length
        ctx_window = 0
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(f"{ollama_url}/api/show", json={"name": ollama_model})
                resp.raise_for_status()
                data = resp.json()
            for key, val in data.get("model_info", {}).items():
                if key.endswith(".context_length"):
                    ctx_window = int(val)
                    break
        except (httpx.ConnectError, httpx.TimeoutException):
            return []
        except Exception:
            pass

        return [_make_model(ollama_model, ctx_window)]

    async def aget_result(self) -> ModelListResult:
        """异步版本。获取模型列表及连接状态，优先从缓存读取。"""
        cached: list[dict[str, Any]] | None = cache.get(CACHE_KEY)
        cached_status: dict[str, Any] | None = cache.get(CACHE_KEY_STATUS)
        if cached is not None and cached_status is not None:
            result = ModelListResult(
                models=cached,
                is_fallback=cached_status.get("is_fallback", False),
                error_message=cached_status.get("error_message", ""),
            )
        else:
            result = await self._afetch_from_api()
            cache.set(CACHE_KEY, result.models, self._cache_ttl)
            cache.set(
                CACHE_KEY_STATUS,
                {"is_fallback": result.is_fallback, "error_message": result.error_message},
                self._cache_ttl,
            )

        result.models = self._merge_system_config_models(result.models)
        return result

    async def aget_models(self) -> list[dict[str, Any]]:
        """异步版本。获取可用模型列表，优先从缓存读取。"""
        result = await self.aget_result()
        return result.models

    async def _afetch_from_api(self) -> ModelListResult:
        """异步版本。从各后端获取模型列表，合并结果。"""
        configs = LLMConfig.get_backend_configs()
        all_models: list[dict[str, Any]] = []

        if configs.get("ollama") and configs["ollama"].enabled:
            all_models.extend(await self._afetch_ollama_models())

        if all_models:
            return ModelListResult(models=all_models)

        return ModelListResult(
            models=self._get_fallback_models(),
            is_fallback=True,
            error_message="所有后端均不可用，使用默认模型列表",
        )

    @staticmethod
    def _get_fallback_models() -> list[dict[str, Any]]:
        """返回预置默认模型列表"""
        return list(_FALLBACK_MODELS)
