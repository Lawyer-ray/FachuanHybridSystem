"""
占位符 Admin 服务

处理 Admin 层的占位符业务逻辑，包括代码占位符同步、查询集过滤和占位符复制。

Requirements: 2.6, 2.7, 2.8
"""

from __future__ import annotations

import logging
from typing import Any

from django.db.models import QuerySet

from apps.documents.services.code_placeholder_registry import CodePlaceholderDefinition

logger = logging.getLogger("apps.documents")


class PlaceholderAdminService:
    """占位符 Admin 服务"""

    def ensure_code_placeholders(
        self,
        definitions: dict[str, CodePlaceholderDefinition],
    ) -> None:
        """
        同步代码占位符：根据定义批量创建缺失的占位符记录。

        Args:
            definitions: 代码占位符定义字典 {key: CodePlaceholderDefinition}
        """
        from apps.documents.models import Placeholder

        existing_keys: set[str] = set(
            Placeholder.objects.values_list("key", flat=True)
        )
        to_create: list[Placeholder] = []
        for key, definition in definitions.items():
            if key in existing_keys:
                continue
            to_create.append(
                Placeholder(
                    key=key,
                    display_name=definition.display_name or key,
                    example_value=definition.example_value or "",
                    description=definition.description or "",
                    is_active=True,
                )
            )
        if to_create:
            Placeholder.objects.bulk_create(to_create, ignore_conflicts=True)

    def get_filtered_queryset(
        self,
        base_qs: QuerySet[Any],
        code_keys: list[str],
    ) -> QuerySet[Any]:
        """
        返回按代码占位符 key 过滤后的查询集。

        Args:
            base_qs: 基础查询集
            code_keys: 代码占位符 key 列表

        Returns:
            过滤后的查询集
        """
        return base_qs.filter(key__in=code_keys)

    def duplicate_placeholder(self, placeholder: Any) -> Any:
        """
        复制占位符并生成唯一 key。

        副本默认禁用（is_active=False）。

        Args:
            placeholder: 要复制的占位符实例

        Returns:
            新创建的 Placeholder 实例
        """
        from apps.documents.models import Placeholder

        new_key: str = f"{placeholder.key}_copy"
        suffix: int = 1
        while Placeholder.objects.filter(key=new_key).exists():
            new_key = f"{placeholder.key}_copy_{suffix}"
            suffix += 1

        return Placeholder.objects.create(
            key=new_key,
            display_name=f"{placeholder.display_name} (副本)",
            example_value=placeholder.example_value,
            description=placeholder.description,
            is_active=False,
        )
