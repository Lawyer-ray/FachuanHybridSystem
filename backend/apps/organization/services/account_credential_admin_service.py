"""
AccountCredentialAdminService - 账号凭证管理服务
封装 Admin 层的业务逻辑，包括自动登录功能
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from apps.core.interfaces import IAutoTokenAcquisitionService, IAutomationService
    from apps.organization.models import AccountCredential
    from apps.organization.services.account_credential_service import (
        AccountCredentialService,
    )

logger = logging.getLogger(__name__)


def _run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


@dataclass
class LoginResult:

    success: bool
    duration: float
    token: str | None = None
    error_message: str | None = None


@dataclass
class BatchLoginResult:

    success_count: int
    error_count: int
    total_duration: float
    message: str


class AccountCredentialAdminService:

    SUPPORTED_SITE: ClassVar[str] = "court_zxfw"

    def __init__(self) -> None:
        self._token_service: IAutoTokenAcquisitionService | None = None
        self._automation_service: IAutomationService | None = None
        self._credential_service: AccountCredentialService | None = None

    @property
    def credential_service(self) -> "AccountCredentialService":
        if self._credential_service is None:
            from apps.organization.services.account_credential_service import (
                AccountCredentialService,
            )

            self._credential_service = AccountCredentialService()
        return self._credential_service

    @property
    def token_service(self) -> "IAutoTokenAcquisitionService":
        if self._token_service is None:
            from apps.core.dependencies import build_auto_token_acquisition_service

            self._token_service = build_auto_token_acquisition_service()
        return self._token_service

    @property
    def automation_service(self) -> "IAutomationService":
        if self._automation_service is None:
            from apps.core.interfaces import ServiceLocator

            self._automation_service = ServiceLocator.get_automation_service()
        return self._automation_service

    def single_auto_login(
        self,
        credential_id: int,
        admin_user: str,
    ) -> LoginResult:
        credential = self.credential_service._get_credential_internal(credential_id)

        if credential.site_name != self.SUPPORTED_SITE:
            return LoginResult(
                success=False,
                duration=0,
                error_message=str(_("账号 %(account)s 不支持自动登录（仅支持法院一张网）")) % {"account": credential.account},
            )

        logger.info(
            "管理员手动触发自动登录",
            extra={
                "admin_user": admin_user,
                "credential_id": credential_id,
                "account": credential.account,
                "site_name": credential.site_name,
            },
        )

        return self._execute_single_login(
            credential=credential,
            admin_user=admin_user,
            trigger_reason="manual_trigger_admin",
        )

    def batch_auto_login(
        self,
        credential_ids: list[int],
        admin_user: str,
    ) -> BatchLoginResult:
        # 只处理法院一张网的账号，物化为列表避免多次 SQL 查询
        court_credentials = list(
            self.credential_service.filter_by_ids_and_site(
                credential_ids=credential_ids,
                site_name=self.SUPPORTED_SITE,
            )
        )

        if not court_credentials:
            return BatchLoginResult(
                success_count=0,
                error_count=0,
                total_duration=0,
                message=str(_("没有找到法院一张网账号")),
            )

        total_count = len(court_credentials)
        logger.info(
            "管理员批量触发自动登录",
            extra={
                "admin_user": admin_user,
                "credential_count": total_count,
                "credential_ids": [c.id for c in court_credentials],
            },
        )

        success_count = 0
        error_count = 0
        total_duration = 0.0

        for credential in court_credentials:
            result = self._execute_single_login(
                credential=credential,
                admin_user=admin_user,
                trigger_reason="batch_manual_trigger_admin",
            )

            total_duration += result.duration

            if result.success:
                success_count += 1
            else:
                error_count += 1

        # 汇总结果
        logger.info(
            "批量自动登录完成",
            extra={
                "admin_user": admin_user,
                "total_credentials": total_count,
                "success_count": success_count,
                "error_count": error_count,
                "total_duration": total_duration,
                "avg_duration": total_duration / total_count if total_count > 0 else 0,
            },
        )

        # 构建消息
        messages = []
        if success_count > 0:
            messages.append(str(_("✅ 成功触发 %(count)d 个账号的自动登录")) % {"count": success_count})
        if error_count > 0:
            messages.append(str(_("❌ %(count)d 个账号登录失败")) % {"count": error_count})
        messages.append(str(_("总耗时 %(duration).1f秒")) % {"duration": total_duration})

        return BatchLoginResult(
            success_count=success_count,
            error_count=error_count,
            total_duration=total_duration,
            message=str(_("，")).join(messages),
        )

    def _execute_single_login(
        self,
        credential: "AccountCredential",
        admin_user: str,
        trigger_reason: str,
    ) -> LoginResult:
        start_time = timezone.now()

        try:
            result = _run_async(
                self.token_service.acquire_token_if_needed(
                    site_name=self.SUPPORTED_SITE,
                    credential_id=credential.id,
                )
            )

            end_time = timezone.now()
            duration = (end_time - start_time).total_seconds()

            if result:
                self._record_login_history(
                    credential=credential,
                    success=True,
                    duration=duration,
                    token=result,
                    trigger_reason=trigger_reason,
                    start_time=start_time,
                    end_time=end_time,
                )
                self.credential_service.update_login_success(credential.id)

                logger.info(
                    "批量登录成功",
                    extra={
                        "admin_user": admin_user,
                        "credential_id": credential.id,
                        "account": credential.account,
                        "duration": duration,
                    },
                )

                return LoginResult(success=True, duration=duration, token=result)
            else:
                self._record_login_history(
                    credential=credential,
                    success=False,
                    duration=duration,
                    error_message=str(_("登录失败，未返回Token")),
                    trigger_reason=trigger_reason,
                    start_time=start_time,
                    end_time=end_time,
                )
                self.credential_service.update_login_failure(credential.id)

                return LoginResult(
                    success=False,
                    duration=duration,
                    error_message=str(_("登录失败，未返回Token")),
                )

        except Exception as e:
            end_time = timezone.now()
            duration = (end_time - start_time).total_seconds()

            self._record_login_history(
                credential=credential,
                success=False,
                duration=duration,
                error_message=str(e),
                trigger_reason=trigger_reason,
                start_time=start_time,
                end_time=end_time,
                error_details={
                    "error_type": type(e).__name__,
                    "admin_user": admin_user,
                    "batch_operation": True,
                },
            )
            self.credential_service.update_login_failure(credential.id)

            logger.error(
                "批量登录失败",
                extra={
                    "admin_user": admin_user,
                    "credential_id": credential.id,
                    "account": credential.account,
                    "error": str(e),
                    "duration": duration,
                },
                exc_info=True,
            )

            return LoginResult(success=False, duration=duration, error_message=str(e))

    def _record_login_history(
        self,
        credential: "AccountCredential",
        success: bool,
        duration: float,
        trigger_reason: str,
        start_time: datetime,
        end_time: datetime,
        token: str | None = None,
        error_message: str | None = None,
        error_details: dict[str, object] | None = None,
    ) -> None:
        # 通过automation服务获取
        try:
            automation_service = self.automation_service

            # 构建历史记录数据
            history_data = {
                "site_name": credential.site_name,
                "account": credential.account,
                "credential_id": credential.id,
                "trigger_reason": trigger_reason,
                "attempt_count": 1,
                "total_duration": duration,
                "created_at": start_time,
                "started_at": start_time,
                "finished_at": end_time,
            }

            if success:
                history_data.update(
                    {
                        "status": "SUCCESS",
                        "token_preview": token[:50] if token else None,
                    }
                )
            else:
                history_data.update(
                    {
                        "status": "FAILED",
                        "error_message": error_message,
                        "error_details": error_details,
                    }
                )

            # 通过automation服务创建历史记录
            automation_service.create_token_acquisition_history_internal(history_data)

        except Exception as e:
            # 记录历史失败不影响主流程
            logger.warning(
                "记录登录历史失败",
                extra={
                    "credential_id": credential.id,
                    "error": str(e),
                },
            )
