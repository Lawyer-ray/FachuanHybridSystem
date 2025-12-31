"""
Token 管理服务
提供 Token 的保存、获取、删除等功能
"""
import logging
from typing import Optional
from datetime import timedelta
from django.core.cache import cache
from django.utils import timezone

from apps.core.interfaces import ITokenService

logger = logging.getLogger("apps.automation")


class TokenService:
    """
    Token 管理服务
    
    使用 Redis + 数据库双层存储：
    - Redis: 快速访问，支持过期时间
    - 数据库: 持久化存储，防止 Redis 重启丢失
    """
    
    CACHE_KEY_PREFIX = "court_token"
    DEFAULT_EXPIRES_IN = 600  # 默认 10 分钟（Token 实际有效期）
    
    def save_token(
        self,
        site_name: str,
        account: str,
        token: str,
        expires_in: int = None,
        token_type: str = "Bearer",
        credential_id: int = None
    ) -> None:
        """
        保存 Token 到 Redis + 数据库
        
        Args:
            site_name: 网站名称，如 "court_zxfw"
            account: 账号
            token: Token 字符串
            expires_in: 过期时间（秒），None 则使用默认值
            token_type: Token 类型，如 "Bearer", "JWT"
            credential_id: 凭证ID，用于关联 TokenAcquisitionHistory
        """
        if expires_in is None:
            expires_in = self.DEFAULT_EXPIRES_IN
        
        try:
            # 1. 保存到 Redis（快速访问）
            cache_key = self._get_cache_key(site_name, account)
            cache.set(cache_key, token, timeout=expires_in)
            logger.info(f"✅ Token 已保存到 Redis: {site_name} - {account}")
            
            # 2. 保存到数据库（持久化）
            from apps.automation.models import CourtToken, TokenAcquisitionHistory, TokenAcquisitionStatus
            
            expires_at = timezone.now() + timedelta(seconds=expires_in)
            
            CourtToken.objects.update_or_create(
                site_name=site_name,
                account=account,
                defaults={
                    "token": token,
                    "token_type": token_type,
                    "expires_at": expires_at,
                }
            )
            logger.info(f"✅ Token 已保存到数据库: {site_name} - {account}")
            logger.info(f"   过期时间: {expires_at}")
            
            # 3. 记录Token获取历史
            TokenAcquisitionHistory.objects.create(
                site_name=site_name,
                account=account,
                credential_id=credential_id,
                status=TokenAcquisitionStatus.SUCCESS,
                trigger_reason="manual_login_test",
                attempt_count=1,
                token_preview=token[:50] if token else None,
                created_at=timezone.now()
            )
            logger.info(f"✅ Token获取历史已记录: {site_name} - {account} (credential_id={credential_id})")
        
        except Exception as e:
            logger.error(f"保存 Token 失败: {e}", exc_info=True)
            raise
    
    def get_token(self, site_name: str, account: str) -> Optional[str]:
        """
        获取 Token（优先从 Redis，Redis 没有则从数据库）
        
        Args:
            site_name: 网站名称
            account: 账号
            
        Returns:
            Token 字符串，不存在或已过期返回 None
        """
        try:
            # 1. 先从 Redis 获取
            cache_key = self._get_cache_key(site_name, account)
            token = cache.get(cache_key)
            
            if token:
                logger.info(f"✅ 从 Redis 获取 Token: {site_name} - {account}")
                return token
            
            # 2. Redis 没有，从数据库获取
            from apps.automation.models import CourtToken
            
            try:
                token_obj = CourtToken.objects.get(
                    site_name=site_name,
                    account=account,
                )
                
                # 检查是否过期
                if token_obj.is_expired():
                    logger.warning(f"Token 已过期: {site_name} - {account}")
                    # 删除过期的 Token
                    token_obj.delete()
                    return None
                
                # 回填到 Redis
                remaining_seconds = int((token_obj.expires_at - timezone.now()).total_seconds())
                if remaining_seconds > 0:
                    cache.set(cache_key, token_obj.token, timeout=remaining_seconds)
                    logger.info(f"✅ 从数据库获取 Token 并回填到 Redis: {site_name} - {account}")
                
                return token_obj.token
            
            except CourtToken.DoesNotExist:
                logger.info(f"Token 不存在: {site_name} - {account}")
                return None
        
        except Exception as e:
            logger.error(f"获取 Token 失败: {e}", exc_info=True)
            return None
    
    def delete_token(self, site_name: str, account: str) -> None:
        """
        删除 Token（同时删除 Redis 和数据库）
        
        Args:
            site_name: 网站名称
            account: 账号
        """
        try:
            # 1. 删除 Redis
            cache_key = self._get_cache_key(site_name, account)
            cache.delete(cache_key)
            logger.info(f"✅ 已从 Redis 删除 Token: {site_name} - {account}")
            
            # 2. 删除数据库
            from apps.automation.models import CourtToken
            
            deleted_count, _ = CourtToken.objects.filter(
                site_name=site_name,
                account=account
            ).delete()
            
            if deleted_count > 0:
                logger.info(f"✅ 已从数据库删除 Token: {site_name} - {account}")
            else:
                logger.info(f"数据库中没有找到 Token: {site_name} - {account}")
        
        except Exception as e:
            logger.error(f"删除 Token 失败: {e}", exc_info=True)
            raise
    
    def get_token_info(self, site_name: str, account: str) -> Optional[dict]:
        """
        获取 Token 详细信息
        
        Args:
            site_name: 网站名称
            account: 账号
            
        Returns:
            Token 信息字典，包含 token, token_type, expires_at 等
        """
        try:
            from apps.automation.models import CourtToken
            
            token_obj = CourtToken.objects.get(
                site_name=site_name,
                account=account,
            )
            
            if token_obj.is_expired():
                logger.warning(f"Token 已过期: {site_name} - {account}")
                return None
            
            return {
                "token": token_obj.token,
                "token_type": token_obj.token_type,
                "expires_at": token_obj.expires_at,
                "created_at": token_obj.created_at,
                "updated_at": token_obj.updated_at,
            }
        
        except CourtToken.DoesNotExist:
            logger.info(f"Token 不存在: {site_name} - {account}")
            return None
        except Exception as e:
            logger.error(f"获取 Token 信息失败: {e}", exc_info=True)
            return None
    
    def _get_cache_key(self, site_name: str, account: str) -> str:
        """
        生成 Redis 缓存 key
        
        Args:
            site_name: 网站名称
            account: 账号
            
        Returns:
            缓存 key
        """
        return f"{self.CACHE_KEY_PREFIX}:{site_name}:{account}"


class TokenServiceAdapter(ITokenService):
    """
    Token 服务适配器
    
    实现 ITokenService Protocol，将 TokenService 适配为标准接口
    """
    
    def __init__(self, service: Optional[TokenService] = None):
        """
        初始化适配器
        
        Args:
            service: TokenService 实例，为 None 时创建新实例
        """
        self._service = service
    
    @property
    def service(self) -> TokenService:
        """延迟加载服务实例"""
        if self._service is None:
            self._service = TokenService()
        return self._service
    
    async def get_token(self, site_name: str) -> Optional[str]:
        """
        获取指定站点的 Token
        
        注意：当前实现假设每个站点只有一个默认账号
        实际使用时可能需要根据业务逻辑选择账号
        
        Args:
            site_name: 站点名称
            
        Returns:
            Token 字符串，不存在或已过期时返回 None
        """
        from asgiref.sync import sync_to_async
        # TODO: 这里需要根据实际业务逻辑获取账号
        # 暂时使用 "default" 作为默认账号
        account = "default"
        return await sync_to_async(self.service.get_token)(site_name, account)
    
    async def save_token(self, site_name: str, token: str, expires_in: int) -> None:
        """
        保存 Token
        
        Args:
            site_name: 站点名称
            token: Token 字符串
            expires_in: 过期时间（秒）
        """
        from asgiref.sync import sync_to_async
        # TODO: 这里需要根据实际业务逻辑获取账号
        # 暂时使用 "default" 作为默认账号
        account = "default"
        await sync_to_async(self.service.save_token)(site_name, account, token, expires_in)
    
    async def delete_token(self, site_name: str) -> None:
        """
        删除 Token
        
        Args:
            site_name: 站点名称
        """
        from asgiref.sync import sync_to_async
        # TODO: 这里需要根据实际业务逻辑获取账号
        # 暂时使用 "default" 作为默认账号
        account = "default"
        await sync_to_async(self.service.delete_token)(site_name, account)
    
    # 内部方法版本，供其他模块调用
    async def get_token_internal(self, site_name: str, account: str = "default") -> Optional[str]:
        """
        获取指定站点的 Token（内部接口，无权限检查）
        
        Args:
            site_name: 站点名称
            account: 账号名称
            
        Returns:
            Token 字符串，不存在或已过期时返回 None
        """
        from asgiref.sync import sync_to_async
        return await sync_to_async(self.service.get_token)(site_name, account)
    
    async def save_token_internal(self, site_name: str, account: str, token: str, expires_in: int) -> None:
        """
        保存 Token（内部接口，无权限检查）
        
        Args:
            site_name: 站点名称
            account: 账号名称
            token: Token 字符串
            expires_in: 过期时间（秒）
        """
        from asgiref.sync import sync_to_async
        logger.info(f"🔄 save_token_internal 开始: site={site_name}, account={account}, expires_in={expires_in}")
        try:
            await sync_to_async(self.service.save_token, thread_sensitive=True)(site_name, account, token, expires_in)
            logger.info(f"✅ save_token_internal 完成: site={site_name}, account={account}")
        except Exception as e:
            logger.error(f"❌ save_token_internal 失败: {e}", exc_info=True)
            raise
    
    async def delete_token_internal(self, site_name: str, account: str = "default") -> None:
        """
        删除 Token（内部接口，无权限检查）
        
        Args:
            site_name: 站点名称
            account: 账号名称
        """
        from asgiref.sync import sync_to_async
        await sync_to_async(self.service.delete_token)(site_name, account)
