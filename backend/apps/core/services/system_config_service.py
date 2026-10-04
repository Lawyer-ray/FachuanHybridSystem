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


def _maybe_decrypt(value: str) -> str:
    """缓存/库值读取时解密；密钥轮换后旧密文解不开时降级返回原值（安全审计 E-01）。"""
    from apps.core.security.secret_codec import SecretCodec

    codec = SecretCodec()
    if codec.is_encrypted(value):
        try:
            return codec.decrypt(value)
        except Exception:
            # 与库内读取的失败模式一致，避免 get_value 全线 500；轮换后应重写配置值自愈
            return value
    # 兼容存量明文（含旧缓存条目）：原样返回
    return value


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

        # 安全审计 B-07：拒绝 is_secret 由 true 降为 false（降级会使 API 响应
        # 直接回显明文），且敏感值更新必须走加密存储，与 set_value 口径一致。
        if is_secret is False and config.is_secret:
            raise ValidationException(
                message="不能将敏感配置降级为非敏感",
                code="SECRET_DOWNGRADE_FORBIDDEN",
                errors={"is_secret": "敏感标志只允许 false → true"},  # pragma: allowlist secret
            )

        if value is not None:
            # 复审结论：加密判定用「生效值」——PATCH 同时把 is_secret 升为 true 时
            # 新值必须加密落库，不能按旧标志走明文路径。
            effective_secret = bool(is_secret) if is_secret is not None else bool(config.is_secret)
            if effective_secret:
                from apps.core.security.secret_codec import SecretCodec

                codec = SecretCodec()
                config.value = value if codec.is_encrypted(value) else codec.encrypt(value)
            else:
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

        # 缓存清理推迟到事务提交后：提交前并发读会把旧值重新回填缓存
        transaction.on_commit(lambda: self._clear_cache(config.key))

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

        # 缓存清理推迟到事务提交后：提交前并发读会把旧值重新回填缓存
        transaction.on_commit(lambda: self._clear_cache(key))

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
            cached_str = cached if isinstance(cached, str) else str(cached)
            return _maybe_decrypt(cached_str)

        config = self._repository.get_by_key(key)
        if config is None or not config.is_active:
            cache.set(cache_key, _MISSING_SENTINEL, timeout=self._cache_timeout)
            return default

        # 安全审计 E-01：缓存始终存「存储态」原值（密钥为密文），读取时再解密，
        # 避免明文密钥进入共享 Redis/落盘 RDB。
        cache.set(cache_key, config.value, timeout=self._cache_timeout)
        return _maybe_decrypt(config.value)

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
