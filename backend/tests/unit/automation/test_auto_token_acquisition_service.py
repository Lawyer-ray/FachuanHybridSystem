"""
自动Token获取服务单元测试
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from apps.automation.exceptions import AutoTokenAcquisitionError, NoAvailableAccountError, TokenAcquisitionTimeoutError
from apps.automation.services.token.auto_token_acquisition_service import AutoTokenAcquisitionService, ConcurrencyConfig
from apps.core.exceptions import ValidationException
from apps.core.interfaces import AccountCredentialDTO, LoginAttemptResult


def create_test_credential(credential_id=1, site_name="court_zxfw", account="test_account") -> AccountCredentialDTO:
    """创建测试用的账号凭证DTO"""
    return AccountCredentialDTO(
        id=credential_id,
        lawyer_id=1,
        site_name=site_name,
        url="https://test.com",
        account=account,
        password="test_password",
    )


@pytest.mark.django_db
class TestAutoTokenAcquisitionService:
    """自动Token获取服务测试"""

    def setup_method(self):
        """测试前准备"""
        self.mock_account_strategy = Mock()
        self.mock_account_strategy.select_account = AsyncMock()
        self.mock_account_strategy.update_account_statistics = AsyncMock()

        self.mock_login_service = Mock()
        self.mock_login_service.login_and_get_token = AsyncMock()

        self.mock_token_service = Mock()
        self.mock_token_service.get_token_internal = AsyncMock()
        self.mock_token_service.save_token_internal = AsyncMock()

        # 创建服务实例
        self.service = AutoTokenAcquisitionService(
            account_selection_strategy=self.mock_account_strategy,
            auto_login_service=self.mock_login_service,
            token_service=self.mock_token_service,
            concurrency_config=ConcurrencyConfig(acquisition_timeout=10.0),
        )

        # 清除类级别的锁
        AutoTokenAcquisitionService.clear_locks()

    def teardown_method(self):
        """测试后清理"""
        AutoTokenAcquisitionService.clear_locks()

    @pytest.mark.anyio
    async def test_acquire_token_with_existing_valid_token(self):
        """测试使用现有有效token"""
        site_name = "court_zxfw"
        existing_token = "existing_valid_token"
        credential = create_test_credential(site_name=site_name)

        self.mock_token_service.get_token_internal.return_value = existing_token
        self.mock_account_strategy.select_account.return_value = credential

        result = await self.service.acquire_token_if_needed(site_name)

        assert result == existing_token
        self.mock_login_service.login_and_get_token.assert_not_called()

    @pytest.mark.anyio
    async def test_acquire_token_with_auto_login_success(self):
        """测试自动登录成功获取token"""
        site_name = "court_zxfw"
        new_token = "new_login_token"
        credential = create_test_credential(site_name=site_name)

        self.mock_token_service.get_token_internal.return_value = None
        self.mock_account_strategy.select_account.return_value = credential
        self.mock_login_service.login_and_get_token.return_value = new_token

        result = await self.service.acquire_token_if_needed(site_name)

        assert result == new_token
        self.mock_account_strategy.select_account.assert_called_once_with(site_name)
        self.mock_login_service.login_and_get_token.assert_called_once_with(credential)

    @pytest.mark.anyio
    async def test_acquire_token_with_specified_credential_id(self):
        """测试使用指定凭证ID获取token"""
        site_name = "court_zxfw"
        credential_id = 123
        new_token = "specified_credential_token"
        credential = create_test_credential(
            credential_id=credential_id, site_name=site_name, account="specified_account"
        )

        self.mock_token_service.get_token_internal.return_value = None
        self.mock_login_service.login_and_get_token.return_value = new_token

        with patch.object(self.service, "_get_credential_by_id", new=AsyncMock(return_value=credential)):
            result = await self.service.acquire_token_if_needed(site_name, credential_id)

        assert result == new_token
        self.mock_account_strategy.select_account.assert_not_called()
        self.mock_login_service.login_and_get_token.assert_called_once_with(credential)

    @pytest.mark.anyio
    async def test_acquire_token_validation_error(self):
        """测试参数验证错误"""
        with pytest.raises(ValidationException, match="网站名称不能为空"):
            await self.service.acquire_token_if_needed("")

        with pytest.raises(ValidationException, match="网站名称不能为空"):
            await self.service.acquire_token_if_needed(None)

    @pytest.mark.anyio
    async def test_acquire_token_no_available_account(self):
        """测试无可用账号"""
        site_name = "court_zxfw"

        self.mock_token_service.get_token_internal.return_value = None
        self.mock_account_strategy.select_account.return_value = None

        with pytest.raises(AutoTokenAcquisitionError):
            await self.service.acquire_token_if_needed(site_name)

    @pytest.mark.anyio
    async def test_acquire_token_login_timeout(self):
        """测试登录超时"""
        site_name = "court_zxfw"
        credential = create_test_credential(site_name=site_name)

        self.mock_token_service.get_token_internal.return_value = None
        self.mock_account_strategy.select_account.return_value = credential
        self.mock_login_service.login_and_get_token.side_effect = asyncio.TimeoutError()

        with pytest.raises(AutoTokenAcquisitionError):
            await self.service.acquire_token_if_needed(site_name)

    @pytest.mark.anyio
    async def test_concurrent_acquisition_same_site(self):
        """测试同一站点的并发获取"""
        site_name = "court_zxfw"
        token = "concurrent_token"
        credential = create_test_credential(site_name=site_name)

        self.mock_token_service.get_token_internal.return_value = None
        self.mock_account_strategy.select_account.return_value = credential

        async def slow_login(*args, **kwargs):
            await asyncio.sleep(0.1)
            return token

        self.mock_login_service.login_and_get_token.side_effect = slow_login

        tasks = [self.service.acquire_token_if_needed(site_name), self.service.acquire_token_if_needed(site_name)]
        results = await asyncio.gather(*tasks)

        assert all(result == token for result in results)
        assert self.mock_login_service.login_and_get_token.call_count <= 2

    def test_get_statistics(self):
        """测试统计功能"""
        stats = self.service.get_statistics()

        assert stats["acquisition_count"] == 0
        assert stats["success_count"] == 0
        assert stats["failure_count"] == 0
        assert stats["success_rate"] == 0
        assert stats["active_acquisitions"] == 0
        assert stats["active_locks"] == 0

    def test_reset_statistics(self):
        """测试重置统计"""
        self.service._acquisition_count = 10
        self.service._success_count = 8
        self.service._failure_count = 2

        self.service.reset_statistics()

        stats = self.service.get_statistics()
        assert stats["acquisition_count"] == 0
        assert stats["success_count"] == 0
        assert stats["failure_count"] == 0

    @pytest.mark.anyio
    async def test_check_any_valid_token(self):
        """测试检查任意有效token"""
        site_name = "court_zxfw"
        existing_token = "any_valid_token"
        credential = create_test_credential(site_name=site_name, account="any_account")

        self.mock_account_strategy.select_account.return_value = credential
        self.mock_token_service.get_token_internal.return_value = existing_token

        result = await self.service._check_any_valid_token(site_name)

        assert result == existing_token

    @pytest.mark.anyio
    async def test_check_any_valid_token_none_available(self):
        """测试检查任意有效token - 无可用账号"""
        site_name = "court_zxfw"

        self.mock_account_strategy.select_account.return_value = None

        result = await self.service._check_any_valid_token(site_name)

        assert result is None
