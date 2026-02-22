"""Business logic services."""

from __future__ import annotations

import logging
import time
from typing import Any, cast

from apps.automation.exceptions import AutoTokenAcquisitionError, NoAvailableAccountError, TokenAcquisitionTimeoutError
from apps.automation.services.token.trigger_reasons import TokenTriggerReason
from apps.automation.utils.logging_mixins.common import mask_account, stable_hash
from apps.core.exceptions import ValidationException

logger = logging.getLogger(__name__)


class TokenAcquisitionOrchestrator:
    def __init__(self, service: Any) -> None:
        self._service = service

    async def acquire_token_if_needed(self, site_name: str, credential_id: int | None = None) -> str:
        svc = self._service
        start_time = time.time()
        acquisition_id = f"{site_name}_{credential_id or 'auto'}_{int(start_time)}"
        account_marker = "auto" if credential_id is None else f"credential:{credential_id}"

        if not isinstance(site_name, str) or not site_name.strip():
            raise ValidationException("网站名称不能为空")

        from apps.automation.utils.logging import AutomationLogger

        AutomationLogger.log_token_acquisition_start(
            acquisition_id=acquisition_id,
            site_name=site_name,
            credential_id=credential_id,
            trigger_reason=TokenTriggerReason.TOKEN_NEEDED,
        )
        logger.info("开始Token获取流程", extra={})

        svc._acquisition_count += 1
        svc.performance_monitor.record_acquisition_start(acquisition_id, site_name, account_marker)

        try:
            await svc.concurrency_optimizer.acquire_resource(acquisition_id, site_name, account_marker)
            try:
                if credential_id:
                    credential = await svc._get_credential_by_id(credential_id)
                    if not credential:
                        raise ValidationException(f"无效的凭证ID: {credential_id}")

                    cached_account = svc._cache_account(credential.account)
                    existing_token = svc.cache_manager.get_cached_token(site_name, cached_account)
                    if not existing_token:
                        existing_token = await svc._get_token_for_account(site_name, credential.account)
                        if existing_token:
                            svc.cache_manager.cache_token(site_name, cached_account, existing_token)

                    if existing_token:
                        AutomationLogger.log_existing_token_used(
                            acquisition_id=acquisition_id,
                            site_name=site_name,
                            account=credential.account,
                            acquisition_method="existing",
                        )
                        return cast(str, existing_token)
                else:
                    credential = await svc.account_selection_strategy.select_account(site_name)
                    if credential:
                        cached_account = svc._cache_account(credential.account)
                        existing_token = svc.cache_manager.get_cached_token(site_name, cached_account)
                        if not existing_token:
                            existing_token = await svc._get_token_for_account(site_name, credential.account)
                            if existing_token:
                                svc.cache_manager.cache_token(site_name, cached_account, existing_token)

                        if existing_token:
                            logger.info(
                                "使用现有Token(自动选择账号)",
                                extra={
                                    "acquisition_id": acquisition_id,
                                    "site_name": site_name,
                                    "account": mask_account(credential.account),
                                    "account_hash": stable_hash(credential.account),
                                    "acquisition_method": "existing",
                                },
                            )
                            return cast(str, existing_token)
                    else:
                        logger.error(
                            "没有找到可用账号", extra={"acquisition_id": acquisition_id, "site_name": site_name}
                        )
                        raise NoAvailableAccountError(
                            f"网站 {site_name} 没有找到法院一张网的账号凭证\n\n"
                            "请在 Admin 后台添加账号:\n"
                            "1. 访问 /admin/organization/accountcredential/\n"
                            "2. 点击「添加账号密码」\n"
                            "3. URL 填写:https://zxfw.court.gov.cn\n"
                            "4. 填写账号和密码\n"
                            "5. 保存后重新执行询价"
                        )

                result = await svc._acquire_token_by_login(acquisition_id, site_name, credential_id, credential)
                total_duration = time.time() - start_time

                if result.success:
                    svc._success_count += 1
                    svc.performance_monitor.record_acquisition_end(
                        acquisition_id,
                        True,
                        total_duration,
                        result.login_attempts[0].attempt_duration if result.login_attempts else None,
                    )

                    if not svc._cache_namespace:
                        await svc.history_recorder.record_acquisition_history(
                            acquisition_id,
                            site_name,
                            credential.account if credential else "unknown",
                            credential_id,
                            result,
                            TokenTriggerReason.TOKEN_NEEDED,
                        )

                    AutomationLogger.log_token_acquisition_success(
                        acquisition_id=acquisition_id,
                        site_name=site_name,
                        account=credential.account,
                        total_duration=total_duration,
                        acquisition_method=result.acquisition_method,
                        login_attempts=len(result.login_attempts),
                        success_rate=svc._success_count / svc._acquisition_count,
                    )
                    return cast(str, result.token)

                svc._failure_count += 1
                error_msg = f"Token获取失败({site_name}): {result.error_details.get('message', '未知错误')}"

                error_type = result.error_details.get("error_type", "unknown")
                svc.performance_monitor.record_acquisition_end(
                    acquisition_id, False, total_duration, error_type=error_type
                )

                if not svc._cache_namespace:
                    await svc.history_recorder.record_acquisition_history(
                        acquisition_id,
                        site_name,
                        credential.account if credential else "unknown",
                        credential_id,
                        result,
                        TokenTriggerReason.TOKEN_NEEDED,
                    )

                logger.error(
                    "Token获取失败",
                    extra={
                        "acquisition_id": acquisition_id,
                        "site_name": site_name,
                        "total_duration": total_duration,
                        "error_details": result.error_details,
                        "login_attempts": len(result.login_attempts),
                        "failure_rate": svc._failure_count / svc._acquisition_count,
                    },
                )
                raise AutoTokenAcquisitionError(
                    message=error_msg, code="TOKEN_ACQUISITION_FAILED", errors=result.error_details
                )
            finally:
                await svc.concurrency_optimizer.release_resource(acquisition_id, site_name, account_marker)
        except (
            AutoTokenAcquisitionError,
            ValidationException,
            NoAvailableAccountError,
            TokenAcquisitionTimeoutError,
        ):
            # 内层 try 已记录过 record_acquisition_end，直接透传
            raise
        except Exception as e:
            total_duration = time.time() - start_time
            error_type = type(e).__name__
            svc.performance_monitor.record_acquisition_end(acquisition_id, False, total_duration, error_type=error_type)

            svc._failure_count += 1
            logger.error(
                "Token获取过程中发生未预期错误",
                extra={
                    "acquisition_id": acquisition_id,
                    "site_name": site_name,
                    "error": str(e),
                    "total_duration": total_duration,
                },
                exc_info=True,
            )
            raise AutoTokenAcquisitionError(
                message=f"Token获取过程中发生未预期错误: {e!s}", code="TOKEN_ACQUISITION_ERROR", errors={}
            ) from e
