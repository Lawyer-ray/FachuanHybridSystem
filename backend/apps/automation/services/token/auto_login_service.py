"""
自动登录服务

封装CourtZxfwService的登录逻辑，实现网络错误重试机制、
验证码识别重试机制、登录超时处理和详细错误记录。
"""
import asyncio
import logging
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime

from apps.core.interfaces import IAutoLoginService, AccountCredentialDTO, LoginAttemptResult, IBrowserService
from apps.core.exceptions import (
    LoginFailedError, 
    NetworkError, 
    TokenAcquisitionTimeoutError,
    AutoTokenAcquisitionError
)

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """重试配置"""
    max_network_retries: int = 3
    max_captcha_retries: int = 3
    network_retry_delay_base: float = 1.0  # 指数退避基础延迟（秒）
    captcha_retry_delay: float = 2.0  # 验证码重试延迟（秒）
    login_timeout: float = 60.0  # 登录超时时间（秒）


class AutoLoginService:
    """
    自动登录服务实现
    
    功能：
    1. 封装CourtZxfwService的登录逻辑
    2. 实现网络错误重试机制（最多3次，指数退避）
    3. 实现验证码识别重试机制（最多3次，刷新验证码）
    4. 添加登录超时处理和详细错误记录
    """
    
    def __init__(
        self,
        retry_config: Optional[RetryConfig] = None,
        browser_service: Optional[IBrowserService] = None
    ):
        """
        初始化自动登录服务
        
        Args:
            retry_config: 重试配置，None则使用默认配置
            browser_service: 浏览器服务，None则使用ServiceLocator获取
        """
        self.retry_config = retry_config or RetryConfig()
        self._browser_service = browser_service
        self._login_attempts: List[LoginAttemptResult] = []
    
    @property
    def browser_service(self) -> IBrowserService:
        """获取浏览器服务（延迟加载）"""
        if self._browser_service is None:
            from apps.core.interfaces import ServiceLocator
            self._browser_service = ServiceLocator.get_browser_service()
        return self._browser_service
    
    async def login_and_get_token(
        self, 
        credential: AccountCredentialDTO
    ) -> str:
        """
        执行自动登录并返回token
        
        Args:
            credential: 账号凭证DTO
            
        Returns:
            登录成功后的token字符串
            
        Raises:
            LoginFailedError: 登录失败
            NetworkError: 网络错误
            TokenAcquisitionTimeoutError: 登录超时
        """
        start_time = time.time()
        self._login_attempts.clear()
        
        from apps.automation.utils.logging import AutomationLogger
        AutomationLogger.log_auto_login_start(
            acquisition_id="auto_login",
            site_name=credential.site_name,
            account=credential.account,
            max_network_retries=self.retry_config.max_network_retries,
            max_captcha_retries=self.retry_config.max_captcha_retries,
            login_timeout=self.retry_config.login_timeout
        )
        
        try:
            # 设置超时
            token = await asyncio.wait_for(
                self._login_with_retries(credential),
                timeout=self.retry_config.login_timeout
            )
            
            total_duration = time.time() - start_time
            AutomationLogger.log_auto_login_success(
                acquisition_id="auto_login",
                site_name=credential.site_name,
                account=credential.account,
                login_duration=total_duration,
                total_attempts=len(self._login_attempts)
            )
            
            return token
            
        except asyncio.TimeoutError:
            total_duration = time.time() - start_time
            error_msg = f"登录超时（{self.retry_config.login_timeout}秒）"
            
            logger.error(f"登录超时", extra={
                "account": credential.account,
                "site_name": credential.site_name,
                "timeout": self.retry_config.login_timeout,
                "total_duration": total_duration,
                "attempts": len(self._login_attempts)
            })
            
            raise TokenAcquisitionTimeoutError(
                message=error_msg,
                errors={
                    "timeout": self.retry_config.login_timeout,
                    "total_duration": total_duration,
                    "attempts": len(self._login_attempts)
                }
            )
        
        except Exception as e:
            total_duration = time.time() - start_time
            logger.error(f"自动登录失败", extra={
                "account": credential.account,
                "site_name": credential.site_name,
                "error": str(e),
                "total_duration": total_duration,
                "attempts": len(self._login_attempts)
            })
            
            if isinstance(e, (LoginFailedError, NetworkError, AutoTokenAcquisitionError)):
                raise
            else:
                raise LoginFailedError(
                    message=f"登录过程中发生未预期错误: {str(e)}",
                    attempts=self._login_attempts.copy()
                )
    
    async def _login_with_retries(self, credential: AccountCredentialDTO) -> str:
        """
        带重试机制的登录
        
        Args:
            credential: 账号凭证DTO
            
        Returns:
            登录成功后的token
            
        Raises:
            LoginFailedError: 所有重试都失败
            NetworkError: 网络错误
        """
        last_exception = None
        
        # 网络重试循环
        for network_attempt in range(1, self.retry_config.max_network_retries + 1):
            try:
                logger.info(f"网络重试 {network_attempt}/{self.retry_config.max_network_retries}")
                
                # 验证码重试循环
                token = await self._login_with_captcha_retries(
                    credential, network_attempt
                )
                
                return token
                
            except NetworkError as e:
                last_exception = e
                logger.warning(f"网络错误（尝试 {network_attempt}）: {str(e)}")
                
                if network_attempt < self.retry_config.max_network_retries:
                    # 指数退避
                    delay = self.retry_config.network_retry_delay_base * (2 ** (network_attempt - 1))
                    logger.info(f"等待 {delay} 秒后重试...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"网络重试已达最大次数，放弃登录")
                    break
                    
            except LoginFailedError as e:
                # 登录失败（非网络问题）不进行网络重试
                raise e
            
            except Exception as e:
                last_exception = e
                logger.error(f"登录过程中发生未预期错误: {str(e)}")
                break
        
        # 所有网络重试都失败
        if isinstance(last_exception, NetworkError):
            raise last_exception
        else:
            raise LoginFailedError(
                message=f"网络重试失败，最后错误: {str(last_exception)}",
                attempts=self._login_attempts.copy()
            )
    
    async def _login_with_captcha_retries(
        self, 
        credential: AccountCredentialDTO, 
        network_attempt: int
    ) -> str:
        """
        带验证码重试的登录
        
        Args:
            credential: 账号凭证DTO
            network_attempt: 当前网络重试次数
            
        Returns:
            登录成功后的token
            
        Raises:
            LoginFailedError: 验证码重试失败
            NetworkError: 网络错误
        """
        # 验证码重试循环
        for captcha_attempt in range(1, self.retry_config.max_captcha_retries + 1):
            attempt_start_time = time.time()
            
            try:
                logger.info(f"验证码重试 {captcha_attempt}/{self.retry_config.max_captcha_retries}")
                
                # 执行单次登录尝试
                token = await self._single_login_attempt(credential)
                
                # 记录成功的尝试
                attempt_result = LoginAttemptResult(
                    success=True,
                    token=token,
                    account=credential.account,
                    error_message=None,
                    attempt_duration=time.time() - attempt_start_time,
                    retry_count=captcha_attempt
                )
                self._login_attempts.append(attempt_result)
                
                logger.info(f"登录成功", extra={
                    "account": credential.account,
                    "network_attempt": network_attempt,
                    "captcha_attempt": captcha_attempt,
                    "attempt_duration": attempt_result.attempt_duration
                })
                
                return token
                
            except NetworkError as e:
                # 网络错误直接抛出，由上层处理网络重试
                attempt_result = LoginAttemptResult(
                    success=False,
                    token=None,
                    account=credential.account,
                    error_message=f"网络错误: {str(e)}",
                    attempt_duration=time.time() - attempt_start_time,
                    retry_count=captcha_attempt
                )
                self._login_attempts.append(attempt_result)
                raise e
                
            except Exception as e:
                # 其他错误（如验证码错误）进行验证码重试
                attempt_result = LoginAttemptResult(
                    success=False,
                    token=None,
                    account=credential.account,
                    error_message=str(e),
                    attempt_duration=time.time() - attempt_start_time,
                    retry_count=captcha_attempt
                )
                self._login_attempts.append(attempt_result)
                
                logger.warning(f"登录失败（验证码尝试 {captcha_attempt}）: {str(e)}")
                
                if captcha_attempt < self.retry_config.max_captcha_retries:
                    logger.info(f"等待 {self.retry_config.captcha_retry_delay} 秒后重试...")
                    await asyncio.sleep(self.retry_config.captcha_retry_delay)
                else:
                    logger.error(f"验证码重试已达最大次数")
                    break
        
        # 所有验证码重试都失败
        raise LoginFailedError(
            message=f"验证码重试失败，已尝试 {self.retry_config.max_captcha_retries} 次",
            attempts=self._login_attempts.copy()
        )
    
    async def _single_login_attempt(self, credential: AccountCredentialDTO) -> str:
        """
        执行单次登录尝试
        
        Args:
            credential: 账号凭证DTO
            
        Returns:
            登录成功后的token
            
        Raises:
            NetworkError: 网络连接错误
            Exception: 其他登录错误（如验证码错误、账号密码错误等）
        """
        try:
            # 在线程池中执行同步的登录操作
            loop = asyncio.get_event_loop()
            token = await loop.run_in_executor(
                None, 
                self._sync_login_attempt, 
                credential
            )
            return token
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # 判断是否为网络错误
            if any(keyword in error_msg for keyword in [
                "network", "connection", "timeout", "dns", "socket", 
                "连接", "网络", "超时", "无法访问"
            ]):
                raise NetworkError(f"网络连接错误: {str(e)}")
            else:
                # 其他错误（验证码、账号密码等）
                raise e
    
    def _sync_login_attempt(self, credential: AccountCredentialDTO) -> str:
        """
        异步的登录尝试
        
        Args:
            credential: 账号凭证DTO
            
        Returns:
            登录成功后的token
            
        Raises:
            Exception: 登录错误
        """
        try:
            # 获取浏览器上下文
            browser_context = self._get_browser_context()
            
            # 创建CourtZxfwService实例
            court_service = self._create_court_service(browser_context, credential.site_name)
            
            # 执行登录
            login_result = court_service.login(
                account=credential.account,
                password=credential.password,
                max_captcha_retries=1,  # 单次尝试不重试验证码，由外层控制
                save_debug=False
            )
            
            if not login_result.get("success"):
                raise Exception(f"登录失败: {login_result.get('message', '未知错误')}")
            
            # 提取token
            token = login_result.get("token")
            if not token:
                raise Exception("登录成功但未获取到token")
            
            return token
            
        except Exception as e:
            raise e
        finally:
            # 清理浏览器上下文
            if 'browser_context' in locals():
                try:
                    browser_context.close()
                except:
                    pass
    
    def _get_browser_context(self):
        """获取浏览器上下文"""
        try:
            # 由于 BrowserServiceAdapter.get_browser() 实际上是同步的，我们可以直接调用底层服务
            # 这是一个临时解决方案，直到接口设计更加一致
            if hasattr(self.browser_service, 'service'):
                # 如果是 BrowserServiceAdapter，直接使用底层服务
                browser = self.browser_service.service.get_browser()
            else:
                # 如果是其他实现，尝试同步调用
                browser = self.browser_service.get_browser()
            
            # 反检测配置
            from apps.automation.services.scraper.core.anti_detection import anti_detection
            default_config = anti_detection.get_browser_context_options()
            
            return browser.new_context(**default_config)
        except Exception as e:
            raise NetworkError(f"无法获取浏览器上下文: {str(e)}")
    
    def _create_court_service(self, browser_context, site_name: str):
        """创建法院服务实例"""
        try:
            from apps.automation.services.scraper.sites.court_zxfw import CourtZxfwService
            
            # 获取页面实例
            page = browser_context.new_page()
            
            # 创建服务实例
            return CourtZxfwService(
                page=page,
                context=browser_context,
                site_name=site_name
            )
        except Exception as e:
            raise Exception(f"创建法院服务失败: {str(e)}")
    
    def get_login_attempts(self) -> List[LoginAttemptResult]:
        """获取登录尝试记录"""
        return self._login_attempts.copy()
    
    def clear_login_attempts(self) -> None:
        """清空登录尝试记录"""
        self._login_attempts.clear()