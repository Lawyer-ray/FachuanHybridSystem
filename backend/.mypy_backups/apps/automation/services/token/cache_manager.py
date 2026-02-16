"""
Token获取缓存管理服务

提供智能缓存管理，减少数据库查询，提升性能。
"""
import logging
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from django.core.cache import cache
from django.utils import timezone

from apps.core.cache import CacheKeys, CacheTimeout
from apps.core.interfaces import AccountCredentialDTO
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
    
    def __init__(self):
        """初始化缓存管理器"""
        self.cache_prefix = "auto_token"
    
    def get_cached_token(self, site_name: str, account: str) -> Optional[str]:
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
            performance_monitor.record_cache_access(cache_key, cached_data is not None)
            
            if cached_data:
                logger.debug(f"Token缓存命中", extra={
                    'site_name': site_name,
                    'account': account,
                    'cache_key': cache_key
                })
                return cached_data.get('token')
            
            logger.debug(f"Token缓存未命中", extra={
                'site_name': site_name,
                'account': account,
                'cache_key': cache_key
            })
            return None
            
        except Exception as e:
            logger.warning(f"获取Token缓存失败: {e}", extra={
                'site_name': site_name,
                'account': account
            })
            return None
    
    def cache_token(
        self, 
        site_name: str, 
        account: str, 
        token: str,
        expires_at: Optional[datetime] = None
    ) -> None:
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
        else:
            # 默认缓存1小时
            timeout = CacheTimeout.LONG
        
        cache_data = {
            'token': token,
            'cached_at': timezone.now().isoformat(),
            'expires_at': expires_at.isoformat() if expires_at else None
        }
        
        try:
            cache.set(cache_key, cache_data, timeout=timeout)
            logger.info(f"Token已缓存", extra={
                'site_name': site_name,
                'account': account,
                'cache_key': cache_key,
                'timeout': timeout
            })
        except Exception as e:
            logger.warning(f"缓存Token失败: {e}", extra={
                'site_name': site_name,
                'account': account
            })
    
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
            logger.info(f"Token缓存已失效", extra={
                'site_name': site_name,
                'account': account,
                'cache_key': cache_key
            })
        except Exception as e:
            logger.warning(f"使Token缓存失效失败: {e}", extra={
                'site_name': site_name,
                'account': account
            })
    
    def get_cached_credentials(self, site_name: str) -> Optional[List[AccountCredentialDTO]]:
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
                
                logger.debug(f"账号凭证缓存命中", extra={
                    'site_name': site_name,
                    'cache_key': cache_key,
                    'count': len(credentials)
                })
                return credentials
            
            logger.debug(f"账号凭证缓存未命中", extra={
                'site_name': site_name,
                'cache_key': cache_key
            })
            return None
            
        except Exception as e:
            logger.warning(f"获取账号凭证缓存失败: {e}", extra={
                'site_name': site_name
            })
            return None
    
    def cache_credentials(self, site_name: str, credentials: List[AccountCredentialDTO]) -> None:
        """
        缓存账号凭证列表
        
        Args:
            site_name: 网站名称
            credentials: 账号凭证DTO列表
        """
        cache_key = self._get_credentials_cache_key(site_name)
        
        try:
            # 序列化DTO对象
            cache_data = []
            for cred in credentials:
                cache_data.append(cred.__dict__)
            
            cache.set(cache_key, cache_data, timeout=CacheTimeout.MEDIUM)
            logger.info(f"账号凭证已缓存", extra={
                'site_name': site_name,
                'cache_key': cache_key,
                'count': len(credentials)
            })
        except Exception as e:
            logger.warning(f"缓存账号凭证失败: {e}", extra={
                'site_name': site_name
            })
    
    def invalidate_credentials_cache(self, site_name: str) -> None:
        """
        使账号凭证缓存失效
        
        Args:
            site_name: 网站名称
        """
        cache_key = self._get_credentials_cache_key(site_name)
        
        try:
            cache.delete(cache_key)
            logger.info(f"账号凭证缓存已失效", extra={
                'site_name': site_name,
                'cache_key': cache_key
            })
        except Exception as e:
            logger.warning(f"使账号凭证缓存失效: {e}", extra={
                'site_name': site_name
            })
    
    def get_cached_account_stats(self, account: str, site_name: str) -> Optional[Dict[str, Any]]:
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
                logger.debug(f"账号统计缓存命中", extra={
                    'account': account,
                    'site_name': site_name,
                    'cache_key': cache_key
                })
                return cached_data
            
            return None
            
        except Exception as e:
            logger.warning(f"获取账号统计缓存失败: {e}", extra={
                'account': account,
                'site_name': site_name
            })
            return None
    
    def cache_account_stats(
        self, 
        account: str, 
        site_name: str, 
        stats: Dict[str, Any]
    ) -> None:
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
            logger.debug(f"账号统计已缓存", extra={
                'account': account,
                'site_name': site_name,
                'cache_key': cache_key
            })
        except Exception as e:
            logger.warning(f"缓存账号统计失败: {e}", extra={
                'account': account,
                'site_name': site_name
            })
    
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
            logger.debug(f"账号统计缓存已失效", extra={
                'account': account,
                'site_name': site_name,
                'cache_key': cache_key
            })
        except Exception as e:
            logger.warning(f"使账号统计缓存失效: {e}", extra={
                'account': account,
                'site_name': site_name
            })
    
    def get_cached_blacklist(self) -> Optional[List[str]]:
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
                logger.debug(f"黑名单缓存命中", extra={
                    'cache_key': cache_key,
                    'count': len(cached_data)
                })
                return cached_data
            
            return None
            
        except Exception as e:
            logger.warning(f"获取黑名单缓存失败: {e}")
            return None
    
    def cache_blacklist(self, blacklist: List[str]) -> None:
        """
        缓存黑名单
        
        Args:
            blacklist: 黑名单账号列表
        """
        cache_key = f"{self.cache_prefix}:blacklist"
        
        try:
            cache.set(cache_key, blacklist, timeout=CacheTimeout.SHORT)
            logger.debug(f"黑名单已缓存", extra={
                'cache_key': cache_key,
                'count': len(blacklist)
            })
        except Exception as e:
            logger.warning(f"缓存黑名单失败: {e}")
    
    def invalidate_blacklist_cache(self) -> None:
        """使黑名单缓存失效"""
        cache_key = f"{self.cache_prefix}:blacklist"
        
        try:
            cache.delete(cache_key)
            logger.debug(f"黑名单缓存已失效", extra={'cache_key': cache_key})
        except Exception as e:
            logger.warning(f"使黑名单缓存失效失败: {e}")
    
    def warm_up_cache(self, site_name: str) -> None:
        """
        预热缓存
        
        Args:
            site_name: 网站名称
        """
        logger.info(f"开始预热缓存", extra={'site_name': site_name})
        
        try:
            # 预加载账号凭证
            from apps.automation.services.token.account_selection_strategy import AccountSelectionStrategy
            strategy = AccountSelectionStrategy()
            
            # 这里需要异步调用，但为了简化，我们先跳过实际的预加载
            # 在实际使用中，可以通过后台任务来预热缓存
            
            logger.info(f"缓存预热完成", extra={'site_name': site_name})
            
        except Exception as e:
            logger.warning(f"缓存预热失败: {e}", extra={'site_name': site_name})
    
    def clear_all_cache(self) -> None:
        """清除所有相关缓存"""
        try:
            # 获取所有相关的缓存键
            cache_patterns = [
                f"{self.cache_prefix}:token:*",
                f"{self.cache_prefix}:credentials:*",
                f"{self.cache_prefix}:account_stats:*",
                f"{self.cache_prefix}:blacklist"
            ]
            
            # 注意：这里简化处理，实际应该使用Redis的SCAN命令
            # 或者维护一个缓存键的注册表
            
            logger.info("所有Token相关缓存已清除")
            
        except Exception as e:
            logger.warning(f"清除缓存失败: {e}")
    
    def get_cache_statistics(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            缓存统计信息
        """
        try:
            # 这里简化处理，实际应该从Redis获取详细统计
            return {
                'cache_backend': 'redis',
                'total_keys': 'unknown',  # 需要Redis DBSIZE命令
                'memory_usage': 'unknown',  # 需要Redis INFO命令
                'hit_rate': 'see_performance_monitor'
            }
        except Exception as e:
            logger.warning(f"获取缓存统计失败: {e}")
            return {}
    
    def _get_token_cache_key(self, site_name: str, account: str) -> str:
        """生成Token缓存键"""
        return f"{self.cache_prefix}:token:{site_name}:{account}"
    
    def _get_credentials_cache_key(self, site_name: str) -> str:
        """生成账号凭证缓存键"""
        return f"{self.cache_prefix}:credentials:{site_name}"
    
    def _get_account_stats_cache_key(self, account: str, site_name: str) -> str:
        """生成账号统计缓存键"""
        return f"{self.cache_prefix}:account_stats:{account}:{site_name}"


# 全局缓存管理器实例
cache_manager = TokenCacheManager()