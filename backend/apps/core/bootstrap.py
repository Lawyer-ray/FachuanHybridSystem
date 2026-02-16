"""Module for bootstrap."""

from __future__ import annotations

import logging
import threading
from typing import Any

from django.conf import settings

logger = logging.getLogger("apps.core.bootstrap")

_lock = threading.Lock()
_initialized = False


def ensure_core_initialized(**_kwargs: Any) -> None:
    global _initialized
    if _initialized:
        return

    with _lock:
        if _initialized:
            return

        try:
            _initialize_config_manager()
            _validate_configuration()
            _setup_config_monitoring()
            logger.info("核心系统初始化完成")
        except Exception as e:
            logger.error("核心系统初始化失败", extra={"error": str(e)})
            if getattr(settings, "DEBUG", False):
                raise

        _initialized = True


def _initialize_config_manager() -> None:
    if not getattr(settings, "CONFIG_MANAGER_AVAILABLE", False):
        logger.warning("统一配置管理器不可用,使用传统配置方式")
        return

    config_manager = getattr(settings, "UNIFIED_CONFIG_MANAGER", None)
    if not config_manager:
        logger.warning("配置管理器实例不存在")
        return

    if not config_manager.is_loaded():
        config_manager.load()
        logger.info("配置管理器加载完成")

    try:
        config_manager.enable_steering_integration()
        logger.info("Steering 系统集成已启用")
    except Exception as e:
        logger.warning("Steering 系统集成启用失败", extra={"error": str(e)})


def _validate_configuration() -> None:
    if not getattr(settings, "CONFIG_MANAGER_AVAILABLE", False):
        return

    config_manager = getattr(settings, "UNIFIED_CONFIG_MANAGER", None)
    if not config_manager:
        return

    critical_configs = [
        "django.secret_key",
        "django.debug",
        "database.engine",
    ]

    missing_configs: list[str] = []
    for config_key in critical_configs:
        try:
            value = config_manager.get(config_key)
            if value is None:
                missing_configs.append(config_key)
        except Exception:
            logger.exception("操作失败")

            missing_configs.append(config_key)

    if missing_configs:
        logger.warning("缺少关键配置项", extra={"missing_configs": missing_configs})
    else:
        logger.info("配置验证通过")

    if not getattr(settings, "DEBUG", True):
        _validate_production_config(config_manager)


def _validate_production_config(config_manager: Any) -> None:
    sensitive_configs = [
        "django.secret_key",
        "database.password",
        "services.moonshot.api_key",
        "chat_platforms.feishu.app_secret",
    ]

    env_missing: list[str] = []
    for config_key in sensitive_configs:
        try:
            value = config_manager.get(config_key)
            if not value:
                env_missing.append(config_key)
        except Exception:
            logger.exception("操作失败")

            env_missing.append(config_key)

    if env_missing:
        logger.error("生产环境缺少敏感配置", extra={"missing_configs": env_missing})
        raise ValueError("生产环境必须设置敏感配置")

    logger.info("生产环境配置验证通过")


def _setup_config_monitoring() -> None:
    if not getattr(settings, "CONFIG_MANAGER_AVAILABLE", False):
        return

    config_manager = getattr(settings, "UNIFIED_CONFIG_MANAGER", None)
    if not config_manager:
        return

    try:
        from .config.listeners import ConfigChangeLogger, ConfigValidationListener

        config_manager.add_listener(ConfigChangeLogger())
        config_manager.add_listener(ConfigValidationListener())
        logger.info("配置监控设置完成")
    except ImportError:
        logger.debug("配置监听器类不存在,跳过监控设置")
    except Exception as e:
        logger.warning("配置监控设置失败", extra={"error": str(e)})
