"""Module for auto login usecase."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from apps.automation.exceptions import AutoTokenAcquisitionError, LoginFailedError, TokenAcquisitionTimeoutError
from apps.automation.services.token.browser_context_factory import BrowserContextFactory
from apps.automation.services.token.court_login_gateway import CourtLoginGateway
from apps.core.exceptions import NetworkError
from apps.core.interfaces import AccountCredentialDTO, LoginAttemptResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetryConfig:
    max_network_retries: int = 3
    max_captcha_retries: int = 3
    network_retry_delay_base: float = 1.0
    captcha_retry_delay: float = 2.0
    login_timeout: float = 60.0


@dataclass
class AutoLoginUsecase:
    retry_config: RetryConfig
    browser_context_factory: BrowserContextFactory
    login_gateway: CourtLoginGateway
    sync_login_attempt: Callable[[AccountCredentialDTO], str] | None = None
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    time_provider: Callable[[], float] = time.time
    _login_attempts: list[LoginAttemptResult] | None = None

    def __post_init__(self) -> None:
        if self._login_attempts is None:
            self._login_attempts = []

    async def execute(self, credential: AccountCredentialDTO) -> str:
        start_time = self.time_provider()
        self._login_attempts.clear()  # type: ignore[union-attr]

        from apps.automation.utils.logging import AutomationLogger

        AutomationLogger.log_auto_login_start(
            acquisition_id="auto_login",
            site_name=credential.site_name,
            account=credential.account,
            max_network_retries=self.retry_config.max_network_retries,
            max_captcha_retries=self.retry_config.max_captcha_retries,
            login_timeout=self.retry_config.login_timeout,
        )

        try:
            token = await asyncio.wait_for(
                self._login_with_retries(credential),
                timeout=self.retry_config.login_timeout,
            )

            total_duration = self.time_provider() - start_time
            AutomationLogger.log_auto_login_success(
                acquisition_id="auto_login",
                site_name=credential.site_name,
                account=credential.account,
                login_duration=total_duration,
                total_attempts=len(self._login_attempts),  # type: ignore
            )
            return token

        except TimeoutError:
            total_duration = self.time_provider() - start_time
            logger.error(
                "登录超时",
                extra={
                    "account": credential.account,
                    "site_name": credential.site_name,
                    "timeout": self.retry_config.login_timeout,
                    "total_duration": total_duration,
                    "attempts": len(self._login_attempts),  # type: ignore
                },
            )
            raise TokenAcquisitionTimeoutError(
                message=f"登录超时({self.retry_config.login_timeout}秒)",
                errors={
                    "timeout": self.retry_config.login_timeout,
                    "total_duration": total_duration,
                    "attempts": len(self._login_attempts),  # type: ignore
                },
            ) from None
        except Exception as e:
            total_duration = self.time_provider() - start_time
            logger.error(
                "自动登录失败",
                extra={
                    "account": credential.account,
                    "site_name": credential.site_name,
                    "error": str(e),
                    "total_duration": total_duration,
                    "attempts": len(self._login_attempts),  # type: ignore
                },
            )
            if isinstance(e, (LoginFailedError, NetworkError, AutoTokenAcquisitionError)):
                raise
            raise LoginFailedError(
                message=f"登录过程中发生未预期错误: {e!s}",
                attempts=self._login_attempts.copy(),  # type: ignore[union-attr]
            ) from e

    def get_login_attempts(self) -> list[LoginAttemptResult]:
        return self._login_attempts.copy()  # type: ignore[union-attr]

    def clear_login_attempts(self) -> None:
        self._login_attempts.clear()  # type: ignore[union-attr]

    async def _login_with_retries(self, credential: AccountCredentialDTO) -> str:
        last_exception: Exception | None = None

        for network_attempt in range(1, self.retry_config.max_network_retries + 1):
            try:
                logger.info(f"网络重试 {network_attempt}/{self.retry_config.max_network_retries}")
                token = await self._login_with_captcha_retries(credential, network_attempt)
                return token
            except NetworkError as e:
                last_exception = e
                logger.warning(f"网络错误(尝试 {network_attempt}): {e!s}")
                if network_attempt < self.retry_config.max_network_retries:
                    delay = self.retry_config.network_retry_delay_base * (2 ** (network_attempt - 1))
                    logger.info(f"等待 {delay} 秒后重试...")
                    await self.sleep(delay)
                else:
                    logger.error("网络重试已达最大次数,放弃登录")
                    break
            except LoginFailedError:
                raise
            except Exception as e:
                last_exception = e
                logger.error(f"登录过程中发生未预期错误: {e!s}")
                break

        if isinstance(last_exception, NetworkError):
            raise last_exception
        raise LoginFailedError(
            message=f"网络重试失败,最后错误: {last_exception!s}",
            attempts=self._login_attempts.copy(),  # type: ignore[union-attr]
        )

    async def _login_with_captcha_retries(self, credential: AccountCredentialDTO, network_attempt: int) -> str:
        for captcha_attempt in range(1, self.retry_config.max_captcha_retries + 1):
            attempt_start_time = self.time_provider()
            try:
                logger.info(f"验证码重试 {captcha_attempt}/{self.retry_config.max_captcha_retries}")
                token = await self._single_login_attempt(credential)
                attempt_result = LoginAttemptResult(
                    success=True,
                    token=token,
                    account=credential.account,
                    error_message=None,
                    attempt_duration=self.time_provider() - attempt_start_time,
                    retry_count=captcha_attempt,
                )
                self._login_attempts.append(attempt_result)  # type: ignore[union-attr]
                logger.info(
                    "登录成功",
                    extra={
                        "account": credential.account,
                        "network_attempt": network_attempt,
                        "captcha_attempt": captcha_attempt,
                        "attempt_duration": attempt_result.attempt_duration,
                    },
                )
                return token
            except NetworkError as e:
                attempt_result = LoginAttemptResult(
                    success=False,
                    token=None,
                    account=credential.account,
                    error_message=f"网络错误: {e!s}",
                    attempt_duration=self.time_provider() - attempt_start_time,
                    retry_count=captcha_attempt,
                )
                self._login_attempts.append(attempt_result)  # type: ignore[union-attr]
                raise
            except Exception as e:
                attempt_result = LoginAttemptResult(
                    success=False,
                    token=None,
                    account=credential.account,
                    error_message=str(e),
                    attempt_duration=self.time_provider() - attempt_start_time,
                    retry_count=captcha_attempt,
                )
                self._login_attempts.append(attempt_result)  # type: ignore[union-attr]
                logger.warning(f"登录失败(验证码尝试 {captcha_attempt}): {e!s}")
                if captcha_attempt < self.retry_config.max_captcha_retries:
                    logger.info(f"等待 {self.retry_config.captcha_retry_delay} 秒后重试...")
                    await self.sleep(self.retry_config.captcha_retry_delay)
                else:
                    logger.error("验证码重试已达最大次数")
                    break

        raise LoginFailedError(
            message=f"验证码重试失败,已尝试 {self.retry_config.max_captcha_retries} 次",
            attempts=self._login_attempts.copy(),  # type: ignore[union-attr]
        )

    async def _single_login_attempt(self, credential: AccountCredentialDTO) -> str:
        try:
            loop = asyncio.get_event_loop()
            fn = self.sync_login_attempt or self._sync_login_attempt
            return await loop.run_in_executor(None, fn, credential)
        except Exception as e:
            error_msg = str(e).lower()
            if any(
                keyword in error_msg
                for keyword in ["network", "connection", "timeout", "dns", "socket", "连接", "网络", "超时", "无法访问"]
            ):
                raise NetworkError(f"网络连接错误: {e!s}") from e
            raise

    def _sync_login_attempt(self, credential: AccountCredentialDTO) -> str:
        browser_context: Any | None = None
        try:
            browser_context = self.browser_context_factory.new_context()
            return self.login_gateway.login(credential=credential, browser_context=browser_context)
        finally:
            if browser_context is not None:
                with contextlib.suppress(Exception):
                    browser_context.close()
