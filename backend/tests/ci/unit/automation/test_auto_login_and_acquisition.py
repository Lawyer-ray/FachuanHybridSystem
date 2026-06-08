"""AutoLoginService 和 AutoTokenAcquisitionService 测试。"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from apps.automation.services.token.auto_login_service import (
    AutoLoginService,
    RetryConfig,
)


class TestRetryConfigAutoLogin:
    """auto_login_service 的 RetryConfig 测试。"""

    def test_defaults(self) -> None:
        cfg = RetryConfig()
        assert cfg.max_network_retries == 3
        assert cfg.max_captcha_retries == 3
        assert cfg.network_retry_delay_base == 1.0
        assert cfg.captcha_retry_delay == 2.0
        assert cfg.login_timeout == 60.0


class TestAutoLoginService:
    """AutoLoginService 测试。"""

    def _make_service(self) -> AutoLoginService:
        svc = AutoLoginService.__new__(AutoLoginService)
        svc.retry_config = RetryConfig()
        svc._browser_service = MagicMock()
        svc._usecase = None
        svc._login_attempts = []
        return svc

    def test_init_defaults(self) -> None:
        svc = AutoLoginService()
        assert svc.retry_config.max_network_retries == 3
        assert svc._login_attempts == []

    def test_init_with_custom_config(self) -> None:
        cfg = RetryConfig(max_network_retries=5)
        svc = AutoLoginService(retry_config=cfg)
        assert svc.retry_config.max_network_retries == 5

    def test_browser_service_property(self) -> None:
        svc = self._make_service()
        assert svc._browser_service is not None
        assert svc.browser_service is svc._browser_service

    def test_browser_service_lazy_load(self) -> None:
        svc = AutoLoginService.__new__(AutoLoginService)
        svc.retry_config = RetryConfig()
        svc._browser_service = MagicMock()
        svc._usecase = None
        svc._login_attempts = []
        result = svc.browser_service
        assert result is svc._browser_service

    @pytest.mark.asyncio
    async def test_login_and_get_token_delegates_to_usecase(self) -> None:
        svc = self._make_service()
        mock_usecase = MagicMock()
        mock_usecase.execute = AsyncMock(return_value="token123")
        svc._usecase = mock_usecase

        credential = MagicMock()
        credential.site_name = "test"
        credential.account = "test"
        result = await svc.login_and_get_token(credential)
        assert result == "token123"

    def test_login_attempts_cleared_on_init(self) -> None:
        svc = self._make_service()
        svc._login_attempts.append(MagicMock())
        assert len(svc._login_attempts) == 1


class TestAutoTokenAcquisitionService:
    """AutoTokenAcquisitionService 关键方法测试。"""

    def test_init_defaults(self) -> None:
        from apps.automation.services.token.auto_token_acquisition_service import AutoTokenAcquisitionService
        svc = AutoTokenAcquisitionService()
        assert svc._acquisition_count == 0
        assert svc._success_count == 0
        assert svc._failure_count == 0

    def test_init_with_deps(self) -> None:
        from apps.automation.services.token.auto_token_acquisition_service import AutoTokenAcquisitionService
        mock_strategy = MagicMock()
        mock_login = MagicMock()
        mock_token = MagicMock()
        svc = AutoTokenAcquisitionService(
            account_selection_strategy=mock_strategy,
            auto_login_service=mock_login,
            token_service=mock_token,
        )
        assert svc._account_selection_strategy is mock_strategy
        assert svc._auto_login_service is mock_login
        assert svc._token_service is mock_token
