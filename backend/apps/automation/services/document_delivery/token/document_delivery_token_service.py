"""
文书送达 Token 管理服务

负责 Token 的获取、缓存和刷新，从 DocumentDeliveryService 中提取。
"""
import asyncio
import logging
import traceback
from typing import Optional, TYPE_CHECKING

from apps.core.interfaces import ServiceLocator, AccountCredentialDTO
from apps.automation.utils.logging import AutomationLogger

if TYPE_CHECKING:
    from apps.automation.services.token.cache_manager import TokenCacheManager
    from apps.automation.services.token.auto_token_acquisition_service import AutoTokenAcquisitionService

logger = logging.getLogger("apps.automation")


class DocumentDeliveryTokenService:
    """
    文书送达 Token 管理服务
    
    职责：
    1. Token 获取（带缓存）
    2. Token 刷新（过期时自动刷新）
    3. 通过 AutoTokenAcquisitionService 获取新 Token
    
    Requirements: 1.1, 1.3, 5.1, 5.2, 5.5
    """
    
    def __init__(
        self,
        cache_manager: Optional["TokenCacheManager"] = None,
        auto_token_service: Optional["AutoTokenAcquisitionService"] = None,
    ):
        """
        初始化 Token 管理服务
        
        Args:
            cache_manager: Token 缓存管理器（可选，用于依赖注入）
            auto_token_service: 自动 Token 获取服务（可选，用于依赖注入）
        """
        self._cache_manager = cache_manager
        self._auto_token_service = auto_token_service
        
        logger.debug("DocumentDeliveryTokenService 初始化完成")
    
    @property
    def cache_manager(self) -> "TokenCacheManager":
        """延迟加载缓存管理器"""
        if self._cache_manager is None:
            from apps.automation.services.token.cache_manager import cache_manager
            self._cache_manager = cache_manager
        return self._cache_manager
    
    @property
    def auto_token_service(self) -> "AutoTokenAcquisitionService":
        """延迟加载自动 Token 获取服务"""
        if self._auto_token_service is None:
            from apps.automation.services.token.auto_token_acquisition_service import (
                AutoTokenAcquisitionService
            )
            self._auto_token_service = AutoTokenAcquisitionService()
        return self._auto_token_service
    
    def acquire_token(self, credential_id: int) -> Optional[str]:
        """
        获取 Token（带缓存和自动刷新）
        
        流程：
        1. 获取凭证信息
        2. 尝试从缓存获取有效 Token
        3. 缓存无效时，调用 auto_token_acquisition_service 获取新 Token
        4. 获取成功后缓存 Token
        5. Token 过期时自动刷新
        6. 失败时返回 None，由调用方降级到 Playwright
        
        Args:
            credential_id: 账号凭证 ID
            
        Returns:
            Token 字符串，获取失败返回 None
            
        Requirements: 5.1, 5.2, 5.3, 5.4
        """
        logger.info(f"获取 Token: credential_id={credential_id}")
        
        try:
            # 1. 获取凭证信息以确定 site_name 和 account
            organization_service = ServiceLocator.get_organization_service()
            credential = organization_service.get_credential_internal(credential_id)
            
            if not credential:
                logger.warning(f"凭证不存在: credential_id={credential_id}")
                return None
            
            site_name = credential.site_name
            account = credential.account
            logger.info(f"凭证信息: site_name={site_name}, account={account}")
            
            # 2. 尝试从缓存获取 Token（最快路径）
            cached_token = self.cache_manager.get_cached_token(site_name, account)
            if cached_token:
                logger.info(f"✅ 从缓存获取 Token 成功: credential_id={credential_id}")
                # 记录日志
                AutomationLogger.log_existing_token_used(
                    acquisition_id=f"doc_delivery_{credential_id}",
                    site_name=site_name,
                    account=account,
                    acquisition_method="cache"
                )
                return cached_token
            
            logger.info(f"缓存未命中，尝试从数据库获取或重新登录")
            
            # 3. 缓存未命中，使用 AutoTokenAcquisitionService 获取 Token
            # 该服务内部会检查数据库、执行登录、并缓存结果
            token = self._acquire_token_via_service(site_name, credential_id)
            
            if token:
                logger.info(f"✅ Token 获取成功: credential_id={credential_id}")
                return token
            else:
                logger.warning(f"Token 获取返回空值，将降级到 Playwright")
                return None
                
        except Exception as e:
            logger.error(f"Token 获取异常: [{type(e).__name__}] {str(e)}")
            # 记录详细错误信息
            AutomationLogger.log_api_error_detail(
                api_name="token_acquisition",
                error_type=type(e).__name__,
                error_message=str(e),
                stack_trace=traceback.format_exc()
            )
            return None
    
    def _acquire_token_via_service(
        self,
        site_name: str,
        credential_id: int
    ) -> Optional[str]:
        """
        通过 AutoTokenAcquisitionService 获取 Token
        
        处理异步调用的封装，支持在同步上下文中调用异步服务。
        
        Args:
            site_name: 网站名称
            credential_id: 凭证 ID
            
        Returns:
            Token 字符串，获取失败返回 None
            
        Requirements: 5.1, 5.2
        """
        try:
            # 检查是否已经在事件循环中
            try:
                loop = asyncio.get_running_loop()
                # 如果已经在事件循环中，使用 run_coroutine_threadsafe
                import concurrent.futures
                future = asyncio.run_coroutine_threadsafe(
                    self.auto_token_service.acquire_token_if_needed(
                        site_name=site_name,
                        credential_id=credential_id
                    ),
                    loop
                )
                # 等待结果，设置超时
                token = future.result(timeout=120)
            except RuntimeError:
                # 没有运行中的事件循环，使用 asyncio.run
                token = asyncio.run(
                    self.auto_token_service.acquire_token_if_needed(
                        site_name=site_name,
                        credential_id=credential_id
                    )
                )
            
            return token
            
        except Exception as e:
            logger.error(f"AutoTokenAcquisitionService 调用失败: {str(e)}")
            return None
    
    def refresh_token_if_expired(
        self,
        credential_id: int,
        current_token: str
    ) -> Optional[str]:
        """
        检查 Token 是否过期，如果过期则刷新
        
        通过尝试一个简单的 API 调用来验证 Token 有效性，
        如果返回 401 则刷新 Token。
        
        Args:
            credential_id: 凭证 ID
            current_token: 当前 Token
            
        Returns:
            有效的 Token（可能是原 Token 或新获取的 Token），
            刷新失败返回 None
            
        Requirements: 5.2, 5.4
        """
        from apps.automation.services.document_delivery.court_document_api_client import (
            CourtDocumentApiClient,
            TokenExpiredError
        )
        
        try:
            # 创建 API 客户端用于验证 Token
            api_client = CourtDocumentApiClient()
            
            # 尝试使用当前 Token 获取文书列表（只获取1条，用于验证）
            test_response = api_client.fetch_document_list(
                token=current_token,
                page_num=1,
                page_size=1
            )
            
            # Token 有效
            logger.debug(f"Token 验证通过: credential_id={credential_id}")
            return current_token
            
        except TokenExpiredError:
            # Token 过期，需要刷新
            logger.info(f"Token 已过期，开始刷新: credential_id={credential_id}")
            
            # 获取凭证信息
            organization_service = ServiceLocator.get_organization_service()
            credential = organization_service.get_credential_internal(credential_id)
            
            if not credential:
                logger.warning(f"凭证不存在，无法刷新 Token")
                return None
            
            # 使缓存失效
            self.cache_manager.invalidate_token_cache(credential.site_name, credential.account)
            
            # 重新获取 Token
            new_token = self._acquire_token_via_service(
                site_name=credential.site_name,
                credential_id=credential_id
            )
            
            if new_token:
                logger.info(f"✅ Token 刷新成功: credential_id={credential_id}")
                return new_token
            else:
                logger.warning(f"Token 刷新失败: credential_id={credential_id}")
                return None
                
        except Exception as e:
            # 其他错误，假设 Token 仍然有效
            logger.warning(f"Token 验证时发生错误，假设 Token 有效: {str(e)}")
            return current_token
    
    def invalidate_token(self, credential_id: int) -> bool:
        """
        使指定凭证的 Token 缓存失效
        
        Args:
            credential_id: 凭证 ID
            
        Returns:
            是否成功使缓存失效
        """
        try:
            # 获取凭证信息
            organization_service = ServiceLocator.get_organization_service()
            credential = organization_service.get_credential_internal(credential_id)
            
            if not credential:
                logger.warning(f"凭证不存在: credential_id={credential_id}")
                return False
            
            # 使缓存失效
            self.cache_manager.invalidate_token_cache(credential.site_name, credential.account)
            logger.info(f"Token 缓存已失效: credential_id={credential_id}")
            return True
            
        except Exception as e:
            logger.error(f"使 Token 缓存失效失败: {str(e)}")
            return False
