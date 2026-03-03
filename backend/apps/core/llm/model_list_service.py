from __future__ import annotations

import logging
from typing import Any

import httpx
from django.core.cache import cache

from apps.core.llm.config import LLMConfig

logger = logging.getLogger(__name__)

CACHE_KEY = "siliconflow_model_list"
DEFAULT_CACHE_TTL = 3600

# 预置默认模型列表（API 不可用时降级）
_FALLBACK_MODELS: list[dict[str, str]] = [
    {"id": "Qwen/Qwen3-8B", "name": "Qwen3-8B"},
    {"id": "Qwen/Qwen2.5-7B-Instruct", "name": "Qwen2.5-7B-Instruct"},
    {"id": "THUDM/glm-4-9b-chat", "name": "GLM-4-9B-Chat"},
    {"id": "deepseek-ai/DeepSeek-V3", "name": "DeepSeek-V3"},
]


class ModelListService:
    """硅基流动模型列表公共服务"""

    def __init__(self, cache_ttl: int = DEFAULT_CACHE_TTL) -> None:
        self._cache_ttl = cache_ttl

    def get_models(self) -> list[dict[str, str]]:
        """获取可用模型列表，优先从缓存读取"""
        cached: list[dict[str, str]] | None = cache.get(CACHE_KEY)
        if cached is not None:
            return cached

        models = self._fetch_from_api()
        if models:
            cache.set(CACHE_KEY, models, self._cache_ttl)
        return models

    def _fetch_from_api(self) -> list[dict[str, str]]:
        """调用 SiliconFlow GET /v1/models API"""
        api_key = LLMConfig.get_api_key()
        base_url = LLMConfig.get_base_url()
        if not api_key:
            logger.warning("SILICONFLOW_API_KEY 未配置，使用默认模型列表")
            return self._get_fallback_models()

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
            models: list[dict[str, str]] = [
                {"id": m["id"], "name": m.get("id", "").split("/")[-1]} for m in data.get("data", []) if m.get("id")
            ]
            if models:
                logger.info("从 SiliconFlow API 获取到 %d 个模型", len(models))
                return models
        except Exception:
            logger.exception("获取 SiliconFlow 模型列表失败")

        return self._get_fallback_models()

    @staticmethod
    def _get_fallback_models() -> list[dict[str, str]]:
        """返回预置默认模型列表"""
        return list(_FALLBACK_MODELS)
