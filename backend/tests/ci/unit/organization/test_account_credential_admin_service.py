"""apps/organization/services/credential/account_credential_admin_service.py 单元测试。

覆盖自动登录（单发/批量）、_execute_single_login 的成功/无 Token/异常分支、
_finish_login 状态回写、_record_login_history 失败容错与依赖属性懒加载。
全部通过注入 mock 服务实现，不触发真实自动化登录。
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.organization.services.credential.account_credential_admin_service import (
    AccountCredentialAdminService,
    BatchLoginResult,
    LoginResult,
    _run_async,
)


def _credential(cred_id: int = 1, site: str = "court_zxfw", account: str = "acct") -> MagicMock:
    cred = MagicMock()
    cred.id = cred_id
    cred.site_name = site
    cred.account = account
    return cred


def _make_service(
    *,
    credentials: list[MagicMock] | None = None,
    token_result: str | None = "tok",
    token_error: Exception | None = None,
    history_error: Exception | None = None,
) -> tuple[AccountCredentialAdminService, dict[str, MagicMock]]:
    svc = AccountCredentialAdminService()

    credential_service = MagicMock()
    credential_service.get_credential_by_id.return_value = (credentials or [_credential()])[0]
    credential_service.filter_by_ids_and_site.return_value = credentials or []
    credential_service.update_login_success = MagicMock()
    credential_service.update_login_failure = MagicMock()

    token_service = MagicMock()

    async def _acquire(**kwargs: Any) -> str:
        if token_error is not None:
            raise token_error
        return token_result  # type: ignore[return-value]

    token_service.acquire_token_if_needed = _acquire

    automation_service = MagicMock()
    if history_error is not None:
        automation_service.create_token_acquisition_history_internal.side_effect = history_error
    else:
        automation_service.create_token_acquisition_history_internal = MagicMock()

    svc._credential_service = credential_service
    svc._token_service = token_service
    svc._automation_service = automation_service

    return svc, {
        "credential_service": credential_service,
        "token_service": token_service,
        "automation_service": automation_service,
    }


class TestRunAsync:
    def test_runs_coroutine_without_running_loop(self) -> None:
        async def coro() -> str:
            return "done"

        assert _run_async(coro()) == "done"

    def test_runs_in_thread_when_loop_already_running(self) -> None:
        """已有事件循环时在独立线程执行 asyncio.run。"""

        async def main() -> str:
            # 当前线程有运行中的 loop，_run_async 应走线程池分支
            return _run_async(inner())

        async def inner() -> str:
            await asyncio.sleep(0)
            return "threaded"

        assert asyncio.run(main()) == "threaded"


class TestLazyProperties:
    def test_credential_service_lazy_init(self) -> None:
        svc = AccountCredentialAdminService()
        with patch(
            "apps.organization.services.credential.account_credential_service.AccountCredentialService"
        ) as mock_cls:
            mock_cls.return_value = "svc-instance"  # type: ignore[assignment]
            first = svc.credential_service
            second = svc.credential_service
        assert first == "svc-instance"
        assert second is first
        mock_cls.assert_called_once()

    def test_token_service_lazy_init(self) -> None:
        svc = AccountCredentialAdminService()
        with patch("apps.core.dependencies.build_auto_token_acquisition_service") as mock_build:
            mock_build.return_value = "token-svc"  # type: ignore[assignment]
            assert svc.token_service == "token-svc"
            mock_build.assert_called_once()

    def test_automation_service_lazy_init(self) -> None:
        svc = AccountCredentialAdminService()
        with patch("apps.core.interfaces.ServiceLocator.get_automation_service") as mock_get:
            mock_get.return_value = "auto-svc"  # type: ignore[assignment]
            assert svc.automation_service == "auto-svc"
            mock_get.assert_called_once()


class TestSingleAutoLogin:
    def test_success_flow(self) -> None:
        cred = _credential(cred_id=7)
        svc, mocks = _make_service(credentials=[cred], token_result="tok-xyz")

        result = svc.single_auto_login(credential_id=7, admin_user="admin-1")

        assert isinstance(result, LoginResult)
        assert result.success is True
        assert result.token == "tok-xyz"
        assert result.duration >= 0
        mocks["credential_service"].update_login_success.assert_called_once_with(7)
        mocks["credential_service"].update_login_failure.assert_not_called()
        # 历史记录包含成功状态与 token 前 50 位
        history = mocks["automation_service"].create_token_acquisition_history_internal.call_args.args[0]
        assert history["status"] == "SUCCESS"
        assert history["trigger_reason"] == "manual_trigger_admin"
        assert history["token_preview"] == "tok-xyz"

    def test_unsupported_site_rejected(self) -> None:
        cred = _credential(site="other_site", account="a@x")
        svc, mocks = _make_service(credentials=[cred])

        result = svc.single_auto_login(credential_id=1, admin_user="admin")

        assert result.success is False
        assert "不支持自动登录" in result.error_message
        assert "a@x" in result.error_message
        assert result.duration == 0
        # 未进入登录流程
        mocks["credential_service"].update_login_success.assert_not_called()
        mocks["credential_service"].update_login_failure.assert_not_called()

    def test_no_token_returned_marks_failure(self) -> None:
        cred = _credential(cred_id=3)
        svc, mocks = _make_service(credentials=[cred], token_result=None)

        result = svc.single_auto_login(credential_id=3, admin_user="admin")

        assert result.success is False
        assert result.token is None
        assert "未返回Token" in result.error_message
        mocks["credential_service"].update_login_failure.assert_called_once_with(3)
        history = mocks["automation_service"].create_token_acquisition_history_internal.call_args.args[0]
        assert history["status"] == "FAILED"

    def test_token_exception_records_error_details(self) -> None:
        cred = _credential(cred_id=4, account="boom-acct")
        svc, mocks = _make_service(credentials=[cred], token_error=RuntimeError("playwright crashed"))

        result = svc.single_auto_login(credential_id=4, admin_user="admin-2")

        assert result.success is False
        assert "playwright crashed" in result.error_message
        mocks["credential_service"].update_login_failure.assert_called_once_with(4)
        history = mocks["automation_service"].create_token_acquisition_history_internal.call_args.args[0]
        assert history["status"] == "FAILED"
        assert history["error_details"]["error_type"] == "RuntimeError"
        assert history["error_details"]["batch_operation"] is True

    def test_long_token_truncated_in_history(self) -> None:
        cred = _credential(cred_id=5)
        long_token = "T" * 120
        svc, mocks = _make_service(credentials=[cred], token_result=long_token)

        svc.single_auto_login(credential_id=5, admin_user="admin")

        history = mocks["automation_service"].create_token_acquisition_history_internal.call_args.args[0]
        assert history["token_preview"] == "T" * 50

    def test_history_recording_failure_does_not_break_login(self) -> None:
        cred = _credential(cred_id=6)
        svc, mocks = _make_service(credentials=[cred], token_result="tok", history_error=RuntimeError("db down"))

        result = svc.single_auto_login(credential_id=6, admin_user="admin")

        # 历史记录失败不影响主流程：登录仍然成功
        assert result.success is True
        mocks["credential_service"].update_login_success.assert_called_once_with(6)


class TestBatchAutoLogin:
    def test_no_court_credentials_returns_zero_result(self) -> None:
        svc, mocks = _make_service(credentials=[])
        mocks["credential_service"].filter_by_ids_and_site.return_value = []

        result = svc.batch_auto_login(credential_ids=[1, 2], admin_user="admin")

        assert isinstance(result, BatchLoginResult)
        assert result.success_count == 0
        assert result.error_count == 0
        assert "没有找到法院一张网账号" in result.message
        mocks["credential_service"].filter_by_ids_and_site.assert_called_once_with(
            credential_ids=[1, 2], site_name="court_zxfw"
        )

    def test_all_success(self) -> None:
        creds = [_credential(cred_id=i, account=f"a{i}") for i in range(1, 4)]
        svc, mocks = _make_service(credentials=creds, token_result="tok")

        result = svc.batch_auto_login(credential_ids=[1, 2, 3], admin_user="batch-admin")

        assert result.success_count == 3
        assert result.error_count == 0
        assert "成功触发 3 个账号" in result.message
        assert mocks["credential_service"].update_login_success.call_count == 3
        # 批量场景 trigger_reason 为 batch 前缀
        history = mocks["automation_service"].create_token_acquisition_history_internal.call_args.args[0]
        assert history["trigger_reason"] == "batch_manual_trigger_admin"

    def test_mixed_results_summarized(self) -> None:
        good = _credential(cred_id=1, account="good")
        bad = _credential(cred_id=2, account="bad")

        svc = AccountCredentialAdminService()
        credential_service = MagicMock()
        credential_service.filter_by_ids_and_site.return_value = [good, bad]
        credential_service.update_login_success = MagicMock()
        credential_service.update_login_failure = MagicMock()
        svc._credential_service = credential_service

        token_service = MagicMock()

        async def _acquire(**kwargs: Any) -> str:
            if kwargs.get("credential_id") == 2:
                raise RuntimeError("login failed for 2")
            return "tok"

        token_service.acquire_token_if_needed = _acquire
        svc._token_service = token_service

        svc._automation_service = MagicMock()

        result = svc.batch_auto_login(credential_ids=[1, 2], admin_user="admin")

        assert result.success_count == 1
        assert result.error_count == 1
        assert "成功触发 1 个账号" in result.message
        assert "1 个账号登录失败" in result.message
        assert "总耗时" in result.message
        credential_service.update_login_success.assert_called_once_with(1)
        credential_service.update_login_failure.assert_called_once_with(2)

    def test_future_exception_becomes_error_result(self) -> None:
        """_execute_single_login 自身抛异常时按失败计入（汇总消息只含统计不含底层错误文本）。"""
        cred = _credential(cred_id=9)
        svc, mocks = _make_service(credentials=[cred], token_result="tok")
        svc._execute_single_login = MagicMock(side_effect=RuntimeError("executor boom"))  # type: ignore[method-assign]

        result = svc.batch_auto_login(credential_ids=[9], admin_user="admin")

        assert result.error_count == 1
        assert result.success_count == 0
        assert "1 个账号登录失败" in result.message
        mocks["credential_service"].update_login_success.assert_not_called()


class TestConstantsAndDataclasses:
    def test_supported_site_constant(self) -> None:
        assert AccountCredentialAdminService.SUPPORTED_SITE == "court_zxfw"

    def test_login_result_defaults(self) -> None:
        result = LoginResult(success=True, duration=1.5)
        assert result.token is None
        assert result.error_message is None

    def test_batch_login_result_fields(self) -> None:
        result = BatchLoginResult(success_count=2, error_count=1, total_duration=3.0, message="m")
        assert (result.success_count, result.error_count, result.total_duration, result.message) == (2, 1, 3.0, "m")
