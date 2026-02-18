"""Business logic services."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict

from apps.automation.exceptions import LoginFailedError, NoAvailableAccountError, TokenAcquisitionTimeoutError
from apps.automation.utils.logging_mixins.common import mask_account, stable_hash
from apps.core.dtos import AccountCredentialDTO, LoginAttemptResult, TokenAcquisitionResult
from apps.core.exceptions import ValidationException

from .cache_manager import cache_manager

logger = logging.getLogger(__name__)


async def acquire_token_by_login(
    service: Any,
    *,
    acquisition_id: str,
    site_name: str,
    credential_id: int | None,
    selected_credential: AccountCredentialDTO | None = None,
    captcha_retry_count: int = 0,
    login_attempts: list | None = None,
    account_retry_count: int = 0,
    tried_accounts: set[str] | None = None,
) -> TokenAcquisitionResult:
    self = service
    logger = service._logger
    start_time = time.time()
    login_attempts = login_attempts or []
    tried_accounts = tried_accounts or set()
    try:
        credential = await _resolve_credential(
            self, logger, acquisition_id, site_name, credential_id, selected_credential, tried_accounts
        )
        logger.info(
            "开始自动登录",
            extra={
                "acquisition_id": acquisition_id,
                "site_name": site_name,
                "account": mask_account(credential.account),
                "account_hash": stable_hash(credential.account),
            },
        )
        login_start_time = time.time()
        try:
            return await _execute_login_success(
                self, logger, credential, acquisition_id, site_name, login_start_time, start_time, login_attempts
            )
        except TimeoutError:
            return await _handle_timeout_error(
                self, logger, credential, acquisition_id, site_name, login_start_time, start_time, login_attempts
            )
        except LoginFailedError as e:
            return await _handle_login_failed_error(
                self,
                logger,
                e,
                credential,
                acquisition_id,
                site_name,
                credential_id,
                login_start_time,
                start_time,
                captcha_retry_count,
                login_attempts,
                account_retry_count,
                tried_accounts,
            )
        except TokenAcquisitionTimeoutError as e:
            return await _handle_token_acquisition_timeout(
                self, logger, e, credential, acquisition_id, site_name, login_start_time, start_time, login_attempts
            )
    except Exception as e:
        logger.exception("操作失败")
        return _handle_outer_exception(logger, e, acquisition_id, site_name, start_time, login_attempts)


async def _resolve_credential(
    self,
    logger: Any,
    acquisition_id: str,
    site_name: str,
    credential_id: int | None,
    selected_credential: AccountCredentialDTO | None,
    tried_accounts: set[str],
) -> AccountCredentialDTO:
    """解析并返回要使用的凭证"""
    if credential_id:
        credential = await self._get_credential_by_id(credential_id)
        if not credential:
            raise ValidationException(f"无效的凭证ID: {credential_id}")
        tried_accounts.add(credential.account)
        logger.info(
            "使用指定账号",
            extra={
                "acquisition_id": acquisition_id,
                "site_name": site_name,
                "account": mask_account(credential.account),
                "account_hash": stable_hash(credential.account),
                "credential_id": credential_id,
            },
        )
        return credential
    if selected_credential:
        tried_accounts.add(selected_credential.account)
        logger.info(
            "使用已选择账号",
            extra={
                "acquisition_id": acquisition_id,
                "site_name": site_name,
                "account": mask_account(selected_credential.account),
                "account_hash": stable_hash(selected_credential.account),
                "selection_reason": "pre_selected",
            },
        )
        return selected_credential
    credential = await self.account_selection_strategy.select_account(site_name)
    if not credential:
        raise NoAvailableAccountError(f"网站 {site_name} 没有可用账号")
    tried_accounts.add(credential.account)
    logger.info(
        "自动选择账号",
        extra={
            "acquisition_id": acquisition_id,
            "site_name": site_name,
            "account": mask_account(credential.account),
            "account_hash": stable_hash(credential.account),
            "selection_reason": "best_available",
        },
    )
    return credential


async def _execute_login_success(
    self,
    logger: Any,
    credential: Any,
    acquisition_id: Any,
    site_name: Any,
    login_start_time: Any,
    start_time: Any,
    login_attempts: Any,
) -> TokenAcquisitionResult:
    """执行登录并在成功时保存 token"""
    token = await asyncio.wait_for(
        self.auto_login_service.login_and_get_token(credential), timeout=self.concurrency_config.acquisition_timeout
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
            "account": mask_account(credential.account),
            "account_hash": stable_hash(credential.account),
        },
    )
    await self._save_token_for_account(site_name, credential.account, token)
    cache_manager.cache_token(site_name, self._cache_account(credential.account), token)
    await self.account_selection_strategy.update_account_statistics(
        account=credential.account, site_name=site_name, success=True
    )
    total_duration = time.time() - start_time
    logger.info(
        "自动登录成功",
        extra={
            "acquisition_id": acquisition_id,
            "site_name": site_name,
            "account": mask_account(credential.account),
            "account_hash": stable_hash(credential.account),
            "login_duration": login_duration,
            "total_duration": total_duration,
        },
    )
    return TokenAcquisitionResult(
        success=True,
        token=token,
        acquisition_method="auto_login",
        total_duration=total_duration,
        login_attempts=login_attempts,
    )


async def _handle_timeout_error(
    self,
    logger: Any,
    credential: Any,
    acquisition_id: Any,
    site_name: Any,
    login_start_time: Any,
    start_time: Any,
    login_attempts: Any,
) -> TokenAcquisitionResult:
    """处理登录超时:检查 token 是否已保存"""
    login_duration = time.time() - login_start_time
    logger.info(
        "登录超时,检查Token是否已保存",
        extra={
            "acquisition_id": acquisition_id,
            "site_name": site_name,
            "account": mask_account(credential.account),
            "account_hash": stable_hash(credential.account),
        },
    )
    await asyncio.sleep(0.2)
    saved_token = await self._get_token_for_account(site_name, credential.account)
    if saved_token:
        logger.info(
            "✅ 超时但Token已保存成功",
            extra={
                "acquisition_id": acquisition_id,
                "site_name": site_name,
                "account": mask_account(credential.account),
                "account_hash": stable_hash(credential.account),
            },
        )
        login_attempts.append(
            LoginAttemptResult(
                success=True,
                token=saved_token,
                account=credential.account,
                error_message="超时但Token已保存",
                attempt_duration=login_duration,
                retry_count=1,
            )
        )
        await self.account_selection_strategy.update_account_statistics(
            account=credential.account, site_name=site_name, success=True
        )
        return TokenAcquisitionResult(
            success=True,
            token=saved_token,
            acquisition_method="auto_login_timeout_recovered",
            total_duration=time.time() - start_time,
            login_attempts=login_attempts,
        )
    error_msg = f"登录超时({self.concurrency_config.acquisition_timeout}秒)"
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
    await self.account_selection_strategy.update_account_statistics(
        account=credential.account, site_name=site_name, success=False
    )
    logger.error(
        "自动登录超时",
        extra={
            "acquisition_id": acquisition_id,
            "site_name": site_name,
            "account": mask_account(credential.account),
            "account_hash": stable_hash(credential.account),
            "timeout": self.concurrency_config.acquisition_timeout,
            "login_duration": login_duration,
        },
    )
    raise TokenAcquisitionTimeoutError(message=error_msg, errors={}) from None


async def _handle_login_failed_error(
    self,
    logger: Any,
    e: Any,
    credential: Any,
    acquisition_id: Any,
    site_name: Any,
    credential_id: Any,
    login_start_time: Any,
    start_time: Any,
    captcha_retry_count: Any,
    login_attempts: Any,
    account_retry_count: Any,
    tried_accounts: Any,
) -> TokenAcquisitionResult:
    """处理登录失败:记录尝试,按错误类型决定是否重试"""
    login_duration = time.time() - login_start_time
    error_type = (getattr(e, "errors", None) or {}).get("error_type")
    if hasattr(e, "attempts") and e.attempts:
        login_attempts.extend(e.attempts)
    else:
        login_attempts.append(
            LoginAttemptResult(
                success=False,
                token=None,
                account=credential.account,
                error_message=str(e),
                attempt_duration=login_duration,
                retry_count=captcha_retry_count + 1,
            )
        )
    if error_type == "captcha_error" and captcha_retry_count < 3:
        return await acquire_token_by_login(
            self,
            acquisition_id=acquisition_id,
            site_name=site_name,
            credential_id=credential_id,
            selected_credential=credential,
            captcha_retry_count=captcha_retry_count + 1,
            login_attempts=login_attempts,
            account_retry_count=account_retry_count,
            tried_accounts=tried_accounts,
        )
    await self.account_selection_strategy.update_account_statistics(
        account=credential.account, site_name=site_name, success=False
    )
    if error_type == "credential_error" and credential_id is None and (account_retry_count < 4):
        alternate = await self.account_selection_strategy.select_account(site_name)
        if alternate and alternate.account not in tried_accounts:
            tried_accounts.add(alternate.account)
            return await acquire_token_by_login(
                self,
                acquisition_id=acquisition_id,
                site_name=site_name,
                credential_id=credential_id,
                selected_credential=alternate,
                captcha_retry_count=0,
                login_attempts=login_attempts,
                account_retry_count=account_retry_count + 1,
                tried_accounts=tried_accounts,
            )
    logger.error(
        "自动登录失败",
        extra={
            "acquisition_id": acquisition_id,
            "site_name": site_name,
            "account": mask_account(credential.account),
            "account_hash": stable_hash(credential.account),
            "error": str(e),
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
        error_details={},
    )


async def _handle_token_acquisition_timeout(
    self,
    logger: Any,
    e: Any,
    credential: Any,
    acquisition_id: Any,
    site_name: Any,
    login_start_time: Any,
    start_time: Any,
    login_attempts: Any,
) -> TokenAcquisitionResult:
    """处理 AutoLoginService 超时"""
    login_duration = time.time() - login_start_time
    logger.info(
        "AutoLoginService超时,检查Token是否已保存",
        extra={
            "acquisition_id": acquisition_id,
            "site_name": site_name,
            "account": mask_account(credential.account),
            "account_hash": stable_hash(credential.account),
        },
    )
    await asyncio.sleep(0.2)
    saved_token = await self._maybe_await(self.token_service.get_token(site_name))
    if saved_token:
        logger.info(
            "✅ AutoLoginService超时但Token已保存成功",
            extra={
                "acquisition_id": acquisition_id,
                "site_name": site_name,
                "account": mask_account(credential.account),
                "account_hash": stable_hash(credential.account),
            },
        )
        login_attempts.append(
            LoginAttemptResult(
                success=True,
                token=saved_token,
                account=credential.account,
                error_message="超时但Token已保存",
                attempt_duration=login_duration,
                retry_count=1,
            )
        )
        await self.account_selection_strategy.update_account_statistics(
            account=credential.account, site_name=site_name, success=True
        )
        return TokenAcquisitionResult(
            success=True,
            token=saved_token,
            acquisition_method="auto_login_timeout_recovered",
            total_duration=time.time() - start_time,
            login_attempts=login_attempts,
        )
    logger.error(
        "AutoLoginService超时且Token未保存",
        extra={
            "acquisition_id": acquisition_id,
            "site_name": site_name,
            "account": mask_account(credential.account),
            "account_hash": stable_hash(credential.account),
            "login_duration": login_duration,
        },
    )
    await self.account_selection_strategy.update_account_statistics(
        account=credential.account, site_name=site_name, success=False
    )
    return TokenAcquisitionResult(
        success=False,
        token=None,
        acquisition_method="auto_login_timeout",
        total_duration=time.time() - start_time,
        login_attempts=login_attempts,
        error_details={},
    )


def _handle_outer_exception(
    logger: Any, e: Any, acquisition_id: Any, site_name: Any, start_time: Any, login_attempts: Any
) -> TokenAcquisitionResult:
    """处理外层异常"""
    total_duration = time.time() - start_time
    if isinstance(e, (LoginFailedError, NoAvailableAccountError, TokenAcquisitionTimeoutError, ValidationException)):
        return TokenAcquisitionResult(
            success=False,
            token=None,
            acquisition_method="auto_login",
            total_duration=total_duration,
            login_attempts=login_attempts,
            error_details={},
        )
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
        error_details={},
    )
