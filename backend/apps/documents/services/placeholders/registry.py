"""Business logic services."""

from __future__ import annotations

import logging
from typing import Any, ClassVar, TypeVar

from apps.core.exceptions import ConflictError, NotFoundError

from .base import BasePlaceholderService

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BasePlaceholderService)


def _service_registration_sort_key(service_class: type[BasePlaceholderService]) -> str:
    """占位符键冲突裁决用的确定性排序键: 服务模块路径 + 类限定名。"""
    return f"{service_class.__module__}.{service_class.__qualname__}"


class PlaceholderRegistry:
    """占位符服务注册表(单例模式)"""

    _instance: PlaceholderRegistry | None = None
    _services: ClassVar[dict[str, type[BasePlaceholderService]]] = {}
    _key_owner_names: ClassVar[dict[str, str]] = {}
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
            PlaceholderRegistry._key_owner_names = {}
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
                message="占位符服务名称冲突",
                code="PLACEHOLDER_SERVICE_CONFLICT",
                errors={"name": f"服务名称 '{service_class.name}' 已存在"},
            )

        # 注册服务
        registry._services[service_class.name] = service_class
        cls._claim_placeholder_keys(registry, service_class)
        logger.info("注册占位符服务: %s (%s)", service_class.name, service_class.__name__)

        return service_class

    @classmethod
    def _claim_placeholder_keys(cls, registry: PlaceholderRegistry, service_class: type[T]) -> None:
        """
        登记服务声明的占位符键归属。

        同一键被多个服务声明时记录 error 日志,并按服务模块路径排序取先者归属,
        确保结果不依赖目录枚举/导入顺序。
        """
        for key in dict.fromkeys(service_class.placeholder_keys):
            owner_name = registry._key_owner_names.get(key)
            if owner_name is None or owner_name == service_class.name or owner_name not in registry._services:
                registry._key_owner_names[key] = service_class.name
                continue

            existing_class = registry._services[owner_name]
            candidates: list[type[BasePlaceholderService]] = [existing_class, service_class]
            winner, loser = sorted(candidates, key=_service_registration_sort_key)
            registry._key_owner_names[key] = winner.name
            logger.error(
                "占位符键注册冲突: 键 '%s' 同时由服务 '%s' 与 '%s' 声明, 按 '%s' 排序保留 '%s'",
                key,
                existing_class.name,
                service_class.name,
                _service_registration_sort_key(winner),
                winner.name,
                extra={
                    "placeholder_key": key,
                    "kept_service": winner.name,
                    "dropped_service": loser.name,
                },
            )

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
                message="占位符服务不存在",
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

        冲突键返回注册时确定性裁决出的归属服务,不依赖注册顺序。

        Args:
            placeholder_key: 占位符键

        Returns:
            对应的服务实例,如果没有找到则返回 None
        """
        owner_name = self._key_owner_names.get(placeholder_key)
        if owner_name and owner_name in self._services:
            return self._services[owner_name]()

        for service_class in self._services.values():
            if placeholder_key in service_class.placeholder_keys:
                return service_class()
        return None

    def get_placeholder_key_owner(self, placeholder_key: str) -> str | None:
        """
        查询占位符键的归属服务名

        Args:
            placeholder_key: 占位符键

        Returns:
            冲突裁决后拥有该键的服务名,未声明或归属服务已失效时返回 None
        """
        owner_name = self._key_owner_names.get(placeholder_key)
        if owner_name and owner_name in self._services:
            return owner_name
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
        self._key_owner_names.clear()
        logger.info("清空占位符服务注册表")
