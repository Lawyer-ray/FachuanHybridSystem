"""Tests for automation.usecases.token.auto_login_usecase — Round 4 deeper coverage.

Covers: _sync_login_attempt with browser context, _single_login_attempt
with various network keywords, execute with LoginFailedError re-raise,
_captcha_retries with exception logging.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.automation.exceptions import (
    AutoTokenAcquisitionError,
    LoginFailedError,
    TokenAcquisitionTimeoutError,
)
from apps.automation.usecases.token.auto_login_usecase import (
    AutoLoginUsecase,
    RetryConfig,
)
from apps.core.exceptions import NetworkError
from apps.core.dto.auth import LoginAttemptResult
from apps.core.dto.organization import AccountCredentialDTO

_LOGGER_PATCH = "apps.automation.utils.logging.AutomationLogger"


def _make_credential(account: str = "user@test.com", site_name: str = "test_site") -> AccountCredentialDTO:
    return AccountCredentialDTO(
        id=1,
        lawyer_id=1,
        lawyer_name="Test Lawyer",
        site_name=site_name,
        url="https://example.com",
        account=account,
        password="pass123",
    )


def _make_usecase(
    *,
    max_network_retries: int = 2,
    max_captcha_retries: int = 2,
    login_timeout: float = 30.0,
    sync_login_attempt=None,
) -> AutoLoginUsecase:
    cfg = RetryConfig(
        max_network_retries=max_network_retries,
        max_captcha_retries=max_captcha_retries,
        login_timeout=login_timeout,
        captcha_retry_delay=0.01,
        network_retry_delay_base=0.01,
    )
    time_counter = [0.0]

    def fake_time():
        val = time_counter[0]
        time_counter[0] += 0.1
        return val

    return AutoLoginUsecase(
        retry_config=cfg,
        browser_context_factory=MagicMock(),
        login_gateway=MagicMock(),
        sync_login_attempt=sync_login_attempt,
        sleep=AsyncMock(),
        time_provider=fake_time,
    )


# ---------------------------------------------------------------------------
# _single_login_attempt — all network keywords
# ---------------------------------------------------------------------------


class TestSingleLoginAttemptNetworkKeywords:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("keyword", [
        "network", "connection", "timeout", "dns", "socket",
        "连接", "网络", "超时", "无法访问",
    ])
    async def test_detects_network_keyword(self, keyword):
        uc = _make_usecase(sync_login_attempt=None)
        uc._sync_login_attempt = MagicMock(side_effect=Exception(f"error {keyword} occurred"))
        with pytest.raises(NetworkError):
            await uc._single_login_attempt(_make_credential())

    @pytest.mark.asyncio
    async def test_non_network_error_passes_through(self):
        uc = _make_usecase(sync_login_attempt=None)
        uc._sync_login_attempt = MagicMock(side_effect=ValueError("captcha wrong"))
        with pytest.raises(ValueError, match="captcha wrong"):
            await uc._single_login_attempt(_make_credential())


# ---------------------------------------------------------------------------
# _sync_login_attempt — browser context lifecycle
# ---------------------------------------------------------------------------


class TestSyncLoginAttempt:
    def test_closes_browser_context_on_success(self):
        uc = _make_usecase()
        mock_ctx = MagicMock()
        uc.browser_context_factory.new_context.return_value = mock_ctx
        uc.login_gateway.login.return_value = "token123"

        result = uc._sync_login_attempt(_make_credential())
        assert result == "token123"
        mock_ctx.close.assert_called_once()

    def test_closes_browser_context_on_failure(self):
        uc = _make_usecase()
        mock_ctx = MagicMock()
        uc.browser_context_factory.new_context.return_value = mock_ctx
        uc.login_gateway.login.side_effect = ValueError("login failed")

        with pytest.raises(ValueError):
            uc._sync_login_attempt(_make_credential())
        mock_ctx.close.assert_called_once()

    def test_handles_close_exception(self):
        uc = _make_usecase()
        mock_ctx = MagicMock()
        mock_ctx.close.side_effect = RuntimeError("close failed")
        uc.browser_context_factory.new_context.return_value = mock_ctx
        uc.login_gateway.login.return_value = "token"

        # Should not raise even though close() fails
        result = uc._sync_login_attempt(_make_credential())
        assert result == "token"

    def test_no_context_created_returns_none(self):
        uc = _make_usecase()
        uc.browser_context_factory.new_context.return_value = None
        uc.login_gateway.login.return_value = "token"

        result = uc._sync_login_attempt(_make_credential())
        assert result == "token"
        # close should not be called when context is None


# ---------------------------------------------------------------------------
# execute — LoginFailedError re-raise
# ---------------------------------------------------------------------------


class TestExecuteReRaise:
    @pytest.mark.asyncio
    async def test_login_failed_error_reraised(self):
        with patch(_LOGGER_PATCH):
            uc = _make_usecase()
            uc._login_with_retries = AsyncMock(side_effect=LoginFailedError("bad creds"))
            with pytest.raises(LoginFailedError, match="bad creds"):
                await uc.execute(_make_credential())

    @pytest.mark.asyncio
    async def test_network_error_reraised(self):
        with patch(_LOGGER_PATCH):
            uc = _make_usecase()
            uc._login_with_retries = AsyncMock(side_effect=NetworkError("down"))
            with pytest.raises(NetworkError, match="down"):
                await uc.execute(_make_credential())

    @pytest.mark.asyncio
    async def test_auto_token_error_reraised(self):
        with patch(_LOGGER_PATCH):
            uc = _make_usecase()
            uc._login_with_retries = AsyncMock(side_effect=AutoTokenAcquisitionError("auto error"))
            with pytest.raises(AutoTokenAcquisitionError):
                await uc.execute(_make_credential())


# ---------------------------------------------------------------------------
# _login_with_retries — exponential backoff delay
# ---------------------------------------------------------------------------


class TestNetworkRetryDelay:
    @pytest.mark.asyncio
    async def test_exponential_backoff_called(self):
        call_count = 0

        async def fail_then_succeed(cred, network_attempt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise NetworkError("fail")
            return "tok"

        cfg = RetryConfig(
            max_network_retries=3,
            max_captcha_retries=1,
            captcha_retry_delay=0.0,
            network_retry_delay_base=2.0,
        )

        mock_sleep = AsyncMock()

        uc = AutoLoginUsecase(
            retry_config=cfg,
            browser_context_factory=MagicMock(),
            login_gateway=MagicMock(),
            sync_login_attempt=None,
            sleep=mock_sleep,
            time_provider=lambda: 0.0,
        )
        uc._login_with_captcha_retries = fail_then_succeed

        result = await uc._login_with_retries(_make_credential())
        assert result == "tok"
        # Should have called sleep once with delay = 2.0 * (2 ** (1-1)) = 2.0
        mock_sleep.assert_called_once_with(2.0)


# ---------------------------------------------------------------------------
# _captcha_retries — exception logging
# ---------------------------------------------------------------------------


class TestCaptchaRetriesLogging:
    @pytest.mark.asyncio
    async def test_failed_attempt_logged(self):
        call_count = 0

        async def fail_then_succeed(cred):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("captcha error")
            return "tok"

        cfg = RetryConfig(max_captcha_retries=3, captcha_retry_delay=0.0, network_retry_delay_base=0.0, max_network_retries=1)

        def fake_time():
            fake_time.val += 0.1
            return fake_time.val
        fake_time.val = 0.0

        uc = AutoLoginUsecase(
            retry_config=cfg,
            browser_context_factory=MagicMock(),
            login_gateway=MagicMock(),
            sync_login_attempt=None,
            sleep=AsyncMock(),
            time_provider=fake_time,
        )
        uc._single_login_attempt = fail_then_succeed

        result = await uc._login_with_captcha_retries(_make_credential(), network_attempt=1)
        assert result == "tok"
        assert len(uc._login_attempts) == 2
        assert uc._login_attempts[0].success is False
        assert "captcha error" in uc._login_attempts[0].error_message
        assert uc._login_attempts[1].success is True


# ---------------------------------------------------------------------------
# __post_init__ — _login_attempts initialization
# ---------------------------------------------------------------------------


class TestPostInit:
    def test_initializes_login_attempts(self):
        uc = _make_usecase()
        assert uc._login_attempts == []

    def test_preserves_existing_attempts(self):
        uc = _make_usecase()
        existing = [MagicMock()]
        uc._login_attempts = existing
        # __post_init__ should not overwrite if already set
        # But since we set it after init, let's test the init behavior
        uc2 = AutoLoginUsecase(
            retry_config=RetryConfig(),
            browser_context_factory=MagicMock(),
            login_gateway=MagicMock(),
            _login_attempts=existing,
        )
        assert uc2._login_attempts is existing
