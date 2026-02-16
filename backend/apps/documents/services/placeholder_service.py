"""
占位符服务

提供占位符的管理和替换功能.
占位符定义统一管理,具体数据替换由外部脚本实现.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8
"""

import logging
from typing import Any, cast

from django.db import IntegrityError, transaction

from apps.core.exceptions import NotFoundError, ValidationException
from apps.documents.models import Placeholder

logger = logging.getLogger(__name__)


class PlaceholderService:
    """
    占位符服务

    提供占位符的注册、查询、验证和格式化功能.
    """

    def create_placeholder(
        self,
        key: str,
        display_name: str,
        example_value: str = "",
        description: str = "",
        is_active: bool = True,
    ) -> Placeholder:
        """
        创建新的占位符

        Args:
            key: 占位符键(唯一)
            display_name: 显示名称
            example_value: 示例值
            description: 说明
            is_active: 是否启用

        Returns:
            创建的占位符对象

        Raises:
            ValidationException: 参数验证失败

        Requirements: 3.1, 3.4
        """
        # 验证必填参数
        if not key or not display_name:
            raise ValidationException(
                message="占位符键和显示名称不能为空",
                code="INVALID_PLACEHOLDER_DATA",
                errors={"key": "占位符键不能为空", "display_name": "显示名称不能为空"},
            )

        try:
            placeholder = Placeholder.objects.create(
                key=key,
                display_name=display_name,
                example_value=example_value,
                description=description,
                is_active=is_active,
            )
            logger.info(f"创建占位符: {key}")
            return placeholder
        except IntegrityError as e:
            raise ValidationException(
                message="创建占位符失败",
                code="PLACEHOLDER_CREATE_FAILED",
                errors={"key": f"占位符键 '{key}' 可能已存在: {e!s}"},
            ) from e

    def register_placeholder(
        self,
        key: str,
        display_name: str,
        example_value: str = "",
        description: str = "",
    ) -> Placeholder:
        """
        注册新的占位符(兼容旧接口)

        Args:
            key: 占位符键(唯一)
            display_name: 显示名称
            example_value: 示例值
            description: 说明

        Returns:
            创建的占位符对象

        Raises:
            ValidationException: 参数验证失败

        Requirements: 3.1, 3.4
        """
        return self.create_placeholder(
            key=key,
            display_name=display_name,
            example_value=example_value,
            description=description,
        )

    def get_placeholder_by_id(self, placeholder_id: int) -> Placeholder:
        """
        根据 ID 获取占位符

        Args:
            placeholder_id: 占位符 ID

        Returns:
            Placeholder 实例

        Raises:
            NotFoundError: 占位符不存在
        """
        try:
            return Placeholder.objects.get(id=placeholder_id)
        except Placeholder.DoesNotExist:
            raise NotFoundError(
                message="占位符不存在",
                code="PLACEHOLDER_NOT_FOUND",
                errors={"placeholder_id": f"ID 为 {placeholder_id} 的占位符不存在"},
            ) from None

    def get_placeholder_by_key(self, key: str) -> Placeholder:
        """
        根据键获取占位符

        Args:
            key: 占位符键

        Returns:
            Placeholder 实例

        Raises:
            NotFoundError: 占位符不存在
        """
        try:
            return Placeholder.objects.get(key=key)
        except Placeholder.DoesNotExist:
            raise NotFoundError(
                message="占位符不存在",
                code="PLACEHOLDER_NOT_FOUND",
                errors={"key": f"键为 '{key}' 的占位符不存在"},
            ) from None

    def update_placeholder(
        self,
        placeholder_id: int,
        key: str | None = None,
        display_name: str | None = None,
        example_value: str | None = None,
        description: str | None = None,
        is_active: bool | None = None,
    ) -> Placeholder:
        """
        更新占位符

        Args:
            placeholder_id: 占位符 ID
            key: 新键
            display_name: 新显示名称
            example_value: 新示例值
            description: 新说明
            is_active: 新启用状态

        Returns:
            更新后的 Placeholder 实例

        Raises:
            NotFoundError: 占位符不存在
            ValidationException: 验证失败
        """
        try:
            placeholder = Placeholder.objects.get(id=placeholder_id)
        except Placeholder.DoesNotExist:
            raise NotFoundError(
                message="占位符不存在",
                code="PLACEHOLDER_NOT_FOUND",
                errors={"placeholder_id": f"ID 为 {placeholder_id} 的占位符不存在"},
            ) from None

        if key is not None:
            placeholder.key = key
        if display_name is not None:
            placeholder.display_name = display_name
        if example_value is not None:
            placeholder.example_value = example_value
        if description is not None:
            placeholder.description = description
        if is_active is not None:
            placeholder.is_active = is_active

        try:
            placeholder.save()
            logger.info(f"更新占位符: {placeholder.key} (ID: {cast(int, placeholder.pk)})")
            return placeholder
        except IntegrityError as e:
            raise ValidationException(
                message="更新占位符失败",
                code="PLACEHOLDER_UPDATE_FAILED",
                errors={"key": f"占位符键可能已存在: {e!s}"},
            ) from e

    def delete_placeholder(self, placeholder_id: int) -> bool:
        """
        删除占位符(软删除)

        Args:
            placeholder_id: 占位符 ID

        Returns:
            是否成功

        Raises:
            NotFoundError: 占位符不存在
        """
        try:
            placeholder = Placeholder.objects.get(id=placeholder_id)
        except Placeholder.DoesNotExist:
            raise NotFoundError(
                message="占位符不存在",
                code="PLACEHOLDER_NOT_FOUND",
                errors={"placeholder_id": f"ID 为 {placeholder_id} 的占位符不存在"},
            ) from None

        placeholder.is_active = False
        placeholder.save(update_fields=["is_active"])
        logger.info(f"软删除占位符: {placeholder.key} (ID: {cast(int, placeholder.pk)})")
        return True

    def list_placeholders(self, is_active: bool | None = None) -> list[Placeholder]:
        """
        列出占位符

        Args:
            is_active: 启用状态过滤,None 表示只返回活跃的

        Returns:
            占位符列表

        Requirements: 3.6
        """
        queryset = Placeholder.objects.all()
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        else:
            queryset = queryset.filter(is_active=True)
        return list(queryset.order_by("key"))

    def get_placeholder_mapping(self) -> dict[str, Placeholder]:
        """
        获取所有活跃占位符的键值映射

        Returns:
            键到占位符对象的映射字典

        Requirements: 3.8
        """
        placeholders = Placeholder.objects.filter(is_active=True)
        return {p.key: p for p in placeholders}

    @transaction.atomic
    def bulk_update_placeholders(self, updates: list[dict[str, Any]]) -> int:
        """
        批量更新占位符

        Args:
            updates: 更新数据列表,每个元素包含 key 和要更新的字段

        Returns:
            更新的占位符数量

        Requirements: 3.4
        """
        updated_count = 0
        for update_data in updates:
            key = update_data.pop("key", None)
            if not key:
                continue

            try:
                placeholder = Placeholder.objects.get(key=key)
                for field, value in update_data.items():
                    if hasattr(placeholder, field):
                        setattr(placeholder, field, value)
                placeholder.save()
                updated_count += 1
                logger.info(f"更新占位符: {key}")
            except Placeholder.DoesNotExist:
                logger.warning(f"占位符 {key} 不存在,跳过更新")
            except Exception as e:
                logger.error(f"更新占位符 {key} 失败: {e}")

        return updated_count
