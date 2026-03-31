"""Module for django runtime."""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from cryptography.fernet import Fernet

_TRUE_VALUES = ("true", "1", "yes", "y", "on")


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    if not value:
        return default
    return value.lower() in _TRUE_VALUES


def _split_csv(value: str) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


@dataclass(frozen=True)
class DjangoSecurityConfig:
    is_production: bool
    debug: bool
    allow_lan: bool
    secret_key: str
    allowed_hosts: list[str]
    credential_encryption_key: str
    scraper_encryption_key: str


def _resolve_secret_key(is_production: bool, dev_secret_key: str) -> str:
    """解析 SECRET_KEY"""
    env_secret_key = os.environ.get("DJANGO_SECRET_KEY", "")
    if not is_production:
        return env_secret_key if env_secret_key else dev_secret_key
    if (
        not env_secret_key
        or env_secret_key in ("change-me-in-production", dev_secret_key)
        or env_secret_key.startswith("django-insecure-")
        or len(env_secret_key) < 50
    ):
        raise RuntimeError("生产环境必须设置安全的 DJANGO_SECRET_KEY")
    return env_secret_key


def _validate_fernet_key(key: str, env_name: str) -> None:
    """验证 Fernet 密钥有效性"""
    try:
        Fernet(key.encode())
    except Exception as e:
        raise RuntimeError(f"{env_name} 无效(必须是 Fernet key)") from e


def _resolve_encryption_keys(is_production: bool) -> tuple[str, str]:
    """解析加密密钥"""
    env_credential_key = (os.environ.get("CREDENTIAL_ENCRYPTION_KEY", "") or "").strip()
    env_scraper_key = (os.environ.get("SCRAPER_ENCRYPTION_KEY", "") or "").strip()

    if is_production:
        if not env_credential_key:
            raise RuntimeError("生产环境必须设置 CREDENTIAL_ENCRYPTION_KEY(Fernet 密钥)")
        _validate_fernet_key(env_credential_key, "CREDENTIAL_ENCRYPTION_KEY")
        credential_key = env_credential_key
        if env_scraper_key:
            _validate_fernet_key(env_scraper_key, "SCRAPER_ENCRYPTION_KEY")
            scraper_key = env_scraper_key
        else:
            scraper_key = credential_key
    else:
        _dev_fallback_key = Fernet.generate_key().decode()
        credential_key = env_credential_key if env_credential_key else _dev_fallback_key
        scraper_key = env_scraper_key if env_scraper_key else credential_key
    return credential_key, scraper_key


def resolve_security_config(
    *,
    dev_secret_key: str,
    default_allowed_hosts_dev: Sequence[str],
    default_allowed_hosts_prod: Sequence[str],
) -> DjangoSecurityConfig:
    is_production = not _env_bool("DJANGO_DEBUG", True)
    allow_lan = _env_bool("DJANGO_ALLOW_LAN", False)
    lan_allowed_hosts_env = os.environ.get("DJANGO_LAN_ALLOWED_HOSTS", "").strip()

    secret_key = _resolve_secret_key(is_production, dev_secret_key)
    credential_key, scraper_key = _resolve_encryption_keys(is_production)

    allowed_hosts_env = os.environ.get("DJANGO_ALLOWED_HOSTS", "")
    if allowed_hosts_env:
        allowed_hosts = _split_csv(allowed_hosts_env)
    elif is_production:
        allowed_hosts = list(default_allowed_hosts_prod)
    else:
        allowed_hosts = list(default_allowed_hosts_dev)

    if allow_lan:
        if is_production:
            raise RuntimeError("生产环境禁止启用 DJANGO_ALLOW_LAN")
        if not lan_allowed_hosts_env:
            raise RuntimeError("启用 DJANGO_ALLOW_LAN 必须同时设置 DJANGO_LAN_ALLOWED_HOSTS(逗号分隔)")
        lan_hosts = _split_csv(lan_allowed_hosts_env)
        allowed_hosts = sorted(set([h for h in allowed_hosts if h != "*"] + lan_hosts))

    return DjangoSecurityConfig(
        is_production=is_production,
        debug=not is_production,
        allow_lan=allow_lan,
        secret_key=secret_key,
        allowed_hosts=allowed_hosts,
        credential_encryption_key=credential_key,
        scraper_encryption_key=scraper_key,
    )


def resolve_cors_and_csrf(
    *,
    debug: bool,
    allow_lan: bool,
    safe_cors_origins: Sequence[str],
) -> dict[str, object]:
    if allow_lan:
        csrf_origins = os.environ.get("CSRF_TRUSTED_ORIGINS", "")
        cors_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "")
        if not cors_origins or not csrf_origins:
            raise RuntimeError("启用 DJANGO_ALLOW_LAN 必须显式设置 CORS_ALLOWED_ORIGINS 与 CSRF_TRUSTED_ORIGINS")
        return {
            "CORS_ALLOWED_ORIGINS": _split_csv(cors_origins),
            "CSRF_TRUSTED_ORIGINS": _split_csv(csrf_origins),
        }

    if debug:
        return {
            "CORS_ALLOW_ALL_ORIGINS": False,
            "CORS_ALLOWED_ORIGINS": list[Any](safe_cors_origins),
            "CSRF_TRUSTED_ORIGINS": list[Any](safe_cors_origins),
        }

    cors_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "")
    csrf_origins = os.environ.get("CSRF_TRUSTED_ORIGINS", "")
    if not cors_origins or not csrf_origins:
        raise RuntimeError("生产环境必须显式设置 CORS_ALLOWED_ORIGINS 与 CSRF_TRUSTED_ORIGINS")
    return {
        "CORS_ALLOWED_ORIGINS": _split_csv(cors_origins),
        "CSRF_TRUSTED_ORIGINS": _split_csv(csrf_origins),
    }


def resolve_perm_open_access(*, is_production: bool) -> bool:
    env_value = os.environ.get("PERM_OPEN_ACCESS", "").strip()
    enabled = env_value.lower() in _TRUE_VALUES
    if is_production:
        if enabled:
            raise RuntimeError("生产环境禁止启用 PERM_OPEN_ACCESS")
        return False
    return enabled if env_value else False


def resolve_rate_limit() -> dict[str, int]:
    return {
        "DEFAULT_REQUESTS": 100,
        "DEFAULT_WINDOW": 60,
        "AUTH_REQUESTS": 5,
        "AUTH_WINDOW": 60,
        "UPLOAD_REQUESTS": 20,
        "UPLOAD_WINDOW": 60,
        "EXPORT_REQUESTS": 20,
        "EXPORT_WINDOW": 60,
        "OCR_REQUESTS": 10,
        "OCR_WINDOW": 60,
        "LLM_REQUESTS": 20,
        "LLM_WINDOW": 60,
        "LLM_HISTORY_REQUESTS": 60,
        "LLM_HISTORY_WINDOW": 60,
        "TASK_REQUESTS": 30,
        "TASK_WINDOW": 60,
        "ADMIN_REQUESTS": 60,
        "ADMIN_WINDOW": 60,
    }


def resolve_channel_layers() -> dict[str, object]:
    redis_url = (os.environ.get("DJANGO_CHANNEL_REDIS_URL", "") or "").strip()
    if redis_url:
        return {
            "default": {
                "BACKEND": "channels_redis.core.RedisChannelLayer",
                "CONFIG": {"hosts": [redis_url]},
            }
        }
    return {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


def resolve_q_cluster() -> dict[str, object]:
    return {
        "name": "default",
        "workers": int(os.environ.get("DJANGO_Q_WORKERS", "2") or "2"),
        "timeout": int(os.environ.get("DJANGO_Q_TIMEOUT", "600") or "600"),
        "retry": int(os.environ.get("DJANGO_Q_RETRY", "1200") or "1200"),
        "queue_limit": int(os.environ.get("DJANGO_Q_QUEUE_LIMIT", "50") or "50"),
        "bulk": int(os.environ.get("DJANGO_Q_BULK", "10") or "10"),
        "orm": os.environ.get("DJANGO_Q_ORM", "default") or "default",
        "max_attempts": int(os.environ.get("DJANGO_Q_MAX_ATTEMPTS", "3") or "3"),
        "catch_up": (os.environ.get("DJANGO_Q_CATCH_UP", "False") or "").lower() in _TRUE_VALUES,
        "poll": float(os.environ.get("DJANGO_Q_POLL", "0.5") or "0.5"),  # 轮询间隔（秒），降低任务启动延迟
    }


def resolve_contract_folder_browse_roots() -> list[str]:
    env_value = os.environ.get("CONTRACT_FOLDER_BROWSE_ROOTS", "").strip()
    if env_value:
        return [p.strip() for p in env_value.replace(";", ",").split(",") if p.strip()]

    if sys.platform == "darwin":
        return ["/Users", "/Volumes"]
    if sys.platform.startswith("win"):
        return ["C:\\"]
    return ["/home", "/mnt"]
