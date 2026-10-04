"""社交登录配置变更时失效 Provider 的配置缓存。

两个监听对象：

1. ``SocialAuthProvider``（社交登录平台配置表）：本表任何增删改都整体失效。
2. ``SystemConfig``：只关心**被借用的共用凭证键**（如 IM 群聊的
   ``FEISHU_APP_ID`` / ``FEISHU_APP_SECRET``，飞书扫码登录凭证留空时会借用）。

为什么不写在 ``SystemConfigAdmin.save_model`` 里：core 禁止新增对业务 app 的
依赖（``tests/ci/structure/test_core_no_business_deps.py`` 的冻结基线只减不增）。
用信号把「谁关心配置变更」交回 social_auth 自己，admin 只负责存配置。
"""

from __future__ import annotations

import logging
from typing import Any

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.core.models import SystemConfig

from .models import SocialAuthProvider
from .providers import PROVIDER_SPECS, ProviderRegistry

logger = logging.getLogger(__name__)


def _borrowed_keys() -> set[str]:
    """被社交登录借用的共用凭证键（如 IM 群聊的 FEISHU_APP_ID / FEISHU_APP_SECRET）。"""
    keys: set[str] = set()
    for spec in PROVIDER_SPECS.values():
        keys.update((spec.get("fallback_credentials") or {}).keys())
    return keys


def invalidate_provider_configs(*keys: str) -> None:
    """配置变更后失效 Provider 配置缓存。

    入参是 SystemConfig 的键名，只有**被借用的共用凭证键**需要失效——
    社交登录自身的配置已迁到 ``SocialAuthProvider`` 表，走该表的信号。

    **一律整体失效**，不按名局部清除：``_configs`` 只装已启用的 Provider，局部
    清除后该名字从缓存消失，而读取方以「缓存是否为空」判断要不要重建，缓存非空
    就不再重建 —— 运行中新启用一个 Provider 后，登录页与绑定页会长期看不到它，
    必须重启后端才恢复。
    """
    touched = {key for key in keys if key}
    if not touched:
        return

    if touched & _borrowed_keys():
        ProviderRegistry.clear_configs()


@receiver(post_save, sender=SocialAuthProvider, dispatch_uid="social_auth_provider_saved")
@receiver(post_delete, sender=SocialAuthProvider, dispatch_uid="social_auth_provider_deleted")
def _on_provider_row_changed(sender: Any, instance: SocialAuthProvider, **kwargs: Any) -> None:
    """社交登录平台配置行增删改 → 整体失效缓存。"""
    ProviderRegistry.clear_configs()


@receiver(post_save, sender=SystemConfig, dispatch_uid="social_auth_borrowed_config_saved")
def _on_config_saved(sender: Any, instance: SystemConfig, **kwargs: Any) -> None:
    invalidate_provider_configs(str(instance.key or ""))


@receiver(post_delete, sender=SystemConfig, dispatch_uid="social_auth_borrowed_config_deleted")
def _on_config_deleted(sender: Any, instance: SystemConfig, **kwargs: Any) -> None:
    invalidate_provider_configs(str(instance.key or ""))
