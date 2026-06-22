"""Additional coverage tests for _login_handler."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:
    from plugins import has_court_login_plugin
    _HAS_LOGIN = has_court_login_plugin()
except ImportError:
    _HAS_LOGIN = False

from apps.core.exceptions import (
    LoginFailedError,
    NoAvailableAccountError,
    TokenAcquisitionTimeoutError,
    ValidationException,
)
from apps.core.interfaces import (
    AccountCredentialDTO,
    LoginAttemptResult,
    TokenAcquisitionResult,
)

pytestmark = pytest.mark.skipif(not _HAS_LOGIN, reason="court_login plugin not installed")


def _make_handler():
    from plugins.court_automation.token._login_handler import LoginHandler

    account_strategy = AsyncMock()
    auto_login = AsyncMock()
    token_service = AsyncMock()
    config = MagicMock()
    config.acquisition_timeout = 30
    return LoginHandler(account_strategy, auto_login, token_service, config)


class TestSelectCredentialIdNotFound:
    @pytest.mark.asyncio
    async def test_invalid_credential_id_raises(self):
        handler = _make_handler()
        with patch("apps.core.dependencies.build_organization_service") as mock_build:
            mock_svc = MagicMock()
            mock_svc.get_credential = AsyncMock(return_value=None)
            mock_build.return_value = mock_svc
            with pytest.raises(ValidationException, match="无效的凭证ID"):
                await handler.select_credential("acq1", "site", credential_id=999, selected_credential=None)


class TestHandleLoginTimeout:
    @pytest.mark.asyncio
    async def test_recovery_fails_raises_timeout(self):
        handler = _make_handler()
        credential = MagicMock()
        credential.account = "user1"
        handler.try_recover_token_after_timeout = AsyncMock(return_value=None)
        with pytest.raises(TokenAcquisitionTimeoutError):
            await handler.handle_login_timeout(
                acquisition_id="acq1",
                site_name="court",
                credential=credential,
                login_duration=10.0,
                login_attempts=[],
                start_time=time.time(),
                exc=TimeoutError(),
            )

    @pytest.mark.asyncio
    async def test_recovery_succeeds_returns_result(self):
        handler = _make_handler()
        credential = MagicMock()
        credential.account = "user1"
        recovered = TokenAcquisitionResult(
            success=True, token="recovered", acquisition_method="timeout_recovered",
            total_duration=5.0, login_attempts=[],
        )
        handler.try_recover_token_after_timeout = AsyncMock(return_value=recovered)
        result = await handler.handle_login_timeout(
            acquisition_id="acq1",
            site_name="court",
            credential=credential,
            login_duration=10.0,
            login_attempts=[],
            start_time=time.time(),
            exc=TimeoutError(),
        )
        assert result.success is True
        assert result.token == "recovered"


class TestHandleLoginFailed:
    @pytest.mark.asyncio
    async def test_exception_with_attempts(self):
        handler = _make_handler()
        credential = MagicMock()
        credential.account = "user1"
        exc = LoginFailedError("login failed")
        exc.attempts = [LoginAttemptResult(success=False, token=None, account="user1", error_message="fail", attempt_duration=5.0, retry_count=1)]
        result = await handler.handle_login_failed(
            acquisition_id="acq1",
            site_name="court",
            credential=credential,
            login_duration=5.0,
            login_attempts=[],
            start_time=time.time(),
            exc=exc,
        )
        assert result.success is False
        assert len(result.login_attempts) == 1

    @pytest.mark.asyncio
    async def test_exception_without_attempts(self):
        handler = _make_handler()
        credential = MagicMock()
        credential.account = "user1"
        exc = RuntimeError("generic error")
        result = await handler.handle_login_failed(
            acquisition_id="acq1",
            site_name="court",
            credential=credential,
            login_duration=3.0,
            login_attempts=[],
            start_time=time.time(),
            exc=exc,
        )
        assert result.success is False
        assert "generic error" in result.error_details["message"]


class TestAcquireTokenByLogin:
    @pytest.mark.asyncio
    async def test_success(self):
        handler = _make_handler()
        credential = MagicMock()
        credential.account = "user1"
        handler.select_credential = AsyncMock(return_value=credential)
        handler._auto_login_service.login_and_get_token = AsyncMock(return_value="token_abc")
        handler._token_service.save_token_internal = AsyncMock()
        handler._account_selection_strategy.update_account_statistics = AsyncMock()

        with patch("plugins.court_automation.token._login_handler.cache_manager") as mock_cache:
            result = await handler.acquire_token_by_login(
                acquisition_id="acq1", site_name="court", credential_id=None,
            )
            assert result.success is True
            assert result.token == "token_abc"
            mock_cache.cache_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_login_timeout_recovery_fails(self):
        handler = _make_handler()
        credential = MagicMock()
        credential.account = "user1"
        handler.select_credential = AsyncMock(return_value=credential)
        handler._auto_login_service.login_and_get_token = AsyncMock(side_effect=TimeoutError())
        handler.try_recover_token_after_timeout = AsyncMock(return_value=None)

        result = await handler.acquire_token_by_login(
            acquisition_id="acq1", site_name="court", credential_id=None,
        )
        # The flow: TimeoutError -> handle_login_timeout -> try_recover returns None
        # -> handle_login_timeout raises TokenAcquisitionTimeoutError
        # -> inner except catches it -> returns failure
        assert result.success is False

    @pytest.mark.asyncio
    async def test_login_failed(self):
        handler = _make_handler()
        credential = MagicMock()
        credential.account = "user1"
        handler.select_credential = AsyncMock(return_value=credential)
        handler._auto_login_service.login_and_get_token = AsyncMock(
            side_effect=LoginFailedError("wrong password")
        )

        result = await handler.acquire_token_by_login(
            acquisition_id="acq1", site_name="court", credential_id=None,
        )
        assert result.success is False

    @pytest.mark.asyncio
    async def test_no_available_account(self):
        handler = _make_handler()
        handler.select_credential = AsyncMock(side_effect=NoAvailableAccountError("no accounts"))

        result = await handler.acquire_token_by_login(
            acquisition_id="acq1", site_name="court", credential_id=None,
        )
        assert result.success is False
        assert "no accounts" in result.error_details["message"]

    @pytest.mark.asyncio
    async def test_token_acquisition_timeout_recovery_succeeds(self):
        handler = _make_handler()
        credential = MagicMock()
        credential.account = "user1"
        handler.select_credential = AsyncMock(return_value=credential)
        exc = TokenAcquisitionTimeoutError(message="timeout")
        handler._auto_login_service.login_and_get_token = AsyncMock(side_effect=exc)
        recovered = TokenAcquisitionResult(
            success=True, token="recovered_tok", acquisition_method="timeout_recovered",
            total_duration=10.0, login_attempts=[],
        )
        handler.try_recover_token_after_timeout = AsyncMock(return_value=recovered)

        result = await handler.acquire_token_by_login(
            acquisition_id="acq1", site_name="court", credential_id=None,
        )
        assert result.success is True
        assert result.token == "recovered_tok"

    @pytest.mark.asyncio
    async def test_token_acquisition_timeout_no_recovery(self):
        handler = _make_handler()
        credential = MagicMock()
        credential.account = "user1"
        handler.select_credential = AsyncMock(return_value=credential)
        exc = TokenAcquisitionTimeoutError(message="timeout")
        handler._auto_login_service.login_and_get_token = AsyncMock(side_effect=exc)
        handler.try_recover_token_after_timeout = AsyncMock(return_value=None)

        result = await handler.acquire_token_by_login(
            acquisition_id="acq1", site_name="court", credential_id=None,
        )
        assert result.success is False
        assert result.acquisition_method == "auto_login_timeout"


class TestGetCredentialById:
    @pytest.mark.asyncio
    async def test_success(self):
        handler = _make_handler()
        mock_cred = MagicMock()
        with patch("apps.core.dependencies.build_organization_service") as mock_build:
            mock_svc = MagicMock()
            mock_svc.get_credential = AsyncMock(return_value=mock_cred)
            mock_build.return_value = mock_svc
            with patch("apps.core.interfaces.AccountCredentialDTO.from_model", return_value=MagicMock(account="test")):
                result = await handler._get_credential_by_id(1)
                assert result is not None

    @pytest.mark.asyncio
    async def test_exception_returns_none(self):
        handler = _make_handler()
        with patch("apps.core.dependencies.build_organization_service") as mock_build:
            mock_build.side_effect = RuntimeError("db error")
            result = await handler._get_credential_by_id(1)
            assert result is None
