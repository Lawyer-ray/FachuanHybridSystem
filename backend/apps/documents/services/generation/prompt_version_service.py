"""Business logic services."""

from __future__ import annotations

import logging

"""
Prompt 版本管理服务

本模块提供 Prompt 模板版本的管理功能,包括版本激活、加载等.

Requirements: 5.3, 5.4, 5.5
"""


from typing import TYPE_CHECKING, Any

from django.db import transaction

from apps.core.exceptions import NotFoundError

if TYPE_CHECKING:
    from apps.documents.models import PromptVersion

logger = logging.getLogger("apps.documents.generation")


class PromptVersionService:
    """
    Prompt 版本管理服务

    提供 Prompt 模板版本的管理功能,包括:
    - 获取活跃的 Prompt 模板
    - 激活指定版本
    - 创建新版本
    """

    def get_active_template(self, name: str) -> Any:
        """
        获取活跃的 Prompt 模板

        Args:
            name: Prompt 名称(如:complaint, defense)

        Returns:
            活跃版本的模板内容,如果不存在则返回 None

        Requirements: 5.3
        """
        from apps.documents.models import PromptVersion

        version = PromptVersion.objects.filter(name=name, is_active=True).first()

        if version:
            logger.info("加载活跃 Prompt 版本", extra={"prompt_name": name, "version": version.version})
            return version.template

        logger.warning("未找到活跃的 Prompt 版本", extra={"prompt_name": name})
        return None

    @transaction.atomic
    def activate_version(self, version_id: int) -> None:
        """
        激活指定版本,停用其他版本

        同一名称下只能有一个激活版本.

        Args:
            version_id: 要激活的版本 ID

        Raises:
            NotFoundError: 版本不存在

        Requirements: 5.4
        """
        from apps.documents.models import PromptVersion

        try:
            version = PromptVersion.objects.get(id=version_id)
        except PromptVersion.DoesNotExist:
            raise NotFoundError(
                message="Prompt 版本不存在",
                code="PROMPT_VERSION_NOT_FOUND",
                errors={"version_id": f"ID 为 {version_id} 的版本不存在"},
            ) from None

        # 停用同名的其他版本
        PromptVersion.objects.filter(name=version.name).update(is_active=False)

        # 激活指定版本
        version.is_active = True
        version.save(update_fields=["is_active"])

        from django.core.cache import cache

        from apps.core.infrastructure import CacheKeys

        cache.delete(CacheKeys.prompt_version_active(version.name))

        logger.info(
            "激活 Prompt 版本",
            extra={"prompt_name": version.name, "version": version.version, "version_id": version_id},
        )

    def create_version(self, name: str, version: str, template: str, description: str = "") -> PromptVersion:
        """
        创建新的 Prompt 版本

        Args:
            name: Prompt 名称
            version: 版本号
            template: 模板内容
            description: 版本说明

        Returns:
            创建的 PromptVersion 实例

        Requirements: 5.5
        """
        from apps.documents.models import PromptVersion

        prompt_version = PromptVersion.objects.create(
            name=name, version=version, template=template, description=description, is_active=False
        )

        logger.info(
            "创建 Prompt 版本",
            extra={"prompt_name": name, "version": version, "version_id": prompt_version.pk},
        )

        return prompt_version
