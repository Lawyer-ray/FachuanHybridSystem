"""
系统配置服务

提供系统配置的 CRUD 操作和缓存管理.
"""

from django.utils.translation import gettext_lazy as _
from collections.abc import Iterable
from typing import Any, cast

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
    def create_config(
        self,
        key: str,
        value: str,
        category: str = "general",
        description: str = "",
        is_secret: bool = False,
        is_active: bool = True,
    ) -> SystemConfig:
        """
        创建系统配置

        Args:
            key: 配置键(唯一标识)
            value: 配置值
            category: 分类
            description: 描述
            is_secret: 是否为敏感信息
            is_active: 是否启用

        Returns:
            创建的 SystemConfig 实例
        """
        if not key or not key.strip():
            raise ValidationException(
                message=_("配置键不能为空"),
                code="INVALID_CONFIG_KEY",
                errors={"key": "配置键不能为空"},
            )

        config = self._repository.create(
            key=key.strip(),
            value=value,
            category=category,
            description=description,
            is_secret=is_secret,
            is_active=is_active,
        )

        # 清除缓存
        self._clear_cache(key)

        return cast(SystemConfig, config)

    @transaction.atomic
    def update_config(
        self,
        config_id: int,
        value: str | None = None,
        category: str | None = None,
        description: str | None = None,
        is_secret: bool | None = None,
        is_active: bool | None = None,
    ) -> SystemConfig:
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
        config = self._model.objects.filter(id=config_id).first()
        if config is None:
            raise NotFoundError(
                message=_("系统配置不存在"),
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

        return cast(SystemConfig, config)

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
                message=_("系统配置不存在"),
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
                message=_("系统配置不存在"),
                code="SYSTEM_CONFIG_NOT_FOUND",
                errors={"config_id": f"ID 为 {config_id} 的配置不存在"},
            )
        return cast(SystemConfig, config)

    def get_config_by_key(self, key: str) -> SystemConfig | None:
        """
        根据键获取系统配置

        Args:
            key: 配置键

        Returns:
            SystemConfig 实例,不存在时返回 None
        """
        return self._repository.get_by_key(key)

    def get_value(self, key: str, default: str = "") -> str:
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
        return cast(str, value)

    def list_configs(
        self,
        category: str | None = None,
        is_active: bool | None = None,
    ) -> list[SystemConfig]:
        """
        列出系统配置

        Args:
            category: 按分类过滤
            is_active: 按启用状态过滤

        Returns:
            SystemConfig 列表
        """
        queryset = self._model.objects.all()

        if category is not None:
            queryset = queryset.filter(category=category)

        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)

        return list(queryset.order_by("category", "key"))

    def warm_cache(self, keys: Iterable[str], timeout: int | None = _DEFAULT_CACHE_TIMEOUT_SECONDS) -> dict[str, str]:
        requested = [str(k) for k in keys if str(k)]
        if not requested:
            return {}

        queryset = self._model.objects.filter(key__in=requested, is_active=True)
        values: dict[str, str] = {str(cfg.key): str(cfg.value) for cfg in queryset}

        for key in requested:
            cache_key = f"system_config:{key}"
            if key in values:
                cache.set(cache_key, values[key], timeout=timeout)
            else:
                cache.set(cache_key, _MISSING_SENTINEL, timeout=timeout)

        return values

    def _clear_cache(self, key: str) -> None:
        """清除系统配置缓存"""
        cache.delete(f"system_config:{key}")

    def get_value_internal(self, key: str, default: str = "") -> str:
        """获取配置值(内部方法,与 get_value 相同)"""
        return self.get_value(key, default)

    def get_category_configs(self, category: str) -> dict[str, str]:
        """获取某分类下的所有配置

        Args:
            category: 配置分类

        Returns:
            配置键值对字典
        """
        configs = self._model.objects.filter(category=category, is_active=True)
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

        config, _created = self._model.objects.update_or_create(
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
