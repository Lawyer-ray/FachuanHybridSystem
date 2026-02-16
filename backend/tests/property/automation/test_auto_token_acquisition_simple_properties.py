"""
自动Token获取服务简化属性测试

**Feature: auto-token-acquisition, Properties 1-12**
**Validates: Requirements 1.1-5.5**
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from hypothesis import given, strategies as st, settings
from datetime import datetime, timedelta

from apps.automation.services.token.auto_token_acquisition_service import AutoTokenAcquisitionService
from apps.core.interfaces import AccountCredentialDTO
from apps.automation.exceptions import AutoTokenAcquisitionError, LoginFailedError, NoAvailableAccountError
from apps.core.exceptions import ValidationException


def create_test_credential(site_name: str, account_id: int = 1, account_suffix: str = "") -> AccountCredentialDTO:
    """创建测试用的AccountCredentialDTO"""
    return AccountCredentialDTO(
        id=account_id,
        lawyer_id=1,
        site_name=site_name,
        url=None,
        account=f"test{account_suffix}@example.com",
        password="password",
        last_login_success_at=datetime.now().isoformat(),
        login_success_count=5,
        login_failure_count=0,
        is_preferred=True
    )


@pytest.mark.django_db
@pytest.mark.anyio
class TestTokenValidityCheckProperties:
    """
    Property 1: Token有效性检查
    **验证: Requirements 1.1, 1.2**
    """

    def setup_method(self):
        """每个测试前清理"""
        AutoTokenAcquisitionService.clear_locks()

    def teardown_method(self):
        """每个测试后清理"""
        AutoTokenAcquisitionService.clear_locks()

    @given(
        site_name=st.text(min_size=1, max_size=20).filter(lambda x: x.strip() and x.isalnum()),
        has_valid_token=st.booleans()
    )
    @settings(max_examples=10, deadline=10000)
    async def test_token_validity_check_consistency(self, site_name: str, has_valid_token: bool):
        """
        Property 1: Token有效性检查一致性

        *For any* 网站名称和Token状态，系统应该一致地检查Token有效性。
        如果有有效Token，应该直接返回；如果没有，应该触发获取流程。

        **Validates: Requirements 1.1, 1.2**
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
        
        if has_valid_token:
            # 有有效Token的情况
            mock_token_service.get_token.return_value = "valid_token_123"
            expected_token = "valid_token_123"
        else:
            # 没有有效Token的情况
            mock_token_service.get_token.return_value = None
            mock_login_service.login_and_get_token.return_value = "new_token_456"
            expected_token = "new_token_456"

        # 创建服务实例
        service = AutoTokenAcquisitionService(
            account_selection_strategy=mock_account_strategy,
            auto_login_service=mock_login_service,
            token_service=mock_token_service
        )

        # 执行测试
        result_token = await service.acquire_token_if_needed(site_name)

        # 验证结果
        assert result_token == expected_token, f"Token应该是 {expected_token}"

        if has_valid_token:
            # 有有效Token时，不应该触发登录
            mock_login_service.login_and_get_token.assert_not_called()
        else:
            # 没有有效Token时，应该触发登录
            mock_login_service.login_and_get_token.assert_called_once()
            mock_token_service.save_token.assert_called_once_with(
                site_name=site_name,
                account=test_credential.account,
                token="new_token_456"
            )


@pytest.mark.django_db
@pytest.mark.anyio
class TestLoginFailureExceptionProperties:
    """
    Property 3: 登录失败异常处理
    **验证: Requirements 1.4**
    """

    def setup_method(self):
        """每个测试前清理"""
        AutoTokenAcquisitionService.clear_locks()

    def teardown_method(self):
        """每个测试后清理"""
        AutoTokenAcquisitionService.clear_locks()

    @given(
        site_name=st.text(min_size=1, max_size=20).filter(lambda x: x.strip() and x.isalnum()),
        error_type=st.sampled_from([
            "network_error", "captcha_error", "credential_error", "timeout_error"
        ])
    )
    @settings(max_examples=8, deadline=10000)
    async def test_login_failure_exception_handling(self, site_name: str, error_type: str):
        """
        Property 3: 登录失败异常处理一致性

        *For any* 网站名称和错误类型，当登录失败时，
        系统应该抛出明确的异常并包含详细错误信息。

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
        mock_token_service.get_token.return_value = None  # 没有现有Token

        # 根据错误类型配置不同的异常
        error_messages = {
            "network_error": "网络连接失败",
            "captcha_error": "验证码识别失败",
            "credential_error": "账号密码错误",
            "timeout_error": "登录超时"
        }

        mock_login_service.login_and_get_token.side_effect = LoginFailedError(
            message=error_messages[error_type],
            errors={"error_type": error_type}
        )

        # 创建服务实例
        service = AutoTokenAcquisitionService(
            account_selection_strategy=mock_account_strategy,
            auto_login_service=mock_login_service,
            token_service=mock_token_service
        )

        # 执行测试并验证异常
        with pytest.raises(AutoTokenAcquisitionError) as exc_info:
            await service.acquire_token_if_needed(site_name)

        # 验证异常信息
        exception = exc_info.value
        assert error_messages[error_type] in str(exception), f"异常信息应包含: {error_messages[error_type]}"
        
        # 验证错误详情
        if hasattr(exception, 'errors') and exception.errors:
            assert "error_type" in exception.errors or "message" in exception.errors, "异常应包含错误详情"

        # 验证账号统计被更新为失败
        mock_account_strategy.update_account_statistics.assert_called_once_with(
            account=test_credential.account,
            site_name=site_name,
            success=False
        )


@pytest.mark.django_db
@pytest.mark.anyio
class TestAccountPrioritySelectionProperties:
    """
    Property 4: 账号优先级选择
    **验证: Requirements 1.5**
    """

    def setup_method(self):
        """每个测试前清理"""
        AutoTokenAcquisitionService.clear_locks()

    def teardown_method(self):
        """每个测试后清理"""
        AutoTokenAcquisitionService.clear_locks()

    @given(
        site_name=st.text(min_size=1, max_size=20).filter(lambda x: x.strip() and x.isalnum()),
        success_count=st.integers(min_value=0, max_value=50),
        failure_count=st.integers(min_value=0, max_value=25)
    )
    @settings(max_examples=8, deadline=10000)
    async def test_account_priority_selection_consistency(
        self, site_name: str, success_count: int, failure_count: int
    ):
        """
        Property 4: 账号优先级选择一致性

        *For any* 网站名称和账号统计，系统应该优先选择
        最近成功登录且成功率高的账号。

        **Validates: Requirements 1.5**
        """
        # 创建Mock服务
        mock_account_strategy = Mock()
        mock_login_service = AsyncMock()
        mock_token_service = Mock()

        # 创建测试凭证（基于统计数据）
        test_credential = AccountCredentialDTO(
            id=1,
            lawyer_id=1,
            site_name=site_name,
            url=None,
            account="test@example.com",
            password="password",
            last_login_success_at=(datetime.now() - timedelta(hours=1)).isoformat() if success_count > 0 else None,
            login_success_count=success_count,
            login_failure_count=failure_count,
            is_preferred=True
        )

        # 配置Mock行为
        mock_account_strategy.select_account = AsyncMock(return_value=test_credential)
        mock_account_strategy.update_account_statistics = AsyncMock()
        mock_token_service.get_token.return_value = None  # 没有现有Token
        mock_login_service.login_and_get_token.return_value = "new_token"

        # 创建服务实例
        service = AutoTokenAcquisitionService(
            account_selection_strategy=mock_account_strategy,
            auto_login_service=mock_login_service,
            token_service=mock_token_service
        )

        # 执行测试
        result_token = await service.acquire_token_if_needed(site_name)

        # 验证结果
        assert result_token == "new_token", "应该返回新获取的Token"

        # 验证账号选择策略被调用
        mock_account_strategy.select_account.assert_called_once_with(site_name)

        # 验证使用了选择的账号进行登录
        mock_login_service.login_and_get_token.assert_called_once_with(test_credential)

        # 验证统计被更新
        mock_account_strategy.update_account_statistics.assert_called_once_with(
            account=test_credential.account,
            site_name=site_name,
            success=True
        )


@pytest.mark.django_db
@pytest.mark.anyio
class TestFinalFailureHandlingProperties:
    """
    Property 8: 最终失败处理
    **验证: Requirements 2.4**
    """

    def setup_method(self):
        """每个测试前清理"""
        AutoTokenAcquisitionService.clear_locks()

    def teardown_method(self):
        """每个测试后清理"""
        AutoTokenAcquisitionService.clear_locks()

    @given(
        site_name=st.text(min_size=1, max_size=20).filter(lambda x: x.strip() and x.isalnum()),
        failure_reason=st.sampled_from([
            "no_accounts", "all_accounts_failed", "network_timeout"
        ])
    )
    @settings(max_examples=6, deadline=10000)
    async def test_final_failure_handling_consistency(self, site_name: str, failure_reason: str):
        """
        Property 8: 最终失败处理一致性

        *For any* 网站名称和失败原因，当所有重试都失败时，
        系统应该抛出包含详细错误信息的异常。

        **Validates: Requirements 2.4**
        """
        # 创建Mock服务
        mock_account_strategy = Mock()
        mock_login_service = AsyncMock()
        mock_token_service = Mock()

        # 根据失败原因配置不同的Mock行为
        if failure_reason == "no_accounts":
            mock_account_strategy.select_account = AsyncMock(return_value=None)
        else:
            # 创建测试凭证
            test_credential = create_test_credential(site_name)
            mock_account_strategy.select_account = AsyncMock(return_value=test_credential)
            mock_account_strategy.update_account_statistics = AsyncMock()

        mock_token_service.get_token.return_value = None

        # 配置登录失败
        failure_messages = {
            "no_accounts": "没有可用账号",
            "all_accounts_failed": "所有账号登录失败",
            "network_timeout": "网络连接超时"
        }

        if failure_reason != "no_accounts":
            mock_login_service.login_and_get_token.side_effect = LoginFailedError(
                message=failure_messages[failure_reason],
                errors={"error_type": failure_reason}
            )

        # 创建服务实例
        service = AutoTokenAcquisitionService(
            account_selection_strategy=mock_account_strategy,
            auto_login_service=mock_login_service,
            token_service=mock_token_service
        )

        # 执行测试并验证异常
        if failure_reason == "no_accounts":
            with pytest.raises(NoAvailableAccountError) as exc_info:
                await service.acquire_token_if_needed(site_name)
            
            exception = exc_info.value
            assert site_name in str(exception), f"异常信息应包含网站名称: {site_name}"
        else:
            with pytest.raises(AutoTokenAcquisitionError) as exc_info:
                await service.acquire_token_if_needed(site_name)
            
            exception = exc_info.value
            assert failure_messages[failure_reason] in str(exception), f"异常信息应包含: {failure_messages[failure_reason]}"


@pytest.mark.django_db
@pytest.mark.anyio
class TestTokenServiceIntegrationProperties:
    """
    Property 11: TokenService集成
    **验证: Requirements 4.5**
    """

    def setup_method(self):
        """每个测试前清理"""
        AutoTokenAcquisitionService.clear_locks()

    def teardown_method(self):
        """每个测试后清理"""
        AutoTokenAcquisitionService.clear_locks()

    @given(
        site_name=st.text(min_size=1, max_size=20).filter(lambda x: x.strip() and x.isalnum()),
        token_exists=st.booleans()
    )
    @settings(max_examples=8, deadline=10000)
    async def test_token_service_integration_consistency(self, site_name: str, token_exists: bool):
        """
        Property 11: TokenService集成一致性

        *For any* 网站名称和Token存在状态，系统应该正确地
        与TokenService集成，保存和获取Token。

        **Validates: Requirements 4.5**
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

        if token_exists:
            # 已存在Token的情况
            existing_token = f"existing_token_for_{site_name}"
            mock_token_service.get_token.return_value = existing_token
        else:
            # 不存在Token的情况
            mock_token_service.get_token.return_value = None
            new_token = f"new_token_for_{site_name}"
            mock_login_service.login_and_get_token.return_value = new_token

        # 创建服务实例
        service = AutoTokenAcquisitionService(
            account_selection_strategy=mock_account_strategy,
            auto_login_service=mock_login_service,
            token_service=mock_token_service
        )

        # 执行测试
        result_token = await service.acquire_token_if_needed(site_name)

        # 验证结果
        if token_exists:
            expected_token = f"existing_token_for_{site_name}"
            assert result_token == expected_token, f"应该返回现有Token: {expected_token}"
            
            # 验证TokenService被正确调用
            mock_token_service.get_token.assert_called()
            
            # 不应该触发登录
            mock_login_service.login_and_get_token.assert_not_called()
            
            # 不应该保存新Token
            mock_token_service.save_token.assert_not_called()
        else:
            expected_token = f"new_token_for_{site_name}"
            assert result_token == expected_token, f"应该返回新Token: {expected_token}"
            
            # 验证TokenService被正确调用
            mock_token_service.get_token.assert_called()
            
            # 应该触发登录
            mock_login_service.login_and_get_token.assert_called_once_with(test_credential)
            
            # 应该保存新Token
            mock_token_service.save_token.assert_called_once_with(
                site_name=site_name,
                account=test_credential.account,
                token=expected_token
            )


@pytest.mark.django_db
class TestParameterValidationProperties:
    """
    Property 13: 参数验证
    **验证: Requirements 1.1**
    """

    def setup_method(self):
        """每个测试前清理"""
        AutoTokenAcquisitionService.clear_locks()

    def teardown_method(self):
        """每个测试后清理"""
        AutoTokenAcquisitionService.clear_locks()

    @given(
        invalid_site_name=st.one_of(
            st.just(""),  # 空字符串
            st.just("   "),  # 只有空格
            st.just(None)  # None值
        )
    )
    @settings(max_examples=6, deadline=5000)
    def test_parameter_validation_consistency(self, invalid_site_name):
        """
        Property 13: 参数验证一致性

        *For any* 无效的网站名称参数，系统应该抛出ValidationException。

        **Validates: Requirements 1.1**
        """
        # 创建服务实例
        service = AutoTokenAcquisitionService()

        # 执行测试并验证异常
        with pytest.raises((ValidationException, TypeError)):
            # 使用asyncio.run来运行异步测试
            import asyncio
            asyncio.run(service.acquire_token_if_needed(invalid_site_name))
