from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx
from django.core.cache import cache

from apps.core.llm.config import LLMConfig

logger = logging.getLogger(__name__)

CACHE_KEY = "siliconflow_model_list"
CACHE_KEY_STATUS = "siliconflow_model_list_status"
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
    "Qwen/Qwen3-8B": 32768,
    "Qwen/Qwen2.5-7B-Instruct": 32768,
    "Qwen/Qwen2.5-72B-Instruct": 131072,
    "THUDM/glm-4-9b-chat": 32768,
    "deepseek-ai/DeepSeek-V3": 65536,
    "deepseek-ai/DeepSeek-R1": 65536,
    "Qwen3.5-397B-A17B": 262144,
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
    """模型列表公共服务（SiliconFlow + Ollama）"""

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
            LLMConfig.get_default_model(),
            LLMConfig.get_ollama_model(),
            LLMConfig.get_openai_compatible_model(),
        ]:
            if default_model:
                _add(default_model)

        return merged + api_models

    def _fetch_from_api(self) -> ModelListResult:
        """从各后端获取模型列表，合并结果"""
        sf_models = self._fetch_siliconflow_models()
        ollama_models = self._fetch_ollama_models()

        all_models = sf_models + ollama_models
        if all_models:
            return ModelListResult(models=all_models)

        return ModelListResult(
            models=self._get_fallback_models(),
            is_fallback=True,
            error_message="所有后端均不可用，使用默认模型列表",
        )

    def _fetch_siliconflow_models(self) -> list[dict[str, Any]]:
        """调用 SiliconFlow GET /v1/models API，提取 context_window"""
        api_key = LLMConfig.get_api_key()
        base_url = LLMConfig.get_base_url()
        if not api_key:
            logger.warning("SILICONFLOW_API_KEY 未配置")
            return []

        url = f"{base_url.rstrip('/')}/models"
        try:
            resp = httpx.get(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                params={"sub_type": "chat"},
                timeout=15.0,
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            models: list[dict[str, Any]] = []
            for m in data.get("data", []):
                if not m.get("id"):
                    continue
                model_id: str = m["id"]
                # SiliconFlow 返回 max_model_len 字段
                ctx = m.get("max_model_len") or m.get("context_length") or 0
                models.append(_make_model(model_id, int(ctx) if ctx else 0))
            if models:
                logger.info("从 SiliconFlow API 获取到 %d 个模型", len(models))
            return models
        except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as exc:
            logger.warning("SiliconFlow API 不可用: %s", exc)
            return []
        except Exception:
            logger.exception("获取 SiliconFlow 模型列表时发生未知错误")
            return []

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
    def _get_fallback_models() -> list[dict[str, Any]]:
        """返回预置默认模型列表"""
        return list(_FALLBACK_MODELS)
