"""Business logic services."""

from __future__ import annotations
from django.utils.translation import gettext_lazy as _

import logging
from typing import Any, ClassVar, TypeVar

from apps.core.exceptions import ConflictError, NotFoundError

from .base import BasePlaceholderService

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BasePlaceholderService)


class PlaceholderRegistry:
    """占位符服务注册表(单例模式)"""

    _instance: PlaceholderRegistry | None = None
    _services: ClassVar[dict[str, type[BasePlaceholderService]]] = {}
    _initialized: bool = False

    def __new__(cls) -> PlaceholderRegistry:
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """初始化注册表"""
        if not self._initialized:
            PlaceholderRegistry._services = {}
            PlaceholderRegistry._initialized = True

    @classmethod
    def register(cls, service_class: type[T]) -> type[T]:
        """
        装饰器:注册占位符服务

        Args:
            service_class: 占位符服务类

        Returns:
            原始服务类(用于装饰器)

        Raises:
            ConflictError: 服务名称已存在
        """
        registry = cls()

        # 验证服务类
        if not issubclass(service_class, BasePlaceholderService):
            raise ValueError(f"服务类必须继承自 BasePlaceholderService: {service_class}")

        # 检查必要属性
        if not service_class.name:
            raise ValueError(f"服务类必须定义 name 属性: {service_class}")

        # 检查重复注册
        if service_class.name in registry._services:
            raise ConflictError(
                message=_("占位符服务名称冲突"),
                code="PLACEHOLDER_SERVICE_CONFLICT",
                errors={"name": f"服务名称 '{service_class.name}' 已存在"},
            )

        # 注册服务
        registry._services[service_class.name] = service_class
        logger.info("注册占位符服务: %s (%s)", service_class.name, service_class.__name__)

        return service_class

    def get_service(self, name: str) -> BasePlaceholderService:
        """
        获取服务实例

        Args:
            name: 服务名称

        Returns:
            服务实例

        Raises:
            NotFoundError: 服务不存在
        """
        if name not in self._services:
            raise NotFoundError(
                message=_("占位符服务不存在"),
                code="PLACEHOLDER_SERVICE_NOT_FOUND",
                errors={"name": f"服务名称 '{name}' 不存在"},
            )

        service_class = self._services[name]
        return service_class()

    def get_services_by_category(self, category: str) -> list[BasePlaceholderService]:
        """
        按分类获取服务列表

        Args:
            category: 服务分类

        Returns:
            该分类下的所有服务实例列表
        """
        services: list[Any] = []
        for service_class in self._services.values():
            if service_class.category == category:
                services.append(service_class())
        return services

    def get_all_services(self) -> list[BasePlaceholderService]:
        """
        获取所有服务

        Returns:
            所有服务实例列表
        """
        return [service_class() for service_class in self._services.values()]

    def get_service_for_placeholder(self, placeholder_key: str) -> BasePlaceholderService | None:
        """
        根据占位符键查找对应的服务

        Args:
            placeholder_key: 占位符键

        Returns:
            对应的服务实例,如果没有找到则返回 None
        """
        for service_class in self._services.values():
            if placeholder_key in service_class.placeholder_keys:
                return service_class()
        return None

    def list_registered_services(self) -> dict[str, dict[str, Any]]:
        """
        列出所有已注册的服务信息

        Returns:
            服务信息字典
        """
        result: dict[str, Any] = {}
        for name, service_class in self._services.items():
            result[name] = {
                "name": service_class.name,
                "display_name": service_class.display_name,
                "description": service_class.description,
                "category": service_class.category,
                "placeholder_keys": service_class.placeholder_keys,
                "placeholder_metadata": getattr(service_class, "placeholder_metadata", {}) or {},
                "class_name": service_class.__name__,
            }
        return result

    def clear(self) -> None:
        """清空注册表(主要用于测试)"""
        self._services.clear()
        logger.info("清空占位符服务注册表")
