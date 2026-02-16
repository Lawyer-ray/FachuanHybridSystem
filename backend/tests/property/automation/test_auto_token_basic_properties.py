"""
自动Token获取服务基础属性测试

**Feature: auto-token-acquisition, Properties 1-5**
**Validates: Requirements 1.1-2.5**
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.automation.exceptions import AutoTokenAcquisitionError, LoginFailedError, NoAvailableAccountError
from apps.automation.services.token.auto_token_acquisition_service import AutoTokenAcquisitionService
from apps.core.exceptions import ValidationException
from apps.core.interfaces import AccountCredentialDTO


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


@pytest.mark.django_db
@pytest.mark.anyio
class TestBasicTokenAcquisitionProperties:
    """
    基础Token获取属性测试
    """

    def setup_method(self):
        """每个测试前清理"""
        AutoTokenAcquisitionService.clear_locks()

    def teardown_method(self):
        """每个测试后清理"""
        AutoTokenAcquisitionService.clear_locks()

    @given(site_name=st.text(min_size=1, max_size=10).filter(lambda x: x.strip() and x.isalnum()))
    @settings(max_examples=5, deadline=15000)
    async def test_token_acquisition_with_existing_token(self, site_name: str):
        """
        Property 1: 当存在有效Token时，直接返回现有Token

        **Validates: Requirements 1.1, 1.2**
        """
        # 创建Mock服务
        mock_account_strategy = Mock()
        mock_login_service = AsyncMock()
        mock_token_service = Mock()

        # 创建测试凭证
        test_credential = create_test_credential(site_name)

        # 配置Mock行为 - 有现有Token
        mock_account_strategy.select_account = AsyncMock(return_value=test_credential)
        mock_token_service.get_token.return_value = f"existing_token_{site_name}"

        # 禁用缓存和其他组件
        with patch("apps.automation.services.token.cache_manager.cache_manager") as mock_cache:
            mock_cache.get_cached_token.return_value = None  # 缓存未命中
            mock_cache.cache_token.return_value = None

            with patch("apps.automation.services.token.performance_monitor.performance_monitor") as mock_perf:
                mock_perf.record_acquisition_start.return_value = None
                mock_perf.record_acquisition_end.return_value = None

                with patch("apps.automation.services.token.concurrency_optimizer.concurrency_optimizer") as mock_conc:
                    mock_conc.acquire_resource = AsyncMock()
                    mock_conc.release_resource = AsyncMock()

                    with patch("apps.automation.services.token.history_recorder.history_recorder") as mock_hist:
                        mock_hist.record_acquisition_history = AsyncMock()

                        # 创建服务实例
                        service = AutoTokenAcquisitionService(
                            account_selection_strategy=mock_account_strategy,
                            auto_login_service=mock_login_service,
                            token_service=mock_token_service,
                        )

                        # 执行测试
                        result_token = await service.acquire_token_if_needed(site_name)

                        # 验证结果
                        expected_token = f"existing_token_{site_name}"
                        assert result_token == expected_token, f"应该返回现有Token: {expected_token}"

                        # 验证不应该触发登录
                        mock_login_service.login_and_get_token.assert_not_called()

    @given(site_name=st.text(min_size=1, max_size=10).filter(lambda x: x.strip() and x.isalnum()))
    @settings(max_examples=5, deadline=15000)
    async def test_token_acquisition_without_existing_token(self, site_name: str):
        """
        Property 2: 当不存在Token时，触发自动登录获取新Token

        **Validates: Requirements 1.1, 1.2**
        """
        # 创建Mock服务
        mock_account_strategy = Mock()
        mock_login_service = AsyncMock()
        mock_token_service = Mock()

        # 创建测试凭证
        test_credential = create_test_credential(site_name)

        # 配置Mock行为 - 没有现有Token
        mock_account_strategy.select_account = AsyncMock(return_value=test_credential)
        mock_account_strategy.update_account_statistics = AsyncMock()
        mock_token_service.get_token.return_value = None
        mock_login_service.login_and_get_token.return_value = f"new_token_{site_name}"

        # 禁用缓存和其他组件
        with patch("apps.automation.services.token.cache_manager.cache_manager") as mock_cache:
            mock_cache.get_cached_token.return_value = None  # 缓存未命中
            mock_cache.cache_token.return_value = None

            with patch("apps.automation.services.token.performance_monitor.performance_monitor") as mock_perf:
                mock_perf.record_acquisition_start.return_value = None
                mock_perf.record_acquisition_end.return_value = None

                with patch("apps.automation.services.token.concurrency_optimizer.concurrency_optimizer") as mock_conc:
                    mock_conc.acquire_resource = AsyncMock()
                    mock_conc.release_resource = AsyncMock()

                    with patch("apps.automation.services.token.history_recorder.history_recorder") as mock_hist:
                        mock_hist.record_acquisition_history = AsyncMock()

                        # 创建服务实例
                        service = AutoTokenAcquisitionService(
                            account_selection_strategy=mock_account_strategy,
                            auto_login_service=mock_login_service,
                            token_service=mock_token_service,
                        )

                        # 执行测试
                        result_token = await service.acquire_token_if_needed(site_name)

                        # 验证结果
                        expected_token = f"new_token_{site_name}"
                        assert result_token == expected_token, f"应该返回新Token: {expected_token}"

                        # 验证应该触发登录
                        mock_login_service.login_and_get_token.assert_called_once_with(test_credential)

                        # 验证应该保存Token
                        mock_token_service.save_token.assert_called_once_with(
                            site_name=site_name, account=test_credential.account, token=expected_token
                        )

    @given(
        site_name=st.text(min_size=1, max_size=10).filter(lambda x: x.strip() and x.isalnum()),
        error_type=st.sampled_from(["network_error", "captcha_error", "credential_error"]),
    )
    @settings(max_examples=6, deadline=15000)
    async def test_login_failure_exception_handling(self, site_name: str, error_type: str):
        """
        Property 3: 登录失败时抛出明确异常

        **Validates: Requirements 1.4**
        """
        # 创建Mock服务
        mock_account_strategy = Mock()
        mock_login_service = AsyncMock()
        mock_token_service = Mock()

        # 创建测试凭证
        test_credential = create_test_credential(site_name)

        # 配置Mock行为
        mock_account_strategy.select_account = AsyncMock(return_value=test_credential)
        mock_account_strategy.update_account_statistics = AsyncMock()
        mock_token_service.get_token.return_value = None

        # 配置登录失败
        error_messages = {
            "network_error": "网络连接失败",
            "captcha_error": "验证码识别失败",
            "credential_error": "账号密码错误",
        }

        mock_login_service.login_and_get_token.side_effect = LoginFailedError(
            message=error_messages[error_type], errors={"error_type": error_type}
        )

        # 禁用缓存和其他组件
        with patch("apps.automation.services.token.cache_manager.cache_manager") as mock_cache:
            mock_cache.get_cached_token.return_value = None
            mock_cache.cache_token.return_value = None

            with patch("apps.automation.services.token.performance_monitor.performance_monitor") as mock_perf:
                mock_perf.record_acquisition_start.return_value = None
                mock_perf.record_acquisition_end.return_value = None

                with patch("apps.automation.services.token.concurrency_optimizer.concurrency_optimizer") as mock_conc:
                    mock_conc.acquire_resource = AsyncMock()
                    mock_conc.release_resource = AsyncMock()

                    with patch("apps.automation.services.token.history_recorder.history_recorder") as mock_hist:
                        mock_hist.record_acquisition_history = AsyncMock()

                        # 创建服务实例
                        service = AutoTokenAcquisitionService(
                            account_selection_strategy=mock_account_strategy,
                            auto_login_service=mock_login_service,
                            token_service=mock_token_service,
                        )

                        # 执行测试并验证异常
                        with pytest.raises(AutoTokenAcquisitionError) as exc_info:
                            await service.acquire_token_if_needed(site_name)

                        # 验证异常信息
                        exception = exc_info.value
                        assert error_messages[error_type] in str(
                            exception
                        ), f"异常信息应包含: {error_messages[error_type]}"

    @given(site_name=st.text(min_size=1, max_size=10).filter(lambda x: x.strip() and x.isalnum()))
    @settings(max_examples=3, deadline=15000)
    async def test_no_available_account_handling(self, site_name: str):
        """
        Property 4: 没有可用账号时抛出NoAvailableAccountError

        **Validates: Requirements 2.4**
        """
        # 创建Mock服务
        mock_account_strategy = Mock()
        mock_login_service = AsyncMock()
        mock_token_service = Mock()

        # 配置Mock行为 - 没有可用账号
        mock_account_strategy.select_account = AsyncMock(return_value=None)
        mock_token_service.get_token.return_value = None

        # 禁用缓存和其他组件
        with patch("apps.automation.services.token.cache_manager.cache_manager") as mock_cache:
            mock_cache.get_cached_token.return_value = None
            mock_cache.cache_token.return_value = None

            with patch("apps.automation.services.token.performance_monitor.performance_monitor") as mock_perf:
                mock_perf.record_acquisition_start.return_value = None
                mock_perf.record_acquisition_end.return_value = None

                with patch("apps.automation.services.token.concurrency_optimizer.concurrency_optimizer") as mock_conc:
                    mock_conc.acquire_resource = AsyncMock()
                    mock_conc.release_resource = AsyncMock()

                    # 创建服务实例
                    service = AutoTokenAcquisitionService(
                        account_selection_strategy=mock_account_strategy,
                        auto_login_service=mock_login_service,
                        token_service=mock_token_service,
                    )

                    # 执行测试并验证异常
                    with pytest.raises(NoAvailableAccountError) as exc_info:
                        await service.acquire_token_if_needed(site_name)

                    # 验证异常信息包含网站名称
                    exception = exc_info.value
                    assert site_name in str(exception), f"异常信息应包含网站名称: {site_name}"

    @given(invalid_site_name=st.one_of(st.just(""), st.just("   ")))  # 空字符串  # 只有空格
    @settings(max_examples=3, deadline=5000)
    async def test_parameter_validation(self, invalid_site_name):
        """
        Property 5: 参数验证

        **Validates: Requirements 1.1**
        """
        # 创建服务实例
        service = AutoTokenAcquisitionService()

        # 执行测试并验证异常
        with pytest.raises(ValidationException) as exc_info:
            await service.acquire_token_if_needed(invalid_site_name)

        # 验证异常信息
        exception = exc_info.value
        assert "网站名称不能为空" in str(exception), "应该包含参数验证错误信息"
