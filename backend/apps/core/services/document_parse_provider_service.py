"""文档解析平台（供应商）配置服务。

从 DocumentParseProvider 模型读取启用的解析平台配置，带进程内 TTL 缓存。
参考 LLMProviderService 的实现模式，供解析后端与 ParserFactory 使用。
"""

from __future__ import annotations

import logging
import time
from typing import ClassVar

from apps.core.models import DocumentParseProvider

logger = logging.getLogger("apps.core.services.document_parse_provider")


class ParseProviderService:
    """解析平台配置服务（进程内 TTL 缓存）。"""

    _CACHE_TTL_SECONDS: ClassVar[float] = 300.0
    _cache: ClassVar[tuple[list[DocumentParseProvider], float] | None] = None

    @classmethod
    def invalidate_cache(cls) -> None:
        """清空平台配置缓存（Admin 保存/删除后调用，使改动立即生效）。"""
        cls._cache = None

    @classmethod
    def get_providers(cls) -> list[DocumentParseProvider]:
        """同步读取启用的解析平台列表（带缓存，按优先级排序）。"""
        cached = cls._cache
        if cached is not None:
            value, cached_at = cached
            if time.monotonic() - cached_at <= cls._CACHE_TTL_SECONDS:
                return value

        try:
            providers = cls._load_from_db()
        except Exception:
            logger.warning("[ParseProviderService] 读取解析平台配置失败", exc_info=True)
            providers = []
        cls._cache = (providers, time.monotonic())
        return providers

    @classmethod
    def get_provider(cls, provider_type: str) -> DocumentParseProvider | None:
        """按服务类型获取优先级最高的启用平台。

        Args:
            provider_type: DocumentParseProvider.ProviderType 值（textin / mineru）。

        Returns:
            匹配的启用平台；未配置时返回 None。
        """
        candidates = [p for p in cls.get_providers() if p.provider_type == provider_type]
        if not candidates:
            return None
        return min(candidates, key=lambda p: (p.priority, p.pk))

    @staticmethod
    def _load_from_db() -> list[DocumentParseProvider]:
        try:
            rows = list(DocumentParseProvider.objects.filter(enabled=True))
        except Exception:
            logger.warning("[ParseProviderService] 读取解析平台配置失败", exc_info=True)
            return []
        rows.sort(key=lambda p: (p.priority, p.pk))
        return rows
