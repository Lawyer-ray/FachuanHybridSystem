"""LLM 平台（供应商）配置服务。

从 LLMProvider 模型读取启用的 OpenAI-compatible 平台配置，带 TTL 缓存。
同步/异步双通道，供 LLMConfig 与后端使用。
"""

from __future__ import annotations

import logging
import time
from typing import ClassVar

from apps.core.llm.backends.base import OpenAIProviderConfig

logger = logging.getLogger("apps.core.services.llm_provider")


class LLMProviderService:
    """LLM 平台配置服务（进程内 TTL 缓存）。"""

    _CACHE_TTL_SECONDS: ClassVar[float] = 300.0
    _cache: ClassVar[tuple[list[OpenAIProviderConfig], float] | None] = None

    @classmethod
    def invalidate_cache(cls) -> None:
        """清空平台配置缓存（Admin 保存/删除后调用，使改动立即生效）。"""
        cls._cache = None

    @classmethod
    def get_providers(cls) -> list[OpenAIProviderConfig]:
        """同步读取启用的平台配置列表（带缓存）。"""
        cached = cls._cache
        if cached is not None:
            value, cached_at = cached
            if time.monotonic() - cached_at <= cls._CACHE_TTL_SECONDS:
                return value

        try:
            providers = cls._load_from_db()
        except Exception:
            logger.warning("[LLMProviderService] 读取平台配置失败", exc_info=True)
            providers = []
        cls._cache = (providers, time.monotonic())
        return providers

    @classmethod
    async def aget_providers(cls) -> list[OpenAIProviderConfig]:
        """异步读取启用的平台配置列表（带缓存）。"""
        cached = cls._cache
        if cached is not None:
            value, cached_at = cached
            if time.monotonic() - cached_at <= cls._CACHE_TTL_SECONDS:
                return value

        from asgiref.sync import sync_to_async

        try:
            providers = await sync_to_async(cls._load_from_db)()
        except Exception:
            logger.warning("[LLMProviderService] 异步读取平台配置失败", exc_info=True)
            providers = []
        cls._cache = (providers, time.monotonic())
        return providers

    @staticmethod
    def _load_from_db() -> list[OpenAIProviderConfig]:
        try:
            from apps.core.models import LLMProvider

            rows = list(LLMProvider.objects.filter(enabled=True))
        except Exception:
            logger.warning("[LLMProviderService] 读取平台配置失败", exc_info=True)
            return []

        providers: list[OpenAIProviderConfig] = []
        for row in rows:
            providers.append(
                OpenAIProviderConfig(
                    name=str(row.name),
                    base_url=(row.base_url or "").strip(),
                    api_keys=row.parsed_api_keys(),
                    default_model=(row.default_model or "").strip(),
                    extra_models=row.parsed_models(),
                    embedding_model=(row.embedding_model or "").strip(),
                    timeout=int(row.timeout or 120),
                    concurrency_per_key=int(row.concurrency_per_key or 0),
                    priority=int(row.priority or 10),
                    enabled=bool(row.enabled),
                )
            )
        providers.sort(key=lambda p: (p.priority, p.name))
        return providers

    @classmethod
    def initialize_default(cls) -> tuple[int, int]:
        """初始化基础 AI 平台数据（律所 kimi 默认平台模板）。

        幂等：仅当表为空时写入一条基础平台；已存在任何平台则跳过。
        返回 (created, skipped)。
        """
        from apps.core.llm.config import LLMConfig
        from apps.core.models import LLMProvider

        if LLMProvider.objects.exists():
            return (0, 1)
        LLMProvider.objects.create(
            name="律所 kimi",
            base_url=LLMConfig.DEFAULT_OPENAI_COMPATIBLE_BASE_URL,
            api_keys="",
            default_model=LLMConfig.DEFAULT_OPENAI_COMPATIBLE_MODEL,
            embedding_model="",
            priority=10,
            concurrency_per_key=3,
            enabled=True,
        )
        cls.invalidate_cache()
        return (1, 0)
