"""
系统配置服务

提供系统配置的 CRUD 操作和缓存管理.
"""

from collections.abc import Iterable
from typing import Any

from django.core.cache import cache
from django.db import transaction

from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.models.system_config import SystemConfig
from apps.core.repositories.system_config_repository import SystemConfigRepository


class _MissingSentinel:
    pass


_MISSING_SENTINEL = _MissingSentinel()
_DEFAULT_CACHE_TIMEOUT_SECONDS = 300


class SystemConfigService:
    """系统配置服务"""

    def __init__(
        self,
        *,
        repository: SystemConfigRepository | None = None,
        cache_timeout: int | None = _DEFAULT_CACHE_TIMEOUT_SECONDS,
    ) -> None:
        self._repository = repository or SystemConfigRepository()
        self._cache_timeout = cache_timeout

    @transaction.atomic
    def update_config(
        self,
        config_id: int,
        value: str | None = None,
        category: str | None = None,
        description: str | None = None,
        is_secret: bool | None = None,
        is_active: bool | None = None,
    ) -> SystemConfig:  # pragma: no cover
        """
        更新系统配置

        Args:
            config_id: 配置 ID
            value: 新配置值
            category: 新分类
            description: 新描述
            is_secret: 新敏感信息标志
            is_active: 新启用状态

        Returns:
            更新后的 SystemConfig 实例
        """
        config = self._repository.get_by_id(config_id)
        if config is None:
            raise NotFoundError(
                message="系统配置不存在",
                code="SYSTEM_CONFIG_NOT_FOUND",
                errors={"config_id": f"ID 为 {config_id} 的配置不存在"},
            )

        if value is not None:
            config.value = value

        if category is not None:
            config.category = category

        if description is not None:
            config.description = description

        if is_secret is not None:
            config.is_secret = is_secret

        if is_active is not None:
            config.is_active = is_active

        config.save()

        # 清除缓存
        self._clear_cache(config.key)

        return config

    @transaction.atomic
    def delete_config(self, config_id: int) -> bool:
        """
        删除系统配置

        Args:
            config_id: 配置 ID

        Returns:
            是否成功
        """
        config = self._repository.get_by_id(config_id)
        if config is None:
            raise NotFoundError(
                message="系统配置不存在",
                code="SYSTEM_CONFIG_NOT_FOUND",
                errors={"config_id": f"ID 为 {config_id} 的配置不存在"},
            )

        key = config.key
        self._repository.delete(config_id)

        # 清除缓存
        self._clear_cache(key)

        return True

    def get_config(self, config_id: int) -> SystemConfig:
        """
        获取系统配置

        Args:
            config_id: 配置 ID

        Returns:
            SystemConfig 实例
        """
        config = self._repository.get_by_id(config_id)
        if config is None:
            raise NotFoundError(
                message="系统配置不存在",
                code="SYSTEM_CONFIG_NOT_FOUND",
                errors={"config_id": f"ID 为 {config_id} 的配置不存在"},
            )
        return config

    def get_value(self, key: str, default: str = "") -> str:  # pragma: no cover
        """
        获取配置值

        Args:
            key: 配置键
            default: 默认值

        Returns:
            配置值,不存在时返回默认值
        """
        cache_key = f"system_config:{key}"
        cached = cache.get(cache_key)
        if cached is _MISSING_SENTINEL or isinstance(cached, _MissingSentinel):
            return default
        if cached is not None:
            return cached if isinstance(cached, str) else str(cached)

        config = self._repository.get_by_key(key)
        if config is None or not config.is_active:
            cache.set(cache_key, _MISSING_SENTINEL, timeout=self._cache_timeout)
            return default

        value = config.value
        if config.is_secret:
            from apps.core.security.secret_codec import SecretCodec

            codec = SecretCodec()
            if codec.is_encrypted(value):
                value = codec.decrypt(value)
        cache.set(cache_key, value, timeout=self._cache_timeout)
        return value

    @classmethod
    async def aget_value(cls, key: str, default: str = "") -> str:  # pragma: no cover
        """异步获取配置值 — 使用 async ORM"""
        # classmethod 无实例状态,仓库本身无状态,直接实例化走 repo 保持与其他方法一致的数据访问路径
        repository = SystemConfigRepository()
        config = await repository.aget_active_by_key(key)
        if config is None:
            return default
        value: str = config.value
        if config.is_secret:
            from apps.core.security.secret_codec import SecretCodec

            codec = SecretCodec()
            if codec.is_encrypted(value):
                value = codec.decrypt(value)
        return value

    def warm_cache(
        self, keys: Iterable[str], timeout: int | None = _DEFAULT_CACHE_TIMEOUT_SECONDS
    ) -> dict[str, str]:  # pragma: no cover
        requested = [str(k) for k in keys if str(k)]
        if not requested:
            return {}

        queryset = self._repository.get_by_keys(requested)
        values: dict[str, str] = {str(cfg.key): str(cfg.value) for cfg in queryset}

        for key in requested:
            cache_key = f"system_config:{key}"
            if key in values:
                cache.set(cache_key, values[key], timeout=timeout)
            else:
                cache.set(cache_key, _MISSING_SENTINEL, timeout=timeout)

        return values

    def _clear_cache(self, key: str) -> None:  # pragma: no cover
        """清除系统配置缓存"""
        cache.delete(f"system_config:{key}")

    def get_value_internal(self, key: str, default: str = "") -> str:
        """获取配置值(内部方法,与 get_value 相同)"""
        return self.get_value(key, default)

    def get_all_active_configs(self) -> list[SystemConfig]:
        """获取所有启用的系统配置

        Returns:
            启用的 SystemConfig 列表
        """
        return self._repository.get_all_active()

    def get_config_by_key(self, key: str) -> SystemConfig | None:
        """按配置键获取系统配置

        与 get_value 不同,本方法直接返回模型实例(含敏感标志等元数据),
        供调用方做存在性判断或读取非值字段,不存在时返回 None 而不抛异常。

        Args:
            key: 配置键

        Returns:
            SystemConfig 实例,不存在时返回 None
        """
        return self._repository.get_by_key(key)

    def get_category_configs(self, category: str) -> dict[str, str]:
        """获取某分类下的所有配置

        Args:
            category: 配置分类

        Returns:
            配置键值对字典
        """
        configs = self._repository.get_by_category(category)
        return {str(config.key): str(config.value) for config in configs}

    def get_category_configs_internal(self, category: str) -> dict[str, str]:
        """获取某分类下的所有配置(内部方法)"""
        return self.get_category_configs(category)

    def set_value(
        self,
        key: str,
        value: str,
        category: str = "general",
        description: str = "",
        is_secret: bool = False,
    ) -> Any:
        """设置配置值(创建或更新)

        Args:
            key: 配置键
            value: 配置值
            category: 分类
            description: 描述
            is_secret: 是否敏感

        Returns:
            SystemConfig 实例
        """
        stored_value = value
        if is_secret:
            from apps.core.security.secret_codec import SecretCodec

            stored_value = SecretCodec().encrypt(value)

        config = self._repository.update_or_create(
            key=key,
            defaults={
                "value": stored_value,
                "category": category,
                "description": description,
                "is_secret": is_secret,
                "is_active": True,
            },
        )
        self._clear_cache(key)
        return config
