"""
自动Token获取服务简化属性测试

**Feature: auto-token-acquisition, Properties 1-13**
**Validates: Requirements 1.1-5.5**
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.automation.services.token.auto_token_acquisition_service import AutoTokenAcquisitionService
from apps.core.exceptions import (
    AutoTokenAcquisitionError,
    LoginFailedError,
    NoAvailableAccountError,
    ValidationException,
)
from apps.core.interfaces import AccountCredentialDTO

_PATCH_CACHE = "apps.automation.services.token.auto_token_acquisition_service.cache_manager"
_PATCH_CACHE2 = "apps.automation.services.token._login_handler.cache_manager"
_PATCH_PERF = "apps.automation.services.token.auto_token_acquisition_service.performance_monitor"
_PATCH_CONC = "apps.automation.services.token.auto_token_acquisition_service.concurrency_optimizer"
_PATCH_HIST = "apps.automation.services.token.auto_token_acquisition_service.history_recorder"


def _cred(site_name: str, account_id: int = 1, success: int = 5, failure: int = 0) -> AccountCredentialDTO:
    return AccountCredentialDTO(
        id=account_id,
        lawyer_id=1,
        site_name=site_name,
        url=None,
        account=f"test{account_id}@example.com",
        password="password",
        last_login_success_at=datetime.now().isoformat(),
        login_success_count=success,
        login_failure_count=failure,
        is_preferred=True,
    )


def _patches() -> tuple[Any, Any, Any, Any, Any]:
    return (
        patch(_PATCH_CACHE),
        patch(_PATCH_CACHE2),
        patch(_PATCH_PERF),
        patch(_PATCH_CONC),
        patch(_PATCH_HIST),
    )


def _cfg(mc: Mock, mc2: Mock, mp: Mock, mco: Mock, mh: Mock) -> None:
    mc.get_cached_token.return_value = None
    mc.cache_token = Mock()
    mc2.cache_token = Mock()
    mp.record_acquisition_start = Mock()
    mp.record_acquisition_end = Mock()
    mco.acquire_resource = AsyncMock()
    mco.release_resource = AsyncMock()
    mh.record_acquisition_history = AsyncMock()


@pytest.mark.django_db
class TestTokenValidityCheckProperties:
    """Property 1: Token有效性检查 — Validates: Requirements 1.1, 1.2"""

    def setup_method(self) -> None:
        AutoTokenAcquisitionService.clear_locks()

    def teardown_method(self) -> None:
        AutoTokenAcquisitionService.clear_locks()

    @given(
        site_name=st.text(min_size=1, max_size=20).filter(lambda x: x.strip() and x.isalnum()),
        has_valid_token=st.booleans(),
    )
    @settings(max_examples=10, deadline=10000)
    def test_token_validity_check_consistency(self, site_name: str, has_valid_token: bool) -> None:
        """有Token直接返回，无Token触发登录"""

        async def _run() -> None:
            cred = _cred(site_name)
            mock_strategy = Mock()
            mock_strategy.select_account = AsyncMock(return_value=cred)
            mock_strategy.update_account_statistics = AsyncMock()
            mock_login = AsyncMock()
            mock_token = AsyncMock()

            if has_valid_token:
                mock_token.get_token_internal = AsyncMock(return_value="valid_token_123")
                expected = "valid_token_123"
            else:
                mock_token.get_token_internal = AsyncMock(return_value=None)
                mock_token.save_token_internal = AsyncMock()
                mock_login.login_and_get_token = AsyncMock(return_value="new_token_456")
                expected = "new_token_456"

            p1, p2, p3, p4, p5 = _patches()
            with p1 as mc, p2 as mc2, p3 as mp, p4 as mco, p5 as mh:
                _cfg(mc, mc2, mp, mco, mh)
                service = AutoTokenAcquisitionService(
                    account_selection_strategy=mock_strategy,
                    auto_login_service=mock_login,
                    token_service=mock_token,
                )
                result = await service.acquire_token_if_needed(site_name)
                assert result == expected
                if has_valid_token:
                    mock_login.login_and_get_token.assert_not_called()
                else:
                    mock_login.login_and_get_token.assert_called_once()

        asyncio.run(_run())


@pytest.mark.django_db
class TestLoginFailureExceptionProperties:
    """Property 3: 登录失败异常处理 — Validates: Requirements 1.4"""

    def setup_method(self) -> None:
        AutoTokenAcquisitionService.clear_locks()

    def teardown_method(self) -> None:
        AutoTokenAcquisitionService.clear_locks()

    @given(
        site_name=st.text(min_size=1, max_size=20).filter(lambda x: x.strip() and x.isalnum()),
        error_type=st.sampled_from(["network_error", "captcha_error", "credential_error"]),
    )
    @settings(max_examples=8, deadline=10000)
    def test_login_failure_exception_handling(self, site_name: str, error_type: str) -> None:
        """登录失败时抛出 AutoTokenAcquisitionError"""

        async def _run() -> None:
            messages = {
                "network_error": "网络连接失败",
                "captcha_error": "验证码识别失败",
                "credential_error": "账号密码错误",
            }
            cred = _cred(site_name)
            mock_strategy = Mock()
            mock_strategy.select_account = AsyncMock(return_value=cred)
            mock_strategy.update_account_statistics = AsyncMock()
            mock_login = AsyncMock()
            mock_login.login_and_get_token = AsyncMock(
                side_effect=LoginFailedError(message=messages[error_type], errors={"error_type": error_type})
            )
            mock_token = AsyncMock()
            mock_token.get_token_internal = AsyncMock(return_value=None)

            p1, p2, p3, p4, p5 = _patches()
            with p1 as mc, p2 as mc2, p3 as mp, p4 as mco, p5 as mh:
                _cfg(mc, mc2, mp, mco, mh)
                service = AutoTokenAcquisitionService(
                    account_selection_strategy=mock_strategy,
                    auto_login_service=mock_login,
                    token_service=mock_token,
                )
                with pytest.raises(AutoTokenAcquisitionError) as exc_info:
                    await service.acquire_token_if_needed(site_name)
                assert messages[error_type] in str(exc_info.value)
                mock_strategy.update_account_statistics.assert_called_once_with(
                    account=cred.account, site_name=site_name, success=False
                )

        asyncio.run(_run())


@pytest.mark.django_db
class TestAccountPrioritySelectionProperties:
    """Property 4: 账号优先级选择 — Validates: Requirements 1.5"""

    def setup_method(self) -> None:
        AutoTokenAcquisitionService.clear_locks()

    def teardown_method(self) -> None:
        AutoTokenAcquisitionService.clear_locks()

    @given(
        site_name=st.text(min_size=1, max_size=20).filter(lambda x: x.strip() and x.isalnum()),
        success_count=st.integers(min_value=0, max_value=50),
        failure_count=st.integers(min_value=0, max_value=25),
    )
    @settings(max_examples=8, deadline=10000)
    def test_account_priority_selection_consistency(
        self, site_name: str, success_count: int, failure_count: int
    ) -> None:
        """账号选择策略被调用，登录成功后统计更新"""

        async def _run() -> None:
            cred = AccountCredentialDTO(
                id=1,
                lawyer_id=1,
                site_name=site_name,
                url=None,
                account="test@example.com",
                password="password",
                last_login_success_at=(datetime.now() - timedelta(hours=1)).isoformat() if success_count > 0 else None,
                login_success_count=success_count,
                login_failure_count=failure_count,
                is_preferred=True,
            )
            mock_strategy = Mock()
            mock_strategy.select_account = AsyncMock(return_value=cred)
            mock_strategy.update_account_statistics = AsyncMock()
            mock_login = AsyncMock()
            mock_login.login_and_get_token = AsyncMock(return_value="new_token")
            mock_token = AsyncMock()
            mock_token.get_token_internal = AsyncMock(return_value=None)
            mock_token.save_token_internal = AsyncMock()

            p1, p2, p3, p4, p5 = _patches()
            with p1 as mc, p2 as mc2, p3 as mp, p4 as mco, p5 as mh:
                _cfg(mc, mc2, mp, mco, mh)
                service = AutoTokenAcquisitionService(
                    account_selection_strategy=mock_strategy,
                    auto_login_service=mock_login,
                    token_service=mock_token,
                )
                result = await service.acquire_token_if_needed(site_name)
                assert result == "new_token"
                mock_strategy.select_account.assert_called_once_with(site_name)
                mock_login.login_and_get_token.assert_called_once_with(cred)
                mock_strategy.update_account_statistics.assert_called_once_with(
                    account=cred.account, site_name=site_name, success=True
                )

        asyncio.run(_run())


@pytest.mark.django_db
class TestFinalFailureHandlingProperties:
    """Property 8: 最终失败处理 — Validates: Requirements 2.4"""

    def setup_method(self) -> None:
        AutoTokenAcquisitionService.clear_locks()

    def teardown_method(self) -> None:
        AutoTokenAcquisitionService.clear_locks()

    @given(
        site_name=st.text(min_size=1, max_size=20).filter(lambda x: x.strip() and x.isalnum()),
        failure_reason=st.sampled_from(["no_accounts", "all_accounts_failed", "network_timeout"]),
    )
    @settings(max_examples=6, deadline=10000)
    def test_final_failure_handling_consistency(self, site_name: str, failure_reason: str) -> None:
        """所有重试失败时抛出包含详细信息的异常"""

        async def _run() -> None:
            mock_strategy = Mock()
            mock_login = AsyncMock()
            mock_token = AsyncMock()
            mock_token.get_token_internal = AsyncMock(return_value=None)

            failure_messages = {
                "no_accounts": "没有可用账号",
                "all_accounts_failed": "所有账号登录失败",
                "network_timeout": "网络连接超时",
            }

            if failure_reason == "no_accounts":
                mock_strategy.select_account = AsyncMock(return_value=None)
            else:
                cred = _cred(site_name)
                mock_strategy.select_account = AsyncMock(return_value=cred)
                mock_strategy.update_account_statistics = AsyncMock()
                mock_login.login_and_get_token = AsyncMock(
                    side_effect=LoginFailedError(
                        message=failure_messages[failure_reason],
                        errors={"error_type": failure_reason},
                    )
                )

            p1, p2, p3, p4, p5 = _patches()
            with p1 as mc, p2 as mc2, p3 as mp, p4 as mco, p5 as mh:
                _cfg(mc, mc2, mp, mco, mh)
                service = AutoTokenAcquisitionService(
                    account_selection_strategy=mock_strategy,
                    auto_login_service=mock_login,
                    token_service=mock_token,
                )
                if failure_reason == "no_accounts":
                    with pytest.raises(NoAvailableAccountError):
                        await service.acquire_token_if_needed(site_name)
                else:
                    with pytest.raises(AutoTokenAcquisitionError) as exc_info:
                        await service.acquire_token_if_needed(site_name)
                    assert failure_messages[failure_reason] in str(exc_info.value)

        asyncio.run(_run())


@pytest.mark.django_db
class TestParameterValidationProperties:
    """Property 13: 参数验证 — Validates: Requirements 1.1"""

    def setup_method(self) -> None:
        AutoTokenAcquisitionService.clear_locks()

    def teardown_method(self) -> None:
        AutoTokenAcquisitionService.clear_locks()

    @given(invalid_site_name=st.one_of(st.just(""), st.just("   ")))
    @settings(max_examples=4, deadline=5000)
    def test_parameter_validation_consistency(self, invalid_site_name: str) -> None:
        """无效 site_name 抛出 ValidationException"""

        async def _run() -> None:
            mock_strategy = Mock()
            mock_strategy.select_account = AsyncMock()
            mock_login = AsyncMock()
            mock_token = AsyncMock()
            mock_token.get_token_internal = AsyncMock(return_value=None)

            p1, p2, p3, p4, p5 = _patches()
            with p1 as mc, p2 as mc2, p3 as mp, p4 as mco, p5 as mh:
                _cfg(mc, mc2, mp, mco, mh)
                service = AutoTokenAcquisitionService(
                    account_selection_strategy=mock_strategy,
                    auto_login_service=mock_login,
                    token_service=mock_token,
                )
                with pytest.raises(ValidationException):
                    await service.acquire_token_if_needed(invalid_site_name)

        asyncio.run(_run())
