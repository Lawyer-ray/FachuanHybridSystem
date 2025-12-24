"""
账号选择策略服务

实现基于最近登录成功时间的账号排序逻辑，
添加账号黑名单机制，避免重复使用失败账号。
集成缓存管理和性能监控。
"""
import logging
from typing import Optional, List
from django.db import models
from django.utils import timezone
from datetime import timedelta

from apps.core.interfaces import IAccountSelectionStrategy, AccountCredentialDTO
from apps.core.exceptions import ValidationException
from .cache_manager import cache_manager
from .performance_monitor import performance_monitor

logger = logging.getLogger(__name__)


class AccountSelectionStrategy:
    """
    账号选择策略实现
    
    基于以下优先级选择账号：
    1. 优先使用标记为preferred的账号
    2. 按最近成功登录时间排序
    3. 排除黑名单中的账号
    4. 考虑登录成功率
    """
    
    def __init__(self, blacklist_duration_hours: int = 1):
        """
        初始化账号选择策略
        
        Args:
            blacklist_duration_hours: 黑名单持续时间（小时）
        """
        self.blacklist_duration_hours = blacklist_duration_hours
        self._blacklist: List[str] = []
    
    async def select_account(
        self, 
        site_name: str, 
        exclude_accounts: Optional[List[str]] = None
    ) -> Optional[AccountCredentialDTO]:
        """
        选择用于登录的账号
        
        Args:
            site_name: 网站名称
            exclude_accounts: 需要排除的账号列表
            
        Returns:
            选中的账号凭证DTO，无可用账号时返回None
        """
        if not site_name:
            from apps.core.exceptions import ValidationException
            raise ValidationException("网站名称不能为空")
        
        # 从缓存获取黑名单
        cached_blacklist = cache_manager.get_cached_blacklist()
        if cached_blacklist is not None:
            self._blacklist = cached_blacklist
        
        logger.info(f"开始选择账号", extra={
            "site_name": site_name,
            "exclude_accounts": exclude_accounts or [],
            "blacklist": self._blacklist
        })
        
        # 尝试从缓存获取账号列表
        available_accounts = cache_manager.get_cached_credentials(site_name)
        
        if available_accounts is None:
            # 缓存未命中，从数据库获取
            available_accounts = await self._get_available_accounts(
                site_name, exclude_accounts or []
            )
            
            # 缓存账号列表
            if available_accounts:
                cache_manager.cache_credentials(site_name, available_accounts)
        else:
            # 缓存命中，但需要过滤排除的账号
            all_excluded = set((exclude_accounts or []) + self._blacklist)
            if all_excluded:
                available_accounts = [
                    acc for acc in available_accounts 
                    if acc.account not in all_excluded
                ]
        
        if not available_accounts:
            logger.warning(f"没有找到可用账号", extra={"site_name": site_name})
            return None
        
        # 选择最优账号
        selected_account = self._select_best_account(available_accounts)
        
        logger.info(f"选择账号成功", extra={
            "site_name": site_name,
            "selected_account": selected_account.account,
            "last_login_success": selected_account.last_login_success_at,
            "success_count": selected_account.login_success_count
        })
        
        return selected_account
    
    async def _get_available_accounts(
        self, 
        site_name: str, 
        exclude_accounts: List[str]
    ) -> List[AccountCredentialDTO]:
        """
        获取所有可用账号
        
        Args:
            site_name: 网站名称
            exclude_accounts: 排除的账号列表
            
        Returns:
            可用账号DTO列表
        """
        from asgiref.sync import sync_to_async
        
        # 使用sync_to_async包装同步的数据库查询
        @sync_to_async
        def get_credentials():
            # 通过ServiceLocator获取organization服务
            from apps.core.interfaces import ServiceLocator
            organization_service = ServiceLocator.get_organization_service()
            
            # 获取指定站点的凭证
            credentials = organization_service.get_credentials_by_site_internal(site_name)
            
            # 排除指定账号
            all_excluded = set(exclude_accounts + self._blacklist)
            if all_excluded:
                credentials = [c for c in credentials if c.account not in all_excluded]
            
            # 直接返回DTO列表（organization服务已经返回DTO）
            return credentials
        
        return await get_credentials()
    
    def _select_best_account(self, accounts: List[AccountCredentialDTO]) -> AccountCredentialDTO:
        """
        从可用账号中选择最优账号
        
        Args:
            accounts: 可用账号列表
            
        Returns:
            最优账号DTO
        """
        if not accounts:
            from apps.core.exceptions import ValidationException
            raise ValidationException("没有可用账号")
        
        # 按优先级排序
        def sort_key(account: AccountCredentialDTO):
            # 1. 优先使用preferred账号
            preferred_score = 1000 if account.is_preferred else 0
            
            # 2. 最近成功登录时间（越近越好）
            if account.last_login_success_at:
                from datetime import datetime
                import pytz
                last_login = datetime.fromisoformat(account.last_login_success_at.replace('Z', '+00:00'))
                if last_login.tzinfo is None:
                    last_login = pytz.UTC.localize(last_login)
                hours_since_login = (timezone.now() - last_login).total_seconds() / 3600
                recency_score = max(0, 100 - hours_since_login)  # 100小时内线性递减
            else:
                recency_score = 0  # 从未成功登录
            
            # 3. 成功次数
            success_score = min(account.login_success_count, 50)  # 最多50分
            
            # 4. 成功率（避免除零）
            total_attempts = account.login_success_count + account.login_failure_count
            if total_attempts > 0:
                success_rate_score = (account.login_success_count / total_attempts) * 20
            else:
                success_rate_score = 10  # 新账号给予中等分数
            
            return -(preferred_score + recency_score + success_score + success_rate_score)
        
        # 排序并选择最优账号
        sorted_accounts = sorted(accounts, key=sort_key)
        return sorted_accounts[0]
    
    def add_to_blacklist(self, account: str) -> None:
        """
        将账号添加到黑名单
        
        Args:
            account: 账号名称
        """
        if account not in self._blacklist:
            self._blacklist.append(account)
            # 更新缓存
            cache_manager.cache_blacklist(self._blacklist)
            logger.info(f"账号已添加到黑名单", extra={"account": account})
    
    def remove_from_blacklist(self, account: str) -> None:
        """
        从黑名单中移除账号
        
        Args:
            account: 账号名称
        """
        if account in self._blacklist:
            self._blacklist.remove(account)
            # 更新缓存
            cache_manager.cache_blacklist(self._blacklist)
            logger.info(f"账号已从黑名单移除", extra={"account": account})
    
    def clear_blacklist(self) -> None:
        """清空黑名单"""
        self._blacklist.clear()
        # 清除缓存
        cache_manager.invalidate_blacklist_cache()
        logger.info("黑名单已清空")
    
    def get_blacklist(self) -> List[str]:
        """获取当前黑名单"""
        return self._blacklist.copy()
    
    async def update_account_statistics(
        self, 
        account: str, 
        site_name: str, 
        success: bool
    ) -> None:
        """
        更新账号登录统计
        
        Args:
            account: 账号名称
            site_name: 网站名称
            success: 是否登录成功
        """
        try:
            from asgiref.sync import sync_to_async
            
            @sync_to_async
            def update_credential():
                # 通过ServiceLocator获取organization服务
                from apps.core.interfaces import ServiceLocator
                organization_service = ServiceLocator.get_organization_service()
                
                # 获取凭证
                cred = organization_service.get_credential_by_account_internal(account, site_name)
                
                # 更新登录统计
                if success:
                    organization_service.update_login_success_internal(cred.id)
                    # 重新获取更新后的值
                    cred = organization_service.get_credential_internal(cred.id)
                    return cred.login_success_count, None
                else:
                    service.update_login_failure(cred.id)
                    # 重新获取更新后的值
                    cred.refresh_from_db()
                    return None, cred.login_failure_count
            
            success_count, failure_count = await update_credential()
            
            # 更新缓存的统计信息
            stats = {
                'success_count': success_count if success else None,
                'failure_count': failure_count if not success else None,
                'last_updated': timezone.now().isoformat()
            }
            cache_manager.cache_account_stats(account, site_name, stats)
            
            # 使账号凭证缓存失效（因为统计信息已更新）
            cache_manager.invalidate_credentials_cache(site_name)
            
            if success:
                # 成功后从黑名单移除
                self.remove_from_blacklist(account)
                logger.info(f"账号登录成功统计已更新", extra={
                    "account": account,
                    "site_name": site_name,
                    "success_count": success_count
                })
            else:
                # 失败后添加到黑名单
                self.add_to_blacklist(account)
                logger.warning(f"账号登录失败统计已更新", extra={
                    "account": account,
                    "site_name": site_name,
                    "failure_count": failure_count
                })
                
        except Exception as e:
            logger.error(f"更新账号统计失败", extra={
                "account": account,
                "site_name": site_name,
                "success": success,
                "error": str(e)
            })