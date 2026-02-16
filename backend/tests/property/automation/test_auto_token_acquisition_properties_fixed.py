"""
自动Token获取服务属性测试 - 修复版本

**Feature: auto-token-acquisition, Properties 1-12**
**Validates: Requirements 1.1-5.5**

修复了并发控制Mock配置问题，避免测试卡住。
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.automation.exceptions import (
    AutoTokenAcquisitionError,
    LoginFailedError,
    NoAvailableAccountError,
    TokenAcquisitionTimeoutError,
)
from apps.automation.services.token.auto_token_acquisition_service import AutoTokenAcquisitionService
from apps.core.exceptions import ValidationException
from apps.core.interfaces import AccountCredentialDTO, LoginAttemptResult, TokenAcquisitionResult


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
        is_preferred=True,
    )


def setup_common_mocks(mock_concurrency, mock_perf, mock_history, mock_cache):
    """设置通用的Mock配置，确保返回值正确"""
    # 配置并发控制 - 确保返回值正确，避免测试卡住
    mock_concurrency.acquire_resource = AsyncMock(return_value=True)
    mock_concurrency.release_resource = AsyncMock(return_value=None)

    # 配置性能监控
    mock_perf.record_acquisition_start = Mock()
    mock_perf.record_acquisition_end = Mock()

    # 配置历史记录
    mock_history.record_acquisition_history = AsyncMock()

    # 配置缓存默认值
    mock_cache.get_cached_token = Mock(return_value=None)
    mock_cache.cache_token = Mock()


@pytest.mark.django_db
@pytest.mark.anyio
class TestLoginSuccessContinuationProperties:
    """
    Property 2: 登录成功后任务继续
    **验证: Requirements 1.3**
    """

    def setup_method(self):
        """每个测试前清理"""
        AutoTokenAcquisitionService.clear_locks()

    def teardown_method(self):
        """每个测试后清理"""
        AutoTokenAcquisitionService.clear_locks()

    @given(
        site_name=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
        login_delay=st.floats(min_value=0.1, max_value=2.0),
    )
    @settings(max_examples=30, deadline=None)
    async def test_task_continuation_after_login(self, site_name: str, login_delay: float):
        """
        Property 2: 登录成功后任务继续执行

        *For any* 网站名称和登录延迟，当自动登录成功后，
        原始任务应该能够继续执行并获得有效Token。

        **Validates: Requirements 1.3**
        """
        # 创建Mock服务
        mock_account_strategy = Mock()
        mock_login_service = AsyncMock()
        mock_token_service = Mock()

        # 创建测试凭证
        test_credential = create_test_credential(site_name)

        # 配置Mock行为 - 模拟登录延迟
        async def mock_login_with_delay(*args, **kwargs):
            await asyncio.sleep(login_delay)
            return f"token_after_{login_delay:.1f}s"

        mock_account_strategy.select_account = AsyncMock(return_value=test_credential)
        mock_account_strategy.update_account_statistics = AsyncMock()
        mock_token_service.get_token.return_value = None  # 没有现有Token
        mock_token_service.save_token = AsyncMock()  # Mock save_token方法
        mock_login_service.login_and_get_token = AsyncMock(side_effect=mock_login_with_delay)

        # Mock cache_manager 和其他依赖
        with patch("apps.automation.services.token.auto_token_acquisition_service.cache_manager") as mock_cache, patch(
            "apps.automation.services.token.auto_token_acquisition_service.concurrency_optimizer"
        ) as mock_concurrency, patch(
            "apps.automation.services.token.auto_token_acquisition_service.performance_monitor"
        ) as mock_perf, patch(
            "apps.automation.services.token.auto_token_acquisition_service.history_recorder"
        ) as mock_history:

            # 使用通用Mock设置函数
            setup_common_mocks(mock_concurrency, mock_perf, mock_history, mock_cache)

            # 创建服务实例
            service = AutoTokenAcquisitionService(
                account_selection_strategy=mock_account_strategy,
                auto_login_service=mock_login_service,
                token_service=mock_token_service,
            )

            # 记录开始时间
            start_time = asyncio.get_event_loop().time()

            # 执行测试
            result_token = await service.acquire_token_if_needed(site_name)

            # 记录结束时间
            end_time = asyncio.get_event_loop().time()
            actual_duration = end_time - start_time

            # 验证结果
            expected_token = f"token_after_{login_delay:.1f}s"
            assert result_token == expected_token, f"应该返回登录后的Token: {expected_token}"

            # 验证执行时间合理（允许一定误差）
            assert actual_duration >= login_delay * 0.8, f"执行时间应该至少是登录延迟的80%"
            assert actual_duration <= login_delay + 5.0, f"执行时间不应该超过登录延迟+5秒"

            # 验证登录服务被调用
            assert mock_login_service.login_and_get_token.call_count == 1

            # 验证并发控制被正确调用
            mock_concurrency.acquire_resource.assert_called_once()
            mock_concurrency.release_resource.assert_called_once()
