"""
Prompt 版本服务适配器

实现 IPromptVersionService 接口,供其他模块(如 automation 模块)调用.
用于解耦 court_pleading_signals_service.py 对 PromptVersion 模型的直接依赖.

Requirements: 6.5, 4.3
"""

import logging
from typing import Any

from django.core.cache import cache

from apps.core.infrastructure import CacheKeys, CacheTimeout

logger = logging.getLogger(__name__)


class PromptVersionServiceAdapter:
    _MISSING_SENTINEL = "__prompt_version_missing__"

    """
    Prompt 版本服务适配器

    实现 IPromptVersionService 接口,提供 Prompt 模板查询功能给其他模块使用.
    使用延迟导入避免循环依赖问题.

    Requirements: 6.5, 4.3
    """

    def get_active_prompt_template(self, name: str) -> Any:
        """
        获取激活的 Prompt 模板

        根据 Prompt 名称查找激活状态的模板,返回模板内容.

        Args:
            name: Prompt 名称(如 'complaint', 'defense')

        Returns:
            模板内容字符串,不存在返回 None

        Requirements: 6.2, 4.5
        """
        cache_key = CacheKeys.prompt_version_active(name)
        cached = cache.get(cache_key)
        if cached is not None:
            if cached == self._MISSING_SENTINEL:
                return None
            return cached

        template = self.get_prompt_template_internal(name)
        if template is None:
            cache.set(cache_key, self._MISSING_SENTINEL, timeout=CacheTimeout.get_medium())
            return None

        cache.set(cache_key, template, timeout=CacheTimeout.get_long())
        return template

    def get_prompt_template_internal(self, name: str) -> Any:
        """
        内部方法:获取 Prompt 模板(无权限检查)

        供 Adapter 调用,跳过权限检查直接获取模板内容.
        查询 PromptVersion 模型中 name 匹配且 is_active=True 的记录.

        Args:
            name: Prompt 名称(如 'complaint', 'defense')

        Returns:
            模板内容字符串,不存在返回 None

        Requirements: 6.2, 4.5
        """
        try:
            from apps.documents.models import PromptVersion

            prompt_version = PromptVersion.objects.filter(name=name, is_active=True).first()

            if prompt_version:
                logger.debug(f"获取 Prompt 模板成功: {name} (版本: {prompt_version.version})")
                return prompt_version.template

            logger.debug(f"未找到激活的 Prompt 模板: {name}")
            return None

        except Exception:
            logger.exception("get_prompt_template_internal_failed", extra={"prompt_name": name})
            raise
