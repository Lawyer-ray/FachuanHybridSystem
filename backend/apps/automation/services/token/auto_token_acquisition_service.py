"""
自动Token获取核心服务

实现财产保险询价任务的自动token获取机制。当系统检测到没有有效token时，
将自动触发法院一张网登录流程，获取新token后继续执行询价任务。
集成性能监控、缓存管理和并发优化。
"""
import asyncio
import logging
import time
from typing import Optional, Dict, Any, Set
from datetime import datetime, timedelta
from dataclasses import dataclass

from apps.core.interfaces import (
    IAutoTokenAcquisitionService, 
    IAccountSelectionStrategy, 
    IAutoLoginService,
    ITokenService,
    AccountCredentialDTO,
    LoginAttemptResult,
    TokenAcquisitionResult
)
from apps.core.exceptions import (
    AutoTokenAcquisitionError,
    LoginFailedError,
    NoAvailableAccountError,
    TokenAcquisitionTimeoutError,
    ValidationException
)
from .performance_monitor import performance_monitor
from .cache_manager import cache_manager
from .concurrency_optimizer import concurrency_optimizer, ConcurrencyConfig
from .history_recorder import history_recorder

logger = logging.getLogger(__name__)


@dataclass
class ConcurrencyConfig:
    """并发控制配置"""
    max_concurrent_acquisitions: int = 1  # 最大并发获取数量
    acquisition_timeout: float = 300.0  # 获取超时时间（秒）
    lock_timeout: float = 30.0  # 锁超时时间（秒）


class AutoTokenAcquisitionService:
    """
    自动Token获取核心服务实现
    
    功能：
    1. 检查token有效性，无效时自动获取
    2. 集成账号选择策略和自动登录服务
    3. 实现并发控制，避免多个任务同时触发登录
    4. 提供结构化日志记录，包含完整的执行轨迹
    5. 支持指定凭证ID或自动选择账号
    """
    
    # 类级别的并发控制
    _active_acquisitions: Set[str] = set()
    _acquisition_locks: Dict[str, asyncio.Lock] = {}
    _lock_creation_lock = asyncio.Lock()
    
    def __init__(
        self,
        account_selection_strategy: Optional[IAccountSelectionStrategy] = None,
        auto_login_service: Optional[IAutoLoginService] = None,
        token_service: Optional[ITokenService] = None,
        concurrency_config: Optional[ConcurrencyConfig] = None
    ):
        """
        初始化自动Token获取服务
        
        Args:
            account_selection_strategy: 账号选择策略，None则使用 ServiceLocator 获取默认实现
            auto_login_service: 自动登录服务，None则使用 ServiceLocator 获取默认实现
            token_service: Token服务，None则使用 ServiceLocator 获取默认实现
            concurrency_config: 并发控制配置，None则使用默认配置
        """
        self._account_selection_strategy = account_selection_strategy
        self._auto_login_service = auto_login_service
        self._token_service = token_service
        self.concurrency_config = concurrency_config or ConcurrencyConfig()
        
        # 执行统计（保留用于向后兼容）
        self._acquisition_count = 0
        self._success_count = 0
        self._failure_count = 0
    
    @property
    def account_selection_strategy(self) -> IAccountSelectionStrategy:
        """获取账号选择策略（延迟加载）"""
        if self._account_selection_strategy is None:
            from apps.core.interfaces import ServiceLocator
            self._account_selection_strategy = ServiceLocator.get_account_selection_strategy()
        return self._account_selection_strategy
    
    @property
    def auto_login_service(self) -> IAutoLoginService:
        """获取自动登录服务（延迟加载）"""
        if self._auto_login_service is None:
            from apps.core.interfaces import ServiceLocator
            self._auto_login_service = ServiceLocator.get_auto_login_service()
        return self._auto_login_service
    
    @property
    def token_service(self) -> ITokenService:
        """获取Token服务（延迟加载）"""
        if self._token_service is None:
            from apps.core.interfaces import ServiceLocator
            self._token_service = ServiceLocator.get_token_service()
        return self._token_service
    
    async def acquire_token_if_needed(
        self, 
        site_name: str, 
        credential_id: Optional[int] = None
    ) -> str:
        """
        如果需要则自动获取token
        
        Args:
            site_name: 网站名称
            credential_id: 指定的凭证ID（可选）
            
        Returns:
            有效的token字符串
            
        Raises:
            AutoTokenAcquisitionError: Token获取失败
            ValidationException: 参数验证失败
            NoAvailableAccountError: 无可用账号
            TokenAcquisitionTimeoutError: 获取超时
        """
        start_time = time.time()
        acquisition_id = f"{site_name}_{credential_id or 'auto'}_{int(start_time)}"
        
        # 参数验证
        if not site_name:
            raise ValidationException("网站名称不能为空")
        
        from apps.automation.utils.logging import AutomationLogger
        AutomationLogger.log_token_acquisition_start(
            acquisition_id=acquisition_id,
            site_name=site_name,
            credential_id=credential_id,
            trigger_reason="token_needed"
        )
        
        self._acquisition_count += 1
        
        # 记录性能监控开始
        performance_monitor.record_acquisition_start(
            acquisition_id, site_name, credential_id or "auto"
        )
        
        try:
            # 并发控制和资源获取
            await concurrency_optimizer.acquire_resource(
                acquisition_id, site_name, credential_id or "auto"
            )
            
            try:
                # 再次检查token（可能在等待期间已被其他任务获取）
                from asgiref.sync import sync_to_async
                
                if credential_id:
                    credential = await self._get_credential_by_id(credential_id)
                    if not credential:
                        raise ValidationException(f"无效的凭证ID: {credential_id}")
                    
                    # 先检查缓存
                    existing_token = cache_manager.get_cached_token(site_name, credential.account)
                    if not existing_token:
                        # 缓存未命中，检查数据库
                        existing_token = await sync_to_async(self.token_service.get_token)(site_name, credential.account)
                        if existing_token:
                            # 缓存Token
                            cache_manager.cache_token(site_name, credential.account, existing_token)
                    
                    if existing_token:
                        AutomationLogger.log_existing_token_used(
                            acquisition_id=acquisition_id,
                            site_name=site_name,
                            account=credential.account,
                            acquisition_method="existing"
                        )
                        return existing_token
                else:
                    # 对于自动选择账号的情况，先选择账号然后检查该账号是否有有效token
                    credential = await self.account_selection_strategy.select_account(site_name)
                    if credential:
                        # 先检查缓存
                        existing_token = cache_manager.get_cached_token(site_name, credential.account)
                        if not existing_token:
                            # 缓存未命中，检查数据库
                            existing_token = await sync_to_async(self.token_service.get_token)(site_name, credential.account)
                            if existing_token:
                                # 缓存Token
                                cache_manager.cache_token(site_name, credential.account, existing_token)
                        
                        if existing_token:
                            logger.info(f"使用现有Token（自动选择账号）", extra={
                                "acquisition_id": acquisition_id,
                                "site_name": site_name,
                                "account": credential.account,
                                "acquisition_method": "existing"
                            })
                            return existing_token
                    else:
                        # 没有找到可用账号
                        logger.error(f"没有找到可用账号", extra={
                            "acquisition_id": acquisition_id,
                            "site_name": site_name
                        })
                        raise NoAvailableAccountError(f"网站 {site_name} 没有配置可用账号，请先在 /admin/organization/accountcredential/ 添加账号")
                
                # 执行自动登录获取token
                result = await self._acquire_token_by_login(
                    acquisition_id, site_name, credential_id, credential
                )
                
                total_duration = time.time() - start_time
                
                if result.success:
                    self._success_count += 1
                    
                    # 记录性能监控结束（成功）
                    performance_monitor.record_acquisition_end(
                        acquisition_id, True, total_duration,
                        result.login_attempts[0].attempt_duration if result.login_attempts else None
                    )
                    
                    # 记录历史到数据库
                    await history_recorder.record_acquisition_history(
                        acquisition_id, site_name, 
                        credential.account if credential else "unknown",
                        credential_id, result, "token_needed"
                    )
                    
                    AutomationLogger.log_token_acquisition_success(
                        acquisition_id=acquisition_id,
                        site_name=site_name,
                        account=credential.account,
                        total_duration=total_duration,
                        acquisition_method=result.acquisition_method,
                        login_attempts=len(result.login_attempts),
                        success_rate=self._success_count / self._acquisition_count
                    )
                    return result.token
                else:
                    self._failure_count += 1
                    error_msg = f"Token获取失败: {result.error_details.get('message', '未知错误')}"
                    
                    # 记录性能监控结束（失败）
                    error_type = result.error_details.get('error_type', 'unknown')
                    performance_monitor.record_acquisition_end(
                        acquisition_id, False, total_duration,
                        error_type=error_type
                    )
                    
                    # 记录历史到数据库
                    await history_recorder.record_acquisition_history(
                        acquisition_id, site_name,
                        credential.account if credential else "unknown", 
                        credential_id, result, "token_needed"
                    )
                    
                    logger.error(f"Token获取失败", extra={
                        "acquisition_id": acquisition_id,
                        "site_name": site_name,
                        "total_duration": total_duration,
                        "error_details": result.error_details,
                        "login_attempts": len(result.login_attempts),
                        "failure_rate": self._failure_count / self._acquisition_count
                    })
                    raise AutoTokenAcquisitionError(
                        message=error_msg,
                        code="TOKEN_ACQUISITION_FAILED",
                        errors=result.error_details
                    )
            
            finally:
                # 释放并发资源
                await concurrency_optimizer.release_resource(
                    acquisition_id, site_name, credential_id or "auto"
                )
        
        except Exception as e:
            total_duration = time.time() - start_time
            
            # 记录性能监控结束（异常）
            error_type = type(e).__name__
            performance_monitor.record_acquisition_end(
                acquisition_id, False, total_duration, error_type=error_type
            )
            
            if isinstance(e, (AutoTokenAcquisitionError, ValidationException, 
                            NoAvailableAccountError, TokenAcquisitionTimeoutError)):
                raise
            else:
                self._failure_count += 1
                logger.error(f"Token获取过程中发生未预期错误", extra={
                    "acquisition_id": acquisition_id,
                    "site_name": site_name,
                    "error": str(e),
                    "total_duration": total_duration
                }, exc_info=True)
                
                raise AutoTokenAcquisitionError(
                    message=f"Token获取过程中发生未预期错误: {str(e)}",
                    code="TOKEN_ACQUISITION_ERROR",
                    errors={"original_error": str(e)}
                )
    
    async def _get_acquisition_lock(self, site_name: str) -> asyncio.Lock:
        """
        获取站点级别的获取锁
        
        Args:
            site_name: 网站名称
            
        Returns:
            异步锁对象
        """
        async with self._lock_creation_lock:
            if site_name not in self._acquisition_locks:
                self._acquisition_locks[site_name] = asyncio.Lock()
            return self._acquisition_locks[site_name]
    
    async def _check_any_valid_token(self, site_name: str) -> Optional[str]:
        """
        检查是否有任何有效token
        
        Args:
            site_name: 网站名称
            
        Returns:
            有效的token，无则返回None
        """
        try:
            # 获取所有该站点的账号
            available_accounts = await self.account_selection_strategy.select_account(site_name)
            if not available_accounts:
                return None
            
            # 检查该账号的token（使用sync_to_async包装同步数据库操作）
            from asgiref.sync import sync_to_async
            token = await sync_to_async(self.token_service.get_token)(site_name, available_accounts.account)
            if token:
                logger.info(f"找到有效Token", extra={
                    "site_name": site_name,
                    "account": available_accounts.account
                })
                return token
            
            return None
            
        except Exception as e:
            logger.warning(f"检查现有Token时发生错误: {str(e)}")
            return None
    
    async def _get_credential_by_id(self, credential_id: int) -> Optional[AccountCredentialDTO]:
        """
        根据ID获取账号凭证
        
        Args:
            credential_id: 凭证ID
            
        Returns:
            账号凭证DTO，不存在时返回None
        """
        try:
            # 通过ServiceLocator获取organization服务
            from apps.core.interfaces import ServiceLocator
            organization_service = ServiceLocator.get_organization_service()
            
            credential = await organization_service.get_credential_internal(credential_id)
            return AccountCredentialDTO.from_model(credential)
            
        except Exception:
            return None
    
    async def _acquire_token_by_login(
        self, 
        acquisition_id: str, 
        site_name: str, 
        credential_id: Optional[int],
        selected_credential: Optional[AccountCredentialDTO] = None
    ) -> TokenAcquisitionResult:
        """
        通过自动登录获取token
        
        Args:
            acquisition_id: 获取流程ID
            site_name: 网站名称
            credential_id: 指定的凭证ID（可选）
            selected_credential: 已选择的凭证（可选，避免重复选择）
            
        Returns:
            Token获取结果
        """
        start_time = time.time()
        login_attempts = []
        
        try:
            # 1. 选择账号（如果还没有选择的话）
            if credential_id:
                credential = await self._get_credential_by_id(credential_id)
                if not credential:
                    raise ValidationException(f"无效的凭证ID: {credential_id}")
                
                logger.info(f"使用指定账号", extra={
                    "acquisition_id": acquisition_id,
                    "site_name": site_name,
                    "account": credential.account,
                    "credential_id": credential_id
                })
            elif selected_credential:
                # 使用已选择的凭证，避免重复选择
                credential = selected_credential
                logger.info(f"使用已选择账号", extra={
                    "acquisition_id": acquisition_id,
                    "site_name": site_name,
                    "account": credential.account,
                    "selection_reason": "pre_selected"
                })
            else:
                # 自动选择账号
                credential = await self.account_selection_strategy.select_account(site_name)
                if not credential:
                    raise NoAvailableAccountError(f"网站 {site_name} 没有可用账号")
                
                logger.info(f"自动选择账号", extra={
                    "acquisition_id": acquisition_id,
                    "site_name": site_name,
                    "account": credential.account,
                    "selection_reason": "best_available"
                })
            
            # 2. 执行自动登录
            logger.info(f"开始自动登录", extra={
                "acquisition_id": acquisition_id,
                "site_name": site_name,
                "account": credential.account
            })
            
            login_start_time = time.time()
            
            try:
                token = await asyncio.wait_for(
                    self.auto_login_service.login_and_get_token(credential),
                    timeout=self.concurrency_config.acquisition_timeout
                )
                
                login_duration = time.time() - login_start_time
                
                # 记录成功的登录尝试
                login_attempt = LoginAttemptResult(
                    success=True,
                    token=token,
                    account=credential.account,
                    error_message=None,
                    attempt_duration=login_duration,
                    retry_count=1
                )
                login_attempts.append(login_attempt)
                
                # 3. 保存token（使用sync_to_async包装同步数据库操作）
                logger.info(f"保存Token到服务", extra={
                    "acquisition_id": acquisition_id,
                    "site_name": site_name,
                    "account": credential.account
                })
                
                from asgiref.sync import sync_to_async
                await sync_to_async(self.token_service.save_token)(
                    site_name=site_name,
                    account=credential.account,
                    token=token
                )
                
                # 缓存新获取的Token
                cache_manager.cache_token(site_name, credential.account, token)
                
                # 4. 更新账号统计
                await self.account_selection_strategy.update_account_statistics(
                    account=credential.account,
                    site_name=site_name,
                    success=True
                )
                
                total_duration = time.time() - start_time
                
                logger.info(f"自动登录成功", extra={
                    "acquisition_id": acquisition_id,
                    "site_name": site_name,
                    "account": credential.account,
                    "login_duration": login_duration,
                    "total_duration": total_duration
                })
                
                return TokenAcquisitionResult(
                    success=True,
                    token=token,
                    acquisition_method="auto_login",
                    total_duration=total_duration,
                    login_attempts=login_attempts
                )
                
            except asyncio.TimeoutError:
                login_duration = time.time() - login_start_time
                
                # 超时后再检查一次Token是否已经保存（可能登录成功但保存Token时超时）
                logger.info(f"登录超时，检查Token是否已保存", extra={
                    "acquisition_id": acquisition_id,
                    "site_name": site_name,
                    "account": credential.account
                })
                
                # 等待一小段时间让Token保存完成
                await asyncio.sleep(2)
                
                # 检查Token是否已保存（使用sync_to_async包装同步数据库操作）
                from asgiref.sync import sync_to_async
                saved_token = await sync_to_async(self.token_service.get_token)(site_name, credential.account)
                if saved_token:
                    logger.info(f"✅ 超时但Token已保存成功", extra={
                        "acquisition_id": acquisition_id,
                        "site_name": site_name,
                        "account": credential.account
                    })
                    
                    # 记录成功的登录尝试
                    login_attempt = LoginAttemptResult(
                        success=True,
                        token=saved_token,
                        account=credential.account,
                        error_message="超时但Token已保存",
                        attempt_duration=login_duration,
                        retry_count=1
                    )
                    login_attempts.append(login_attempt)
                    
                    # 更新账号统计为成功
                    await self.account_selection_strategy.update_account_statistics(
                        account=credential.account,
                        site_name=site_name,
                        success=True
                    )
                    
                    total_duration = time.time() - start_time
                    
                    return TokenAcquisitionResult(
                        success=True,
                        token=saved_token,
                        acquisition_method="auto_login_timeout_recovered",
                        total_duration=total_duration,
                        login_attempts=login_attempts
                    )
                
                # Token确实没有保存，记录失败
                error_msg = f"登录超时（{self.concurrency_config.acquisition_timeout}秒）"
                
                # 记录超时的登录尝试
                login_attempt = LoginAttemptResult(
                    success=False,
                    token=None,
                    account=credential.account,
                    error_message=error_msg,
                    attempt_duration=login_duration,
                    retry_count=1
                )
                login_attempts.append(login_attempt)
                
                # 更新账号统计
                await self.account_selection_strategy.update_account_statistics(
                    account=credential.account,
                    site_name=site_name,
                    success=False
                )
                
                logger.error(f"自动登录超时", extra={
                    "acquisition_id": acquisition_id,
                    "site_name": site_name,
                    "account": credential.account,
                    "timeout": self.concurrency_config.acquisition_timeout,
                    "login_duration": login_duration
                })
                
                raise TokenAcquisitionTimeoutError(
                    message=error_msg,
                    errors={
                        "timeout": self.concurrency_config.acquisition_timeout,
                        "login_duration": login_duration
                    }
                )
                
            except LoginFailedError as e:
                login_duration = time.time() - login_start_time
                
                # 获取登录尝试记录
                if hasattr(e, 'attempts') and e.attempts:
                    login_attempts.extend(e.attempts)
                else:
                    # 创建失败记录
                    login_attempt = LoginAttemptResult(
                        success=False,
                        token=None,
                        account=credential.account,
                        error_message=str(e),
                        attempt_duration=login_duration,
                        retry_count=1
                    )
                    login_attempts.append(login_attempt)
                
                # 更新账号统计
                await self.account_selection_strategy.update_account_statistics(
                    account=credential.account,
                    site_name=site_name,
                    success=False
                )
                
                logger.error(f"自动登录失败", extra={
                    "acquisition_id": acquisition_id,
                    "site_name": site_name,
                    "account": credential.account,
                    "error": str(e),
                    "login_duration": login_duration,
                    "attempts": len(login_attempts)
                })
                
                # 返回失败结果而不是抛出异常
                total_duration = time.time() - start_time
                return TokenAcquisitionResult(
                    success=False,
                    token=None,
                    acquisition_method="auto_login",
                    total_duration=total_duration,
                    login_attempts=login_attempts,
                    error_details={
                        "message": str(e),
                        "error_type": type(e).__name__
                    }
                )
            
            except TokenAcquisitionTimeoutError as e:
                # AutoLoginService超时，检查Token是否已保存
                login_duration = time.time() - login_start_time
                
                logger.info(f"AutoLoginService超时，检查Token是否已保存", extra={
                    "acquisition_id": acquisition_id,
                    "site_name": site_name,
                    "account": credential.account
                })
                
                # 等待一小段时间让Token保存完成
                await asyncio.sleep(2)
                
                # 检查Token是否已保存（使用sync_to_async包装同步数据库操作）
                from asgiref.sync import sync_to_async
                saved_token = await sync_to_async(self.token_service.get_token)(site_name, credential.account)
                if saved_token:
                    logger.info(f"✅ AutoLoginService超时但Token已保存成功", extra={
                        "acquisition_id": acquisition_id,
                        "site_name": site_name,
                        "account": credential.account
                    })
                    
                    # 记录成功的登录尝试
                    login_attempt = LoginAttemptResult(
                        success=True,
                        token=saved_token,
                        account=credential.account,
                        error_message="超时但Token已保存",
                        attempt_duration=login_duration,
                        retry_count=1
                    )
                    login_attempts.append(login_attempt)
                    
                    # 更新账号统计为成功
                    await self.account_selection_strategy.update_account_statistics(
                        account=credential.account,
                        site_name=site_name,
                        success=True
                    )
                    
                    total_duration = time.time() - start_time
                    
                    return TokenAcquisitionResult(
                        success=True,
                        token=saved_token,
                        acquisition_method="auto_login_timeout_recovered",
                        total_duration=total_duration,
                        login_attempts=login_attempts
                    )
                
                # Token确实没有保存，记录失败并重新抛出异常
                logger.error(f"AutoLoginService超时且Token未保存", extra={
                    "acquisition_id": acquisition_id,
                    "site_name": site_name,
                    "account": credential.account,
                    "login_duration": login_duration
                })
                
                # 更新账号统计
                await self.account_selection_strategy.update_account_statistics(
                    account=credential.account,
                    site_name=site_name,
                    success=False
                )
                
                # 返回失败结果而不是抛出异常
                total_duration = time.time() - start_time
                return TokenAcquisitionResult(
                    success=False,
                    token=None,
                    acquisition_method="auto_login_timeout",
                    total_duration=total_duration,
                    login_attempts=login_attempts,
                    error_details={
                        "message": str(e),
                        "error_type": type(e).__name__
                    }
                )
                
        except Exception as e:
            total_duration = time.time() - start_time
            
            if isinstance(e, (LoginFailedError, NoAvailableAccountError, 
                            TokenAcquisitionTimeoutError, ValidationException)):
                # 返回失败结果
                return TokenAcquisitionResult(
                    success=False,
                    token=None,
                    acquisition_method="auto_login",
                    total_duration=total_duration,
                    login_attempts=login_attempts,
                    error_details={
                        "message": str(e),
                        "error_type": type(e).__name__
                    }
                )
            else:
                # 未预期错误
                logger.error(f"自动登录过程中发生未预期错误", extra={
                    "acquisition_id": acquisition_id,
                    "site_name": site_name,
                    "error": str(e),
                    "total_duration": total_duration
                }, exc_info=True)
                
                return TokenAcquisitionResult(
                    success=False,
                    token=None,
                    acquisition_method="auto_login",
                    total_duration=total_duration,
                    login_attempts=login_attempts,
                    error_details={
                        "message": f"未预期错误: {str(e)}",
                        "error_type": "UnexpectedError"
                    }
                )
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取服务统计信息
        
        Returns:
            统计信息字典
        """
        return {
            "acquisition_count": self._acquisition_count,
            "success_count": self._success_count,
            "failure_count": self._failure_count,
            "success_rate": self._success_count / self._acquisition_count if self._acquisition_count > 0 else 0,
            "active_acquisitions": len(self._active_acquisitions),
            "active_locks": len(self._acquisition_locks)
        }
    
    def reset_statistics(self) -> None:
        """重置统计信息"""
        self._acquisition_count = 0
        self._success_count = 0
        self._failure_count = 0
    
    @classmethod
    def clear_locks(cls) -> None:
        """清除所有锁（用于测试）"""
        cls._active_acquisitions.clear()
        cls._acquisition_locks.clear()