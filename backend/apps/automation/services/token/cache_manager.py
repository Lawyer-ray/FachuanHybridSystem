"""
Token获取缓存管理服务

提供智能缓存管理，减少数据库查询，提升性能。
"""

import hashlib
import logging
import re
from datetime import datetime
from typing import Any, cast

from django.core.cache import cache
from django.utils import timezone

from apps.core.cache import CacheTimeout
from apps.core.interfaces import AccountCredentialDTO
from apps.core.telemetry.metrics import record_cache_access, record_cache_result

from .performance_monitor import performance_monitor

logger = logging.getLogger(__name__)


class TokenCacheManager:
    """
    Token缓存管理器

    功能：
    1. Token缓存管理
    2. 账号凭证缓存
    3. 登录统计缓存
    4. 智能缓存失效
    """

    def __init__(self) -> None:
        """初始化缓存管理器"""
        self.cache_prefix = "auto_token"

    def get_cached_token(self, site_name: str, account: str) -> str | None:
        """
        获取缓存的Token

        Args:
            site_name: 网站名称
            account: 账号

        Returns:
            缓存的Token，无则返回None
        """
        cache_key = self._get_token_cache_key(site_name, account)

        try:
            cached_data = cache.get(cache_key)
            hit = cached_data is not None
            performance_monitor.record_cache_access(cache_key, hit)
            record_cache_access(cache_kind="automation_token", name="token", hit=hit)

            if cached_data:
                logger.debug(
                    "Token缓存命中", extra={"site_name": site_name, "account": account, "cache_key": cache_key}
                )
                return cast(str | None, cached_data.get("token"))

            logger.debug("Token缓存未命中", extra={"site_name": site_name, "account": account, "cache_key": cache_key})
            return None

        except Exception as e:
            logger.warning(f"获取Token缓存失败: {e}", extra={"site_name": site_name, "account": account})
            record_cache_result(cache_kind="automation_token", name="token", result="error")
            return None

    def cache_token(self, site_name: str, account: str, token: str, expires_at: datetime | None = None) -> None:
        """
        缓存Token

        Args:
            site_name: 网站名称
            account: 账号
            token: Token值
            expires_at: 过期时间
        """
        cache_key = self._get_token_cache_key(site_name, account)

        # 计算缓存超时时间
        if expires_at:
            timeout = int((expires_at - timezone.now()).total_seconds())
            # 提前5分钟过期，避免使用即将过期的Token
            timeout = max(0, timeout - 300)
            # 如果剩余时间不足5分钟，不缓存
            if timeout == 0:
                logger.debug("Token即将过期，跳过缓存", extra={"site_name": site_name, "account": account})
                return
        else:
            # 默认缓存1小时
            timeout = CacheTimeout.LONG

        cache_data = {
            "token": token,
            "cached_at": timezone.now().isoformat(),
            "expires_at": expires_at.isoformat() if expires_at else None,
        }

        try:
            cache.set(cache_key, cache_data, timeout=timeout)
            logger.info(
                "Token已缓存",
                extra={"site_name": site_name, "account": account, "cache_key": cache_key, "timeout": timeout},
            )
        except Exception as e:
            logger.warning(f"缓存Token失败: {e}", extra={"site_name": site_name, "account": account})

    def invalidate_token_cache(self, site_name: str, account: str) -> None:
        """
        使Token缓存失效

        Args:
            site_name: 网站名称
            account: 账号
        """
        cache_key = self._get_token_cache_key(site_name, account)

        try:
            cache.delete(cache_key)
            logger.info("Token缓存已失效", extra={"site_name": site_name, "account": account, "cache_key": cache_key})
        except Exception as e:
            logger.warning(f"使Token缓存失效失败: {e}", extra={"site_name": site_name, "account": account})

    def get_cached_credentials(self, site_name: str) -> list[AccountCredentialDTO] | None:
        """
        获取缓存的账号凭证列表

        Args:
            site_name: 网站名称

        Returns:
            账号凭证DTO列表，无则返回None
        """
        cache_key = self._get_credentials_cache_key(site_name)

        try:
            cached_data = cache.get(cache_key)
            performance_monitor.record_cache_access(cache_key, cached_data is not None)

            if cached_data:
                # 反序列化为DTO对象
                credentials = []
                for cred_data in cached_data:
                    dto = AccountCredentialDTO(**cred_data)
                    credentials.append(dto)

                logger.debug(
                    "账号凭证缓存命中",
                    extra={"site_name": site_name, "cache_key": cache_key, "count": len(credentials)},
                )
                return credentials

            logger.debug("账号凭证缓存未命中", extra={"site_name": site_name, "cache_key": cache_key})
            return None

        except Exception as e:
            logger.warning(f"获取账号凭证缓存失败: {e}", extra={"site_name": site_name})
            return None

    def cache_credentials(self, site_name: str, credentials: list[AccountCredentialDTO]) -> None:
        """
        缓存账号凭证列表（密码字段置空，不存储明文密码）

        Args:
            site_name: 网站名称
            credentials: 账号凭证DTO列表
        """
        cache_key = self._get_credentials_cache_key(site_name)

        try:
            # 序列化DTO对象，密码字段置空
            cache_data = []
            for cred in credentials:
                cred_dict = cred.__dict__.copy()
                cred_dict["password"] = ""
                cache_data.append(cred_dict)

            cache.set(cache_key, cache_data, timeout=CacheTimeout.MEDIUM)
            logger.info(
                "账号凭证已缓存", extra={"site_name": site_name, "cache_key": cache_key, "count": len(credentials)}
            )
        except Exception as e:
            logger.warning(f"缓存账号凭证失败: {e}", extra={"site_name": site_name})

    def invalidate_credentials_cache(self, site_name: str) -> None:
        """
        使账号凭证缓存失效

        Args:
            site_name: 网站名称
        """
        cache_key = self._get_credentials_cache_key(site_name)

        try:
            cache.delete(cache_key)
            logger.info("账号凭证缓存已失效", extra={"site_name": site_name, "cache_key": cache_key})
        except Exception as e:
            logger.warning(f"使账号凭证缓存失效: {e}", extra={"site_name": site_name})

    def get_cached_account_stats(self, account: str, site_name: str) -> dict[str, Any] | None:
        """
        获取缓存的账号统计信息

        Args:
            account: 账号
            site_name: 网站名称

        Returns:
            账号统计信息，无则返回None
        """
        cache_key = self._get_account_stats_cache_key(account, site_name)

        try:
            cached_data = cache.get(cache_key)
            performance_monitor.record_cache_access(cache_key, cached_data is not None)

            if cached_data:
                logger.debug(
                    "账号统计缓存命中", extra={"account": account, "site_name": site_name, "cache_key": cache_key}
                )
                return cast(dict[str, Any] | None, cached_data)

            return None

        except Exception as e:
            logger.warning(f"获取账号统计缓存失败: {e}", extra={"account": account, "site_name": site_name})
            return None

    def cache_account_stats(self, account: str, site_name: str, stats: dict[str, Any]) -> None:
        """
        缓存账号统计信息

        Args:
            account: 账号
            site_name: 网站名称
            stats: 统计信息
        """
        cache_key = self._get_account_stats_cache_key(account, site_name)

        try:
            cache.set(cache_key, stats, timeout=CacheTimeout.MEDIUM)
            logger.debug("账号统计已缓存", extra={"account": account, "site_name": site_name, "cache_key": cache_key})
        except Exception as e:
            logger.warning(f"缓存账号统计失败: {e}", extra={"account": account, "site_name": site_name})

    def invalidate_account_stats_cache(self, account: str, site_name: str) -> None:
        """
        使账号统计缓存失效

        Args:
            account: 账号
            site_name: 网站名称
        """
        cache_key = self._get_account_stats_cache_key(account, site_name)

        try:
            cache.delete(cache_key)
            logger.debug(
                "账号统计缓存已失效", extra={"account": account, "site_name": site_name, "cache_key": cache_key}
            )
        except Exception as e:
            logger.warning(f"使账号统计缓存失效: {e}", extra={"account": account, "site_name": site_name})

    def get_cached_blacklist(self) -> list[str] | None:
        """
        获取缓存的黑名单

        Returns:
            黑名单账号列表，无则返回None
        """
        cache_key = f"{self.cache_prefix}:blacklist"

        try:
            cached_data = cache.get(cache_key)
            performance_monitor.record_cache_access(cache_key, cached_data is not None)

            if cached_data:
                logger.debug("黑名单缓存命中", extra={"cache_key": cache_key, "count": len(cached_data)})
                return cast(list[str] | None, cached_data)

            return None

        except Exception as e:
            logger.warning(f"获取黑名单缓存失败: {e}")
            return None

    def cache_blacklist(self, blacklist: list[str]) -> None:
        """
        缓存黑名单

        Args:
            blacklist: 黑名单账号列表
        """
        cache_key = f"{self.cache_prefix}:blacklist"

        try:
            cache.set(cache_key, blacklist, timeout=CacheTimeout.SHORT)
            logger.debug("黑名单已缓存", extra={"cache_key": cache_key, "count": len(blacklist)})
        except Exception as e:
            logger.warning(f"缓存黑名单失败: {e}")

    def invalidate_blacklist_cache(self) -> None:
        """使黑名单缓存失效"""
        cache_key = f"{self.cache_prefix}:blacklist"

        try:
            cache.delete(cache_key)
            logger.debug("黑名单缓存已失效", extra={"cache_key": cache_key})
        except Exception as e:
            logger.warning(f"使黑名单缓存失效失败: {e}")

    def invalidate_site_cache(self, site_name: str, *, accounts: list[str] | None = None) -> None:
        """
        定向失效指定站点的缓存

        Args:
            site_name: 网站名称
            accounts: 指定账号列表，None 则仅失效凭证缓存
        """
        self.invalidate_credentials_cache(site_name)
        logger.info("站点凭证缓存已失效", extra={"site_name": site_name})

        if accounts:
            for account in accounts:
                self.invalidate_token_cache(site_name, account)
                self.invalidate_account_stats_cache(account, site_name)
            logger.info(
                "站点账号缓存已失效",
                extra={"site_name": site_name, "account_count": len(accounts)},
            )

    def _is_cache_clear_allowed(self) -> bool:
        """
        检查全量清理是否被允许

        仅在 DEBUG 模式或设置了 ALLOW_CACHE_CLEAR 环境变量时允许。
        """
        import os

        from django.conf import settings

        if getattr(settings, "DEBUG", False):
            return True
        allow_env = (os.environ.get("ALLOW_CACHE_CLEAR", "") or "").lower()
        return allow_env in ("true", "1", "yes")

    def warm_up_cache(self, site_name: str) -> None:
        """
        预热缓存

        Args:
            site_name: 网站名称
        """
        logger.info("开始预热缓存", extra={"site_name": site_name})

        try:
            # 预加载账号凭证
            from apps.automation.services.token.account_selection_strategy import AccountSelectionStrategy

            AccountSelectionStrategy()

            # 这里需要异步调用，但为了简化，我们先跳过实际的预加载
            # 在实际使用中，可以通过后台任务来预热缓存

            logger.info("缓存预热完成", extra={"site_name": site_name})

        except Exception as e:
            logger.warning(f"缓存预热失败: {e}", extra={"site_name": site_name})

    def clear_all_cache(self) -> None:
        """清除所有相关缓存（仅 DEBUG 模式或设置 ALLOW_CACHE_CLEAR 时生效）"""
        if not self._is_cache_clear_allowed():
            logger.warning("生产环境禁止全量清除缓存，如需清除请设置 ALLOW_CACHE_CLEAR=true")
            return

        try:
            from django.conf import settings

            caches_conf = getattr(settings, "CACHES", {})
            default_conf = caches_conf.get("default", {})
            backend = default_conf.get("BACKEND", "")

            if "redis" in backend.lower():
                self._clear_redis_namespace_cache(default_conf, backend=backend)
            else:
                cache.clear()

            logger.info("所有Token相关缓存已清除")
        except Exception as e:
            logger.warning(f"清除缓存失败: {e}")

    def _clear_redis_namespace_cache(self, cache_conf: dict[str, Any], *, backend: str = "") -> None:
        """
        清除 Redis 命名空间下的 Token 缓存键

        Args:
            cache_conf: CACHES['default'] 配置字典
            backend: 缓存后端类名
        """
        location = cache_conf.get("LOCATION")
        if not location:
            logger.warning("token_cache_clear_redis_location_missing")
            return

        try:
            import redis  # type: ignore[import-untyped]

            client = redis.from_url(str(location))
            pattern = f"{self.cache_prefix}:*"
            keys = client.keys(pattern)
            if keys:
                client.delete(*keys)
            logger.info(f"Redis 命名空间缓存已清除: {len(keys)} 个键")
        except ModuleNotFoundError:
            logger.warning("token_cache_clear_redis_client_init_failed")
        except Exception as e:
            logger.warning(f"Redis 缓存清除失败: {e}")

    def get_cache_statistics(self) -> dict[str, Any]:
        """
        获取缓存统计信息

        Returns:
            缓存统计信息
        """
        try:
            # 这里简化处理，实际应该从Redis获取详细统计
            return {
                "cache_backend": "redis",
                "total_keys": "unknown",  # 需要Redis DBSIZE命令
                "memory_usage": "unknown",  # 需要Redis INFO命令
                "hit_rate": "see_performance_monitor",
            }
        except Exception as e:
            logger.warning(f"获取缓存统计失败: {e}")
            return {}

    def _get_token_cache_key(self, site_name: str, account: str) -> str:
        """生成Token缓存键（账号哈希化，site_name 清理特殊字符）"""
        safe_site = re.sub(r"[^a-zA-Z0-9_\-]", "_", site_name)
        account_hash = hashlib.sha256(account.encode()).hexdigest()[:16]
        return f"{self.cache_prefix}:token:{safe_site}:{account_hash}"

    def _get_credentials_cache_key(self, site_name: str) -> str:
        """生成账号凭证缓存键"""
        return f"{self.cache_prefix}:credentials:{site_name}"

    def _get_account_stats_cache_key(self, account: str, site_name: str) -> str:
        """生成账号统计缓存键"""
        return f"{self.cache_prefix}:account_stats:{account}:{site_name}"


# 全局缓存管理器实例
cache_manager = TokenCacheManager()
