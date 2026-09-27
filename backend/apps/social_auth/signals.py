"""SystemConfig 变更时失效社交登录 Provider 的配置缓存。

为什么不写在 ``SystemConfigAdmin.save_model`` 里：core 禁止新增对业务 app 的
依赖（``tests/ci/structure/test_core_no_business_deps.py`` 的冻结基线只减不增）。
用信号把「谁关心配置变更」交回 social_auth 自己，admin 只负责存配置。
"""

from __future__ import annotations

import logging
from typing import Any

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from apps.core.models import SystemConfig

from .providers import PROVIDER_SPECS, ProviderRegistry

logger = logging.getLogger(__name__)

_PREVIOUS_KEY_ATTR = "_social_auth_previous_key"


def _borrowed_keys() -> set[str]:
    """被社交登录借用的共用凭证键（如 IM 群聊的 FEISHU_APP_ID / FEISHU_APP_SECRET）。"""
    keys: set[str] = set()
    for spec in PROVIDER_SPECS.values():
        keys.update((spec.get("fallback_credentials") or {}).keys())
    return keys


def invalidate_provider_configs(*keys: str) -> None:
    """配置变更后失效 Provider 配置缓存。

    除了本分类的 ``SOCIAL_AUTH_*``，还要关注被借用的共用凭证——扫码登录复用
    它们，改了同样要失效缓存。

    **一律整体失效**，不按名局部清除：``_configs`` 只装已启用的 Provider，局部
    清除后该名字从缓存消失，而读取方以「缓存是否为空」判断要不要重建，缓存非空
    就不再重建 —— 运行中新启用一个 Provider 后，登录页与绑定页会长期看不到它，
    必须重启后端才恢复。
    """
    touched = {key for key in keys if key}
    if not touched:
        return

    prefixes = [str(spec["prefix"]) for spec in PROVIDER_SPECS.values()]
    affects_providers = bool(touched & _borrowed_keys()) or any(
        key.startswith(prefix) for key in touched for prefix in prefixes
    )
    if affects_providers:
        ProviderRegistry.clear_configs()


@receiver(pre_save, sender=SystemConfig)
def _remember_previous_key(sender: Any, instance: SystemConfig, **kwargs: Any) -> None:
    """改名时 ``post_save`` 只能拿到新键，旧键先在这里记下来。"""
    if not instance.pk:
        return
    previous = SystemConfig.objects.filter(pk=instance.pk).only("key").first()
    setattr(instance, _PREVIOUS_KEY_ATTR, str(previous.key or "") if previous else "")


@receiver(post_save, sender=SystemConfig)
def _on_config_saved(sender: Any, instance: SystemConfig, **kwargs: Any) -> None:
    previous = str(getattr(instance, _PREVIOUS_KEY_ATTR, "") or "")
    invalidate_provider_configs(str(instance.key or ""), previous)


@receiver(post_delete, sender=SystemConfig)
def _on_config_deleted(sender: Any, instance: SystemConfig, **kwargs: Any) -> None:
    invalidate_provider_configs(str(instance.key or ""))
