"""
自动Token获取服务属性测试 - 修复版本

**Feature: auto-token-acquisition, Properties 1-12**
**Validates: Requirements 1.1-5.5**
"""

from typing import Any
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.automation.services.token.auto_token_acquisition_service import AutoTokenAcquisitionService
from apps.core.interfaces import AccountCredentialDTO

_PATCH_CACHE = "apps.automation.services.token.auto_token_acquisition_service.cache_manager"
_PATCH_CACHE2 = "apps.automation.services.token._login_handler.cache_manager"
_PATCH_PERF = "apps.automation.services.token.auto_token_acquisition_service.performance_monitor"
_PATCH_CONC = "apps.automation.services.token.auto_token_acquisition_service.concurrency_optimizer"
_PATCH_HIST = "apps.automation.services.token.auto_token_acquisition_service.history_recorder"


def create_test_credential(site_name: str, account_id: int = 1) -> AccountCredentialDTO:
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


def setup_patches() -> tuple[Any, Any, Any, Any, Any]:
    return (
        patch(_PATCH_CACHE),
        patch(_PATCH_CACHE2),
        patch(_PATCH_PERF),
        patch(_PATCH_CONC),
        patch(_PATCH_HIST),
    )


def configure_mocks(mc: Mock, mc2: Mock, mp: Mock, mco: Mock, mh: Mock) -> None:
    mc.get_cached_token.return_value = None
    mc.cache_token = Mock()
    mc2.cache_token = Mock()
    mp.record_acquisition_start = Mock()
    mp.record_acquisition_end = Mock()
    mco.acquire_resource = AsyncMock()
    mco.release_resource = AsyncMock()
    mh.record_acquisition_history = AsyncMock()


@pytest.mark.django_db
class TestLoginSuccessContinuationProperties:
    """Property 2: 登录成功后任务继续 — Validates: Requirements 1.3"""

    def setup_method(self) -> None:
        AutoTokenAcquisitionService.clear_locks()

    def teardown_method(self) -> None:
        AutoTokenAcquisitionService.clear_locks()

    @given(
        site_name=st.text(min_size=1, max_size=20).filter(lambda x: x.strip() and x.isalnum()),
        login_delay=st.floats(min_value=0.01, max_value=0.1),
    )
    @settings(max_examples=5, deadline=10000)
    def test_task_continuation_after_login(self, site_name: str, login_delay: float) -> None:
        """Property 2: 登录成功后任务继续执行"""

        async def _run() -> None:
            test_credential = create_test_credential(site_name)
            mock_account_strategy = Mock()
            mock_account_strategy.select_account = AsyncMock(return_value=test_credential)
            mock_account_strategy.update_account_statistics = AsyncMock()
            mock_login_service = AsyncMock()

            async def mock_login_with_delay(*args: object, **kwargs: object) -> str:
                await asyncio.sleep(login_delay)
                return f"token_after_delay"

            mock_login_service.login_and_get_token = AsyncMock(side_effect=mock_login_with_delay)
            mock_token_service = AsyncMock()
            mock_token_service.get_token_internal = AsyncMock(return_value=None)
            mock_token_service.save_token_internal = AsyncMock()

            p1, p2, p3, p4, p5 = setup_patches()
            with p1 as mc, p2 as mc2, p3 as mp, p4 as mco, p5 as mh:
                configure_mocks(mc, mc2, mp, mco, mh)
                service = AutoTokenAcquisitionService(
                    account_selection_strategy=mock_account_strategy,
                    auto_login_service=mock_login_service,
                    token_service=mock_token_service,
                )
                result = await service.acquire_token_if_needed(site_name)
                assert result == "token_after_delay"
                mock_login_service.login_and_get_token.assert_called_once_with(test_credential)
                mco.acquire_resource.assert_called_once()
                mco.release_resource.assert_called_once()

        asyncio.run(_run())
