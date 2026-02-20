"""
Token 登录处理器

封装自动登录流程中的登录执行、超时处理、失败处理等逻辑。
"""

from django.utils.translation import gettext_lazy as _
import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from apps.core.exceptions import (
    LoginFailedError,
    NoAvailableAccountError,
    TokenAcquisitionTimeoutError,
    ValidationException,
)
from apps.core.interfaces import (
    AccountCredentialDTO,
    IAccountSelectionStrategy,
    IAutoLoginService,
    ITokenService,
    LoginAttemptResult,
    TokenAcquisitionResult,
)

from .cache_manager import cache_manager

if TYPE_CHECKING:
    from .concurrency_optimizer import ConcurrencyConfig

logger = logging.getLogger(__name__)


class LoginHandler:
    """
    登录处理器

    封装自动登录流程中的凭证选择、登录执行、超时/失败处理逻辑。
    """

    def __init__(
        self,
        account_selection_strategy: IAccountSelectionStrategy,
        auto_login_service: IAutoLoginService,
        token_service: ITokenService,
        concurrency_config: "ConcurrencyConfig",
    ) -> None:
        self._account_selection_strategy = account_selection_strategy
        self._auto_login_service = auto_login_service
        self._token_service = token_service
        self._concurrency_config = concurrency_config

    async def select_credential(
        self,
        acquisition_id: str,
        site_name: str,
        credential_id: int | None,
        selected_credential: AccountCredentialDTO | None,
    ) -> AccountCredentialDTO:
        """选择登录凭证"""
        if credential_id:
            credential = await self._get_credential_by_id(credential_id)
            if not credential:
                raise ValidationException(f"无效的凭证ID: {credential_id}")
            logger.info(
                "使用指定账号",
                extra={
                    "acquisition_id": acquisition_id,
                    "site_name": site_name,
                    "account": credential.account,
                    "credential_id": credential_id,
                },
            )
            return credential
        if selected_credential:
            logger.info(
                "使用已选择账号",
                extra={
                    "acquisition_id": acquisition_id,
                    "site_name": site_name,
                    "account": selected_credential.account,
                    "selection_reason": "pre_selected",
                },
            )
            return selected_credential
        credential = await self._account_selection_strategy.select_account(site_name)
        if not credential:
            raise NoAvailableAccountError(f"网站 {site_name} 没有可用账号")
        logger.info(
            "自动选择账号",
            extra={
                "acquisition_id": acquisition_id,
                "site_name": site_name,
                "account": credential.account,
                "selection_reason": "best_available",
            },
        )
        return credential

    async def try_recover_token_after_timeout(
        self,
        site_name: str,
        account: str,
        login_duration: float,
        login_attempts: list[LoginAttemptResult],
        start_time: float,
    ) -> TokenAcquisitionResult | None:
        """超时后等待并检查 token 是否已保存，成功则返回结果，否则返回 None"""
        await asyncio.sleep(2)
        saved_token = await self._token_service.get_token_internal(site_name, account) # type: ignore
        if not saved_token:
            return None
        logger.info("超时但Token已保存成功", extra={"site_name": site_name, "account": account})
        login_attempts.append(
            LoginAttemptResult(
                success=True,
                token=saved_token,
                account=account,
                error_message=_("超时但Token已保存"), # type: ignore
                attempt_duration=login_duration,
                retry_count=1,
            )
        )
        await self._account_selection_strategy.update_account_statistics( # type: ignore
            account=account, site_name=site_name, success=True
        )
        return TokenAcquisitionResult(
            success=True,
            token=saved_token,
            acquisition_method="auto_login_timeout_recovered",
            total_duration=time.time() - start_time,
            login_attempts=login_attempts,
        )

    async def handle_login_timeout(
        self,
        acquisition_id: str,
        site_name: str,
        credential: AccountCredentialDTO,
        login_duration: float,
        login_attempts: list[Any],
        start_time: float,
        exc: Exception,
    ) -> TokenAcquisitionResult:
        """处理登录超时，尝试恢复 token"""
        logger.info(
            "登录超时，检查Token是否已保存",
            extra={
                "acquisition_id": acquisition_id,
                "site_name": site_name,
                "account": credential.account,
            },
        )
        recovered = await self.try_recover_token_after_timeout(
            site_name, credential.account, login_duration, login_attempts, start_time
        )
        if recovered is not None:
            return recovered
        error_msg = f"登录超时（{self._concurrency_config.acquisition_timeout}秒）"
        login_attempts.append(
            LoginAttemptResult(
                success=False,
                token=None,
                account=credential.account,
                error_message=error_msg,
                attempt_duration=login_duration,
                retry_count=1,
            )
        )
        await self._account_selection_strategy.update_account_statistics( # type: ignore
            account=credential.account, site_name=site_name, success=False
        )
        logger.error(
            "自动登录超时",
            extra={
                "acquisition_id": acquisition_id,
                "site_name": site_name,
                "account": credential.account,
                "timeout": self._concurrency_config.acquisition_timeout,
            },
        )
        raise TokenAcquisitionTimeoutError(
            message=error_msg,
            errors={
                "timeout": self._concurrency_config.acquisition_timeout,
                "login_duration": login_duration,
            },
        ) from exc

    async def handle_login_failed(
        self,
        acquisition_id: str,
        site_name: str,
        credential: AccountCredentialDTO,
        login_duration: float,
        login_attempts: list[Any],
        start_time: float,
        exc: Exception,
    ) -> TokenAcquisitionResult:
        """处理登录失败"""
        if hasattr(exc, "attempts") and exc.attempts:
            login_attempts.extend(exc.attempts)
        else:
            login_attempts.append(
                LoginAttemptResult(
                    success=False,
                    token=None,
                    account=credential.account,
                    error_message=str(exc),
                    attempt_duration=login_duration,
                    retry_count=1,
                )
            )
        await self._account_selection_strategy.update_account_statistics( # type: ignore
            account=credential.account, site_name=site_name, success=False
        )
        logger.error(
            "自动登录失败",
            extra={
                "acquisition_id": acquisition_id,
                "site_name": site_name,
                "account": credential.account,
                "error": str(exc),
                "login_duration": login_duration,
                "attempts": len(login_attempts),
            },
        )
        return TokenAcquisitionResult(
            success=False,
            token=None,
            acquisition_method="auto_login",
            total_duration=time.time() - start_time,
            login_attempts=login_attempts,
            error_details={"message": str(exc), "error_type": type(exc).__name__},
        )

    async def acquire_token_by_login(
        self,
        acquisition_id: str,
        site_name: str,
        credential_id: int | None,
        selected_credential: AccountCredentialDTO | None = None,
    ) -> TokenAcquisitionResult:
        """通过自动登录获取 token"""
        start_time = time.time()
        login_attempts: list[Any] = []

        try:
            credential = await self.select_credential(acquisition_id, site_name, credential_id, selected_credential)

            logger.info(
                "开始自动登录",
                extra={
                    "acquisition_id": acquisition_id,
                    "site_name": site_name,
                    "account": credential.account,
                },
            )
            login_start_time = time.time()

            try:
                token = await asyncio.wait_for(
                    self._auto_login_service.login_and_get_token(credential),
                    timeout=self._concurrency_config.acquisition_timeout,
                )
                login_duration = time.time() - login_start_time
                login_attempts.append(
                    LoginAttemptResult(
                        success=True,
                        token=token,
                        account=credential.account,
                        error_message=None,
                        attempt_duration=login_duration,
                        retry_count=1,
                    )
                )

                logger.info(
                    "保存Token到服务",
                    extra={
                        "acquisition_id": acquisition_id,
                        "site_name": site_name,
                        "account": credential.account,
                    },
                )
                await self._token_service.save_token_internal( # type: ignore
                    site_name=site_name,
                    account=credential.account,
                    token=token,
                    expires_in=3600,
                )
                cache_manager.cache_token(site_name, credential.account, token)
                await self._account_selection_strategy.update_account_statistics( # type: ignore
                    account=credential.account, site_name=site_name, success=True
                )

                logger.info(
                    "自动登录成功",
                    extra={
                        "acquisition_id": acquisition_id,
                        "site_name": site_name,
                        "account": credential.account,
                        "login_duration": login_duration,
                        "total_duration": time.time() - start_time,
                    },
                )
                return TokenAcquisitionResult(
                    success=True,
                    token=token,
                    acquisition_method="auto_login",
                    total_duration=time.time() - start_time,
                    login_attempts=login_attempts,
                )

            except TimeoutError as e:
                return await self.handle_login_timeout(
                    acquisition_id,
                    site_name,
                    credential,
                    time.time() - login_start_time,
                    login_attempts,
                    start_time,
                    e,
                )

            except LoginFailedError as e:
                return await self.handle_login_failed(
                    acquisition_id,
                    site_name,
                    credential,
                    time.time() - login_start_time,
                    login_attempts,
                    start_time,
                    e,
                )

            except TokenAcquisitionTimeoutError as e:
                login_duration = time.time() - login_start_time
                logger.info(
                    "AutoLoginService超时，检查Token是否已保存",
                    extra={
                        "acquisition_id": acquisition_id,
                        "site_name": site_name,
                        "account": credential.account,
                    },
                )
                recovered = await self.try_recover_token_after_timeout(
                    site_name, credential.account, login_duration, login_attempts, start_time
                )
                if recovered is not None:
                    return recovered
                logger.error(
                    "AutoLoginService超时且Token未保存",
                    extra={
                        "acquisition_id": acquisition_id,
                        "site_name": site_name,
                        "account": credential.account,
                    },
                )
                await self._account_selection_strategy.update_account_statistics( # type: ignore
                    account=credential.account, site_name=site_name, success=False
                )
                return TokenAcquisitionResult(
                    success=False,
                    token=None,
                    acquisition_method="auto_login_timeout",
                    total_duration=time.time() - start_time,
                    login_attempts=login_attempts,
                    error_details={"message": str(e), "error_type": type(e).__name__},
                )

        except Exception as e:
            total_duration = time.time() - start_time
            if not isinstance(
                e,
                (
                    LoginFailedError,
                    NoAvailableAccountError,
                    TokenAcquisitionTimeoutError,
                    ValidationException,
                ),
            ):
                logger.error(
                    "自动登录过程中发生未预期错误",
                    extra={
                        "acquisition_id": acquisition_id,
                        "site_name": site_name,
                        "error": str(e),
                        "total_duration": total_duration,
                    },
                    exc_info=True,
                )
            return TokenAcquisitionResult(
                success=False,
                token=None,
                acquisition_method="auto_login",
                total_duration=total_duration,
                login_attempts=login_attempts,
                error_details={"message": str(e), "error_type": type(e).__name__},
            )

    async def _get_credential_by_id(self, credential_id: int) -> AccountCredentialDTO | None:
        """根据 ID 获取账号凭证"""
        try:
            from apps.core.dependencies import build_organization_service

            organization_service = build_organization_service()
            credential = await organization_service.get_credential_internal(credential_id) # type: ignore
            return AccountCredentialDTO.from_model(credential)
        except Exception:
            return None
