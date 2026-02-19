"""Module for cache."""

from __future__ import annotations

"""
缓存配置模块
提供 Django 内置本地内存缓存配置
"""

import os
from typing import Any


def _safe_get_config(key: str, default: Any | None = None) -> Any:
    """安全获取配置,避免循环导入"""
    try:
        from apps.core.config import get_config

        return get_config(key, default)
    except Exception:
        logger.exception("操作失败")

        return default


def _hash_key_component(value: str) -> str:
    import hashlib
    import hmac

    from django.conf import settings

    v = (value or "").strip().encode("utf-8")
    secret = (getattr(settings, "SECRET_KEY", "") or "").encode("utf-8")
    return hmac.new(secret, v, hashlib.sha256).hexdigest()[:32]


def _normalize_key_component(value: str, *, max_len: int = 64) -> str:
    import re

    raw = (value or "").strip()
    if not raw:
        return "empty"

    normalized = raw.lower()
    if re.fullmatch(r"[a-z0-9._-]+", normalized) and len(normalized) <= max_len:
        return normalized

    cleaned = re.sub(r"[^a-z0-9._-]+", "-", normalized).strip("-._")
    if not cleaned:
        cleaned = "x"

    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip("-._") or "x"

    return f"{cleaned}-{_hash_key_component(raw)}"


def get_cache_config() -> dict[str, Any]:
    """
    获取缓存配置

    使用 Django 内置的本地内存缓存,无需外部依赖.

    Returns:
        Django CACHES 配置字典
    """
    default_timeout = _safe_get_config("performance.cache.default_timeout", 300)

    redis_url = (os.environ.get("DJANGO_CACHE_REDIS_URL", "") or "").strip()
    if redis_url:
        return {
            "default": {
                "BACKEND": "django.core.cache.backends.redis.RedisCache",
                "LOCATION": redis_url,
                "KEY_PREFIX": _safe_get_config("performance.cache.key_prefix", "lawfirm"),
                "TIMEOUT": default_timeout,
            }
        }

    return {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "unique-lawfirm-cache",
            "OPTIONS": {
                "MAX_ENTRIES": 1000,
            },
            "KEY_PREFIX": _safe_get_config("performance.cache.key_prefix", "lawfirm"),
            "TIMEOUT": default_timeout,
        }
    }


# 缓存 key 常量
class CacheKeys:
    """缓存 key 定义"""

    # 用户相关
    USER_ORG_ACCESS = "user:org_access:{user_id}"  # 用户组织访问权限
    USER_TEAMS = "user:teams:{user_id}"  # 用户团队列表

    # 案件相关
    CASE_ACCESS_GRANTS = "case:access_grants:{user_id}"  # 用户案件访问授权

    # 自动化相关
    AUTOMATION_COURT_SMS_RECOVERY_SCHEDULED = "automation:court_sms_recovery_scheduled"

    # 配置相关
    CASE_STAGES_CONFIG = "config:case_stages"  # 案件阶段配置
    LEGAL_STATUS_CONFIG = "config:legal_status"  # 诉讼地位配置
    SYSTEM_CONFIG = "system_config:{key}"

    # 法院系统 Token 相关
    COURT_TOKEN = "court_token:{site_name}:{account}"  # 法院系统 Token
    # 自动化 Token 性能监控
    AUTOMATION_TOKEN_PERF_ACQUISITION = "automation:token:perf:acquisition:{acquisition_id}"
    AUTOMATION_TOKEN_PERF_CONCURRENT = "automation:token:perf:concurrent:{site_name}"
    AUTOMATION_TOKEN_PERF_COUNTER = "automation:token:perf:counter:{date}:{site_name}:{metric}"

    # Prompt 相关
    PROMPT_TEMPLATE = "prompt_template:{name}"
    PROMPT_VERSION_ACTIVE = "prompt_version:active:{name}"

    # Documents 模板匹配相关(包含版本号以便模板变更自动失效)
    DOCUMENTS_MATCH_CONTRACT_TEMPLATES = "documents:matching:contract_templates:{case_type}:{version}"
    DOCUMENTS_MATCH_FOLDER_TEMPLATES = "documents:matching:folder_templates:{template_type}:{case_type}:{version}"
    DOCUMENTS_MATCH_CASE_FILE_TEMPLATES = "documents:matching:case_file_templates:{case_type}:{case_stage}:{version}"
    DOCUMENTS_MATCHING_VERSION_DOCUMENT_TEMPLATES = "documents:matching:version:document_templates"
    DOCUMENTS_MATCHING_VERSION_FOLDER_TEMPLATES = "documents:matching:version:folder_templates"

    @classmethod
    def user_org_access(cls, user_id: int) -> str:
        return cls.USER_ORG_ACCESS.format(user_id=user_id)

    @classmethod
    def user_teams(cls, user_id: int) -> str:
        return cls.USER_TEAMS.format(user_id=user_id)

    @classmethod
    def case_access_grants(cls, user_id: int) -> str:
        return cls.CASE_ACCESS_GRANTS.format(user_id=user_id)

    @classmethod
    def automation_court_sms_recovery_scheduled(cls) -> str:
        return cls.AUTOMATION_COURT_SMS_RECOVERY_SCHEDULED

    @classmethod
    def court_token(cls, site_name: str, account: str) -> str:
        return cls.COURT_TOKEN.format(
            site_name=_normalize_key_component(site_name, max_len=64),
            account=_hash_key_component(account),
        )

    @classmethod
    def automation_token_perf_acquisition(cls, acquisition_id: str) -> str:
        return cls.AUTOMATION_TOKEN_PERF_ACQUISITION.format(acquisition_id=acquisition_id)

    @classmethod
    def automation_token_perf_concurrent(cls, *, site_name: str = "all") -> str:
        return cls.AUTOMATION_TOKEN_PERF_CONCURRENT.format(site_name=site_name or "all")

    @classmethod
    def automation_token_perf_counter(cls, *, date: str, site_name: str, metric: str) -> str:
        return cls.AUTOMATION_TOKEN_PERF_COUNTER.format(date=date, site_name=site_name or "all", metric=metric)

    @classmethod
    def prompt_template(cls, name: str) -> str:
        return cls.PROMPT_TEMPLATE.format(name=name)

    @classmethod
    def prompt_version_active(cls, name: str) -> str:
        return cls.PROMPT_VERSION_ACTIVE.format(name=name)

    @classmethod
    def system_config(cls, key: str) -> str:
        return cls.SYSTEM_CONFIG.format(key=key)

    @classmethod
    def documents_matching_contract_templates(cls, *, case_type: str, version: int) -> str:
        return cls.DOCUMENTS_MATCH_CONTRACT_TEMPLATES.format(case_type=case_type or "", version=version or 1)

    @classmethod
    def documents_matching_folder_templates(cls, *, template_type: str, case_type: str, version: int) -> str:
        return cls.DOCUMENTS_MATCH_FOLDER_TEMPLATES.format(
            template_type=template_type or "",
            case_type=case_type or "",
            version=version or 1,
        )

    @classmethod
    def documents_matching_case_file_templates(cls, *, case_type: str, case_stage: str, version: int) -> str:
        return cls.DOCUMENTS_MATCH_CASE_FILE_TEMPLATES.format(
            case_type=case_type or "",
            case_stage=case_stage or "",
            version=version or 1,
        )

    @classmethod
    def documents_matching_version_document_templates(cls) -> str:
        return cls.DOCUMENTS_MATCHING_VERSION_DOCUMENT_TEMPLATES

    @classmethod
    def documents_matching_version_folder_templates(cls) -> str:
        return cls.DOCUMENTS_MATCHING_VERSION_FOLDER_TEMPLATES


# 缓存超时时间(秒)
class _CacheTimeoutMeta(type):
    def __getattribute__(cls, name: str) -> int:
        if name == "SHORT":
            return int(_safe_get_config("performance.cache.timeout_short", 60))
        if name == "MEDIUM":
            return int(_safe_get_config("performance.cache.timeout_medium", 300))
        if name == "LONG":
            return int(_safe_get_config("performance.cache.timeout_long", 3600))
        if name == "DAY":
            return int(_safe_get_config("performance.cache.timeout_day", 86400))
        return int(super().__getattribute__(name))


class CacheTimeout(metaclass=_CacheTimeoutMeta):
    """缓存超时时间定义"""

    @staticmethod
    def get_short() -> int:
        """短期缓存(1分钟)"""
        return int(CacheTimeout.SHORT)

    @staticmethod
    def get_medium() -> int:
        """中期缓存(5分钟)"""
        return int(CacheTimeout.MEDIUM)

    @staticmethod
    def get_long() -> int:
        """长期缓存(1小时)"""
        return int(CacheTimeout.LONG)

    @staticmethod
    def get_day() -> int:
        """日缓存(1天)"""
        return int(CacheTimeout.DAY)

    @staticmethod
    def until_end_of_day(*, now: Any | None = None, buffer_seconds: int = 3600) -> int:
        from datetime import datetime, time, timedelta

        from django.utils import timezone

        if now is None:
            now = timezone.now()

        if timezone.is_naive(now):
            now = timezone.make_aware(now, timezone.get_current_timezone())

        end = timezone.make_aware(
            datetime.combine(now.date() + timedelta(days=1), time.min),
            timezone.get_current_timezone(),
        )
        seconds = int((end - now).total_seconds()) + int(buffer_seconds or 0)
        return max(1, seconds)

    # 保持向后兼容的常量
    SHORT = 60
    MEDIUM = 300
    LONG = 3600
    DAY = 86400


def invalidate_user_org_access_cache(user_id: int) -> None:
    from django.core.cache import cache

    cache.delete(CacheKeys.user_org_access(user_id))


def invalidate_case_access_cache(user_id: int) -> None:
    from django.core.cache import cache

    cache.delete(CacheKeys.case_access_grants(user_id))


def invalidate_user_access_context(user_id: int, *, org_access: bool = True, case_grants: bool = True) -> None:
    from django.core.cache import cache

    keys: list[Any] = []
    if org_access:
        keys.append(CacheKeys.user_org_access(user_id))
    if case_grants:
        keys.append(CacheKeys.case_access_grants(user_id))
    if keys:
        cache.delete_many(keys)


def invalidate_users_access_context(user_ids: list[int], *, org_access: bool = True, case_grants: bool = True) -> None:
    from django.core.cache import cache

    keys: list[str] = []
    for user_id in user_ids or []:
        if org_access:
            keys.append(CacheKeys.user_org_access(user_id))
        if case_grants:
            keys.append(CacheKeys.case_access_grants(user_id))
    if keys:
        cache.delete_many(keys)


def bump_cache_version(key: str, *, timeout: int) -> int:
    from django.core.cache import cache

    cache.add(key, 1, timeout=timeout)
    try:
        return int(cache.incr(key))
    except Exception:
        logger.exception("操作失败")

        current = int(cache.get(key) or 1)
        new_val = current + 1
        cache.set(key, new_val, timeout=timeout)
        return new_val


def delete_cache_key(key: str) -> None:
    from django.core.cache import cache

    cache.delete(key)


import logging

logger = logging.getLogger(__name__)
