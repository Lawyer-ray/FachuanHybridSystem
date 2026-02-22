"""
自动Token获取服务基础属性测试

**Feature: auto-token-acquisition, Properties 1-5**
**Validates: Requirements 1.1-2.5**
"""

import asyncio
from datetime import datetime
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

# patch 路径：指向使用处（import 进来的名字），不是定义处
_PATCH_CACHE = "apps.automation.services.token.auto_token_acquisition_service.cache_manager"
_PATCH_CACHE2 = "apps.automation.services.token._login_handler.cache_manager"
_PATCH_PERF = "apps.automation.services.token.auto_token_acquisition_service.performance_monitor"
_PATCH_CONC = "apps.automation.services.token.auto_token_acquisition_service.concurrency_optimizer"
_PATCH_HIST = "apps.automation.services.token.auto_token_acquisition_service.history_recorder"


def create_test_credential(site_name: str, account_id: int = 1) -> AccountCredentialDTO:
    """创建测试用的AccountCredentialDTO"""
    return AccountCredentialDTO(
        id=account_id,
        lawyer_id=1,
        site_name=site_name,
        url=None,
        account=f"test{account_id}@example.com",
        password="password",
        last_login_success_at=datetime.now().isoformat(),
        login_success_count=5,
        login_failure_count=0,
        is_preferred=True,
    )


def _make_token_service_mock(return_value: str | None) -> AsyncMock:
    """创建 token_service AsyncMock，正确 mock get_token_internal / save_token_internal"""
    mock = AsyncMock()
    mock.get_token_internal = AsyncMock(return_value=return_value)
    mock.save_token_internal = AsyncMock()
    return mock


def _configure_singleton_mocks(
    mock_cache: Mock,
    mock_cache2: Mock,
    mock_perf: Mock,
    mock_conc: Mock,
    mock_hist: Mock,
) -> None:
    """统一配置单例 mock 的行为"""
    mock_cache.get_cached_token.return_value = None
    mock_cache.cache_token = Mock()  # 同步调用
    mock_cache2.cache_token = Mock()  # _login_handler 里也是同步调用
    mock_perf.record_acquisition_start = Mock()  # 同步调用
    mock_perf.record_acquisition_end = Mock()  # 同步调用
    mock_conc.acquire_resource = AsyncMock()
    mock_conc.release_resource = AsyncMock()
    mock_hist.record_acquisition_history = AsyncMock()


@pytest.mark.django_db
class TestBasicTokenAcquisitionProperties:
    """基础Token获取属性测试"""

    def setup_method(self) -> None:
        AutoTokenAcquisitionService.clear_locks()

    def teardown_method(self) -> None:
        AutoTokenAcquisitionService.clear_locks()

    @given(site_name=st.text(min_size=1, max_size=10).filter(lambda x: x.strip() and x.isalnum()))
    @settings(max_examples=5, deadline=15000)
    def test_token_acquisition_with_existing_token(self, site_name: str) -> None:
        """
        Property 1: 当存在有效Token时，直接返回现有Token

        **Validates: Requirements 1.1, 1.2**
        """

        async def _run() -> None:
            mock_account_strategy = Mock()
            mock_login_service = AsyncMock()
            mock_token_service = _make_token_service_mock(return_value=f"existing_token_{site_name}")
            mock_account_strategy.select_account = AsyncMock(return_value=create_test_credential(site_name))

            with (
                patch(_PATCH_CACHE) as mc,
                patch(_PATCH_CACHE2) as mc2,
                patch(_PATCH_PERF) as mp,
                patch(_PATCH_CONC) as mco,
                patch(_PATCH_HIST) as mh,
            ):
                _configure_singleton_mocks(mc, mc2, mp, mco, mh)
                service = AutoTokenAcquisitionService(
                    account_selection_strategy=mock_account_strategy,
                    auto_login_service=mock_login_service,
                    token_service=mock_token_service,
                )
                result = await service.acquire_token_if_needed(site_name)
                assert result == f"existing_token_{site_name}"
                mock_login_service.login_and_get_token.assert_not_called()

        asyncio.run(_run())

    @given(site_name=st.text(min_size=1, max_size=10).filter(lambda x: x.strip() and x.isalnum()))
    @settings(max_examples=5, deadline=15000)
    def test_token_acquisition_without_existing_token(self, site_name: str) -> None:
        """
        Property 2: 当不存在Token时，触发自动登录获取新Token

        **Validates: Requirements 1.1, 1.2**
        """

        async def _run() -> None:
            test_credential = create_test_credential(site_name)
            mock_account_strategy = Mock()
            mock_account_strategy.select_account = AsyncMock(return_value=test_credential)
            mock_account_strategy.update_account_statistics = AsyncMock()
            mock_login_service = AsyncMock()
            mock_login_service.login_and_get_token = AsyncMock(return_value=f"new_token_{site_name}")
            mock_token_service = _make_token_service_mock(return_value=None)

            with (
                patch(_PATCH_CACHE) as mc,
                patch(_PATCH_CACHE2) as mc2,
                patch(_PATCH_PERF) as mp,
                patch(_PATCH_CONC) as mco,
                patch(_PATCH_HIST) as mh,
            ):
                _configure_singleton_mocks(mc, mc2, mp, mco, mh)
                service = AutoTokenAcquisitionService(
                    account_selection_strategy=mock_account_strategy,
                    auto_login_service=mock_login_service,
                    token_service=mock_token_service,
                )
                result = await service.acquire_token_if_needed(site_name)
                assert result == f"new_token_{site_name}"
                mock_login_service.login_and_get_token.assert_called_once_with(test_credential)
                mock_token_service.save_token_internal.assert_called_once_with(
                    site_name=site_name,
                    account=test_credential.account,
                    token=f"new_token_{site_name}",
                    expires_in=3600,
                )

        asyncio.run(_run())

    @given(
        site_name=st.text(min_size=1, max_size=10).filter(lambda x: x.strip() and x.isalnum()),
        error_type=st.sampled_from(["network_error", "captcha_error", "credential_error"]),
    )
    @settings(max_examples=6, deadline=15000)
    def test_login_failure_exception_handling(self, site_name: str, error_type: str) -> None:
        """
        Property 3: 登录失败时抛出明确异常

        **Validates: Requirements 1.4**
        """

        async def _run() -> None:
            error_messages = {
                "network_error": "网络连接失败",
                "captcha_error": "验证码识别失败",
                "credential_error": "账号密码错误",
            }
            test_credential = create_test_credential(site_name)
            mock_account_strategy = Mock()
            mock_account_strategy.select_account = AsyncMock(return_value=test_credential)
            mock_account_strategy.update_account_statistics = AsyncMock()
            mock_login_service = AsyncMock()
            mock_login_service.login_and_get_token = AsyncMock(
                side_effect=LoginFailedError(
                    message=error_messages[error_type],
                    errors={"error_type": error_type},
                )
            )
            mock_token_service = _make_token_service_mock(return_value=None)

            with (
                patch(_PATCH_CACHE) as mc,
                patch(_PATCH_CACHE2) as mc2,
                patch(_PATCH_PERF) as mp,
                patch(_PATCH_CONC) as mco,
                patch(_PATCH_HIST) as mh,
            ):
                _configure_singleton_mocks(mc, mc2, mp, mco, mh)
                service = AutoTokenAcquisitionService(
                    account_selection_strategy=mock_account_strategy,
                    auto_login_service=mock_login_service,
                    token_service=mock_token_service,
                )
                with pytest.raises(AutoTokenAcquisitionError) as exc_info:
                    await service.acquire_token_if_needed(site_name)
                assert error_messages[error_type] in str(exc_info.value)

        asyncio.run(_run())

    @given(site_name=st.text(min_size=1, max_size=10).filter(lambda x: x.strip() and x.isalnum()))
    @settings(max_examples=3, deadline=15000)
    def test_no_available_account_handling(self, site_name: str) -> None:
        """
        Property 4: 没有可用账号时抛出NoAvailableAccountError

        **Validates: Requirements 2.4**
        """

        async def _run() -> None:
            mock_account_strategy = Mock()
            mock_account_strategy.select_account = AsyncMock(return_value=None)
            mock_login_service = AsyncMock()
            mock_token_service = _make_token_service_mock(return_value=None)

            with (
                patch(_PATCH_CACHE) as mc,
                patch(_PATCH_CACHE2) as mc2,
                patch(_PATCH_PERF) as mp,
                patch(_PATCH_CONC) as mco,
                patch(_PATCH_HIST) as mh,
            ):
                _configure_singleton_mocks(mc, mc2, mp, mco, mh)
                service = AutoTokenAcquisitionService(
                    account_selection_strategy=mock_account_strategy,
                    auto_login_service=mock_login_service,
                    token_service=mock_token_service,
                )
                with pytest.raises(NoAvailableAccountError):
                    await service.acquire_token_if_needed(site_name)

        asyncio.run(_run())

    @given(invalid_site_name=st.one_of(st.just(""), st.just("   ")))
    @settings(max_examples=3, deadline=5000)
    def test_parameter_validation(self, invalid_site_name: str) -> None:
        """
        Property 5: 参数验证

        **Validates: Requirements 1.1**
        """

        async def _run() -> None:
            mock_account_strategy = Mock()
            mock_account_strategy.select_account = AsyncMock()
            mock_login_service = AsyncMock()
            mock_token_service = _make_token_service_mock(return_value=None)

            with (
                patch(_PATCH_CACHE) as mc,
                patch(_PATCH_CACHE2) as mc2,
                patch(_PATCH_PERF) as mp,
                patch(_PATCH_CONC) as mco,
                patch(_PATCH_HIST) as mh,
            ):
                _configure_singleton_mocks(mc, mc2, mp, mco, mh)
                service = AutoTokenAcquisitionService(
                    account_selection_strategy=mock_account_strategy,
                    auto_login_service=mock_login_service,
                    token_service=mock_token_service,
                )
                with pytest.raises(ValidationException) as exc_info:
                    await service.acquire_token_if_needed(invalid_site_name)
                assert "网站名称不能为空" in str(exc_info.value)

        asyncio.run(_run())
