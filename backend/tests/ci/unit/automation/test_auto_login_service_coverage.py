"""Tests for auto_login_service — coverage for uncovered branches."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:
    from plugins import has_court_login_plugin
    _HAS_LOGIN = has_court_login_plugin()
except ImportError:
    _HAS_LOGIN = False

if _HAS_LOGIN:
    from plugins.court_automation.token.auto_login_service import AutoLoginService, RetryConfig
else:
    AutoLoginService = None  # type: ignore[assignment,misc]
    RetryConfig = None  # type: ignore[assignment,misc]

from apps.core.exceptions import (
    AutoTokenAcquisitionError,
    LoginFailedError,
    NetworkError,
    TokenAcquisitionTimeoutError,
)
from apps.core.interfaces import AccountCredentialDTO

pytestmark = pytest.mark.skipif(not _HAS_LOGIN, reason="court_login plugin not installed")


def _make_cred(account: str = "test@test.com", site_name: str = "court") -> AccountCredentialDTO:
    return AccountCredentialDTO(
        id=1,
        lawyer_id=1,
        lawyer_name="Test",
        site_name=site_name,
        url=None,
        account=account,
        password="pass",
        last_login_success_at=None,
        login_success_count=0,
        login_failure_count=0,
    )


class TestRetryConfig:
    def test_default_values(self) -> None:
        cfg = RetryConfig()
        assert cfg.max_network_retries == 3
        assert cfg.max_captcha_retries == 3
        assert cfg.network_retry_delay_base == 1.0
        assert cfg.captcha_retry_delay == 2.0
        assert cfg.login_timeout == 60.0

    def test_custom_values(self) -> None:
        cfg = RetryConfig(max_network_retries=5, login_timeout=30.0)
        assert cfg.max_network_retries == 5
        assert cfg.login_timeout == 30.0


class TestAutoLoginServiceInit:
    def test_default_config(self) -> None:
        svc = AutoLoginService()
        assert svc.retry_config is not None
        assert svc._browser_service is None
        assert svc._usecase is None

    def test_custom_config(self) -> None:
        cfg = RetryConfig(max_network_retries=10)
        svc = AutoLoginService(retry_config=cfg)
        assert svc.retry_config.max_network_retries == 10

    def test_injected_deps(self) -> None:
        mock_bs = MagicMock()
        mock_uc = MagicMock()
        svc = AutoLoginService(browser_service=mock_bs, usecase=mock_uc)
        assert svc._browser_service is mock_bs
        assert svc._usecase is mock_uc


class TestBrowserServiceProperty:
    def test_lazy_loads_when_none(self) -> None:
        svc = AutoLoginService()
        with patch("apps.core.services.browser.get_browser_service") as mock_get:
            mock_get.return_value = MagicMock()
            result = svc.browser_service
            assert result is not None

    def test_returns_existing(self) -> None:
        mock_bs = MagicMock()
        svc = AutoLoginService(browser_service=mock_bs)
        assert svc.browser_service is mock_bs


class TestLoginAndGetToken:
    @pytest.mark.asyncio
    async def test_delegates_to_usecase(self) -> None:
        mock_uc = AsyncMock()
        mock_uc.execute.return_value = "token_abc"
        svc = AutoLoginService(usecase=mock_uc)
        cred = _make_cred()
        result = await svc.login_and_get_token(cred)
        assert result == "token_abc"
        mock_uc.execute.assert_called_once_with(cred)

    @pytest.mark.asyncio
    async def test_timeout_raises(self) -> None:
        svc = AutoLoginService(retry_config=RetryConfig(login_timeout=0.1))

        async def _slow_login(cred: AccountCredentialDTO) -> str:
            await asyncio.sleep(10)
            return "token"

        svc._login_with_retries = _slow_login  # type: ignore[assignment]
        with pytest.raises(TokenAcquisitionTimeoutError):
            await svc.login_and_get_token(_make_cred())

    @pytest.mark.asyncio
    async def test_login_failed_error_propagates(self) -> None:
        svc = AutoLoginService()
        svc._login_with_retries = AsyncMock(side_effect=LoginFailedError(message="bad creds", attempts=[]))  # type: ignore[assignment]
        with patch("apps.automation.utils.logging.AutomationLogger"):
            with pytest.raises(LoginFailedError):
                await svc.login_and_get_token(_make_cred())

    @pytest.mark.asyncio
    async def test_network_error_propagates(self) -> None:
        svc = AutoLoginService()
        svc._login_with_retries = AsyncMock(side_effect=NetworkError("network issue"))  # type: ignore[assignment]
        with patch("apps.automation.utils.logging.AutomationLogger"):
            with pytest.raises(NetworkError):
                await svc.login_and_get_token(_make_cred())

    @pytest.mark.asyncio
    async def test_generic_exception_wrapped_as_login_failed(self) -> None:
        svc = AutoLoginService()
        svc._login_with_retries = AsyncMock(side_effect=ValueError("something unexpected"))  # type: ignore[assignment]
        with patch("apps.automation.utils.logging.AutomationLogger"):
            with pytest.raises(LoginFailedError, match="未预期错误"):
                await svc.login_and_get_token(_make_cred())


class TestSingleLoginAttempt:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        svc = AutoLoginService()
        with patch.object(svc, "_sync_login_attempt", return_value="token_ok"):
            result = await svc._single_login_attempt(_make_cred())
            assert result == "token_ok"

    @pytest.mark.asyncio
    async def test_network_error_keyword(self) -> None:
        svc = AutoLoginService()
        with patch.object(svc, "_sync_login_attempt", side_effect=Exception("connection refused")):
            with pytest.raises(NetworkError, match="网络连接错误"):
                await svc._single_login_attempt(_make_cred())

    @pytest.mark.asyncio
    async def test_non_network_error(self) -> None:
        svc = AutoLoginService()
        with patch.object(svc, "_sync_login_attempt", side_effect=Exception("验证码错误")):
            with pytest.raises(Exception, match="验证码错误"):
                await svc._single_login_attempt(_make_cred())


class TestLoginAttempts:
    def test_get_returns_copy(self) -> None:
        svc = AutoLoginService()
        attempts = svc.get_login_attempts()
        assert isinstance(attempts, list)
        assert attempts == []

    def test_clear(self) -> None:
        svc = AutoLoginService()
        svc._login_attempts.append(MagicMock())
        svc.clear_login_attempts()
        assert len(svc._login_attempts) == 0
