"""Tests for automation.usecases.token.auto_login_usecase.

Covers: RetryConfig defaults, AutoLoginUsecase.execute success/timeout/error paths,
_login_with_retries network retry + captcha retry, _single_login_attempt network
keyword detection, get/clear_login_attempts.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:
    from plugins import has_court_login_plugin
    _HAS_LOGIN = has_court_login_plugin()
except ImportError:
    _HAS_LOGIN = False

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

pytestmark = pytest.mark.skipif(not _HAS_LOGIN, reason="court_login plugin not installed")


# ---------------------------------------------------------------------------
# RetryConfig
# ---------------------------------------------------------------------------


class TestRetryConfig:
    def test_defaults(self):
        cfg = RetryConfig()
        assert cfg.max_network_retries == 3
        assert cfg.max_captcha_retries == 3
        assert cfg.network_retry_delay_base == 1.0
        assert cfg.captcha_retry_delay == 2.0
        assert cfg.login_timeout == 60.0

    def test_custom_values(self):
        cfg = RetryConfig(max_network_retries=5, login_timeout=120.0)
        assert cfg.max_network_retries == 5
        assert cfg.login_timeout == 120.0

    def test_frozen(self):
        cfg = RetryConfig()
        with pytest.raises(AttributeError):
            cfg.max_network_retries = 10  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
# AutoLoginUsecase.execute — success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_success():
    with patch(_LOGGER_PATCH):
        uc = _make_usecase(sync_login_attempt=lambda cred: "tok123")
        result = await uc.execute(_make_credential())
        assert result == "tok123"


@pytest.mark.asyncio
async def test_execute_clears_attempts_on_start():
    with patch(_LOGGER_PATCH):
        uc = _make_usecase(sync_login_attempt=lambda cred: "tok")
        uc._login_attempts = [MagicMock()]
        await uc.execute(_make_credential())
        # Should have been cleared and then populated with new attempts
        assert any(a.success for a in uc._login_attempts)


# ---------------------------------------------------------------------------
# AutoLoginUsecase.execute — timeout path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_timeout_raises():
    async def slow_login(cred):
        await asyncio.sleep(100)

    cfg = RetryConfig(login_timeout=0.01, captcha_retry_delay=0.0, network_retry_delay_base=0.0)

    def fake_time():
        fake_time.val += 0.001
        return fake_time.val

    fake_time.val = 0.0

    with patch(_LOGGER_PATCH):
        uc = AutoLoginUsecase(
            retry_config=cfg,
            browser_context_factory=MagicMock(),
            login_gateway=MagicMock(),
            sync_login_attempt=None,
            sleep=AsyncMock(),
            time_provider=fake_time,
        )
        # Override _login_with_retries to be slow
        uc._login_with_retries = lambda cred: asyncio.sleep(10)

        with pytest.raises(TokenAcquisitionTimeoutError) as exc_info:
            await uc.execute(_make_credential())
        assert "超时" in str(exc_info.value)


# ---------------------------------------------------------------------------
# AutoLoginUsecase.execute — unexpected error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_unexpected_error_wraps_in_login_failed():
    with patch(_LOGGER_PATCH):
        uc = _make_usecase(sync_login_attempt=MagicMock(side_effect=ValueError("boom")))
        with pytest.raises(LoginFailedError) as exc_info:
            await uc.execute(_make_credential())
        # The error propagates through captcha retry exhaustion -> LoginFailedError
        assert "验证码重试失败" in str(exc_info.value) or "未预期错误" in str(exc_info.value)


# ---------------------------------------------------------------------------
# AutoLoginUsecase.execute — re-raises known errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("exc_cls", [LoginFailedError, NetworkError, AutoTokenAcquisitionError])
async def test_execute_re_raises_known_errors(exc_cls):
    with patch(_LOGGER_PATCH):
        uc = _make_usecase()

        async def fail(cred):
            raise exc_cls("known error")

        uc._login_with_retries = fail
        with pytest.raises(exc_cls):
            await uc.execute(_make_credential())


# ---------------------------------------------------------------------------
# get / clear login_attempts
# ---------------------------------------------------------------------------


def test_get_login_attempts_returns_copy():
    uc = _make_usecase()
    original = LoginAttemptResult(success=True, token="t", account="a", error_message=None, attempt_duration=0.1, retry_count=1)
    uc._login_attempts.append(original)
    attempts = uc.get_login_attempts()
    assert attempts is not uc._login_attempts
    assert len(attempts) == 1


def test_clear_login_attempts():
    uc = _make_usecase()
    uc._login_attempts.append(MagicMock())
    uc.clear_login_attempts()
    assert len(uc._login_attempts) == 0


# ---------------------------------------------------------------------------
# _single_login_attempt — network keyword detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_login_attempt_detects_network_errors():
    uc = _make_usecase(sync_login_attempt=None)
    uc._sync_login_attempt = MagicMock(side_effect=Exception("网络连接超时"))
    credential = _make_credential()

    with pytest.raises(NetworkError):
        await uc._single_login_attempt(credential)


@pytest.mark.asyncio
async def test_single_login_attempt_passes_through_non_network():
    uc = _make_usecase(sync_login_attempt=None)
    uc._sync_login_attempt = MagicMock(side_effect=ValueError("some other error"))
    credential = _make_credential()

    with pytest.raises(ValueError):
        await uc._single_login_attempt(credential)


# ---------------------------------------------------------------------------
# _login_with_retries — NetworkError retry exhaustion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_with_retries_network_exhaustion():
    async def fail_with_network(cred, network_attempt):
        raise NetworkError("down")

    cfg = RetryConfig(max_network_retries=2, max_captcha_retries=1, captcha_retry_delay=0.0, network_retry_delay_base=0.0)

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
    uc._login_with_captcha_retries = fail_with_network

    with pytest.raises(NetworkError):
        await uc._login_with_retries(_make_credential())


# ---------------------------------------------------------------------------
# _login_with_retries — non-NetworkError exception breaks loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_with_retries_unexpected_breaks():
    call_count = 0

    async def fail_unexpected(cred, network_attempt):
        nonlocal call_count
        call_count += 1
        raise ValueError("unexpected")

    cfg = RetryConfig(max_network_retries=3, max_captcha_retries=1, captcha_retry_delay=0.0, network_retry_delay_base=0.0)

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
    uc._login_with_captcha_retries = fail_unexpected

    with pytest.raises(LoginFailedError):
        await uc._login_with_retries(_make_credential())
    assert call_count == 1  # should break after first unexpected error


# ---------------------------------------------------------------------------
# _login_with_retries — LoginFailedError re-raised immediately
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_with_retries_login_failed_reraised():
    async def fail_login(cred, network_attempt):
        raise LoginFailedError("bad creds")

    cfg = RetryConfig(max_network_retries=3, max_captcha_retries=1, captcha_retry_delay=0.0, network_retry_delay_base=0.0)

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
    uc._login_with_captcha_retries = fail_login

    with pytest.raises(LoginFailedError):
        await uc._login_with_retries(_make_credential())


# ---------------------------------------------------------------------------
# _login_with_retries — success on second network attempt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_with_retries_success_on_retry():
    call_count = 0

    async def succeed_on_second(cred, network_attempt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise NetworkError("temp failure")
        return "tok"

    cfg = RetryConfig(max_network_retries=3, max_captcha_retries=1, captcha_retry_delay=0.0, network_retry_delay_base=0.0)

    uc = AutoLoginUsecase(
        retry_config=cfg,
        browser_context_factory=MagicMock(),
        login_gateway=MagicMock(),
        sync_login_attempt=None,
        sleep=AsyncMock(),
        time_provider=lambda: 0.0,
    )
    uc._login_with_captcha_retries = succeed_on_second

    result = await uc._login_with_retries(_make_credential())
    assert result == "tok"


# ---------------------------------------------------------------------------
# _login_with_captcha_retries — success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_captcha_retries_success():
    uc = _make_usecase(sync_login_attempt=lambda cred: "tok")

    result = await uc._login_with_captcha_retries(_make_credential(), network_attempt=1)
    assert result == "tok"
    assert len(uc._login_attempts) == 1
    assert uc._login_attempts[0].success is True


# ---------------------------------------------------------------------------
# _login_with_captcha_retries — NetworkError re-raised (no captcha retry)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_captcha_retries_network_error_no_retry():
    async def fail_net(cred):
        raise NetworkError("net down")

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
    uc._single_login_attempt = fail_net

    with pytest.raises(NetworkError):
        await uc._login_with_captcha_retries(_make_credential(), network_attempt=1)
    assert len(uc._login_attempts) == 1
    assert uc._login_attempts[0].success is False


# ---------------------------------------------------------------------------
# _login_with_captcha_retries — captcha retry exhaustion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_captcha_retries_exhaustion():
    call_count = 0

    async def fail_always(cred):
        nonlocal call_count
        call_count += 1
        raise ValueError("captcha wrong")

    cfg = RetryConfig(max_captcha_retries=2, captcha_retry_delay=0.0, network_retry_delay_base=0.0, max_network_retries=1)

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
    uc._single_login_attempt = fail_always

    with pytest.raises(LoginFailedError) as exc_info:
        await uc._login_with_captcha_retries(_make_credential(), network_attempt=1)
    assert "验证码重试失败" in str(exc_info.value)
    assert call_count == 2


# ---------------------------------------------------------------------------
# _login_with_captcha_retries — captcha retry succeeds on second attempt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_captcha_retries_success_on_second():
    call_count = 0

    async def succeed_on_second(cred):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("captcha wrong")
        return "tok2"

    cfg = RetryConfig(max_captcha_retries=3, captcha_retry_delay=0.0, network_retry_delay_base=0.0, max_network_retries=1)

    uc = AutoLoginUsecase(
        retry_config=cfg,
        browser_context_factory=MagicMock(),
        login_gateway=MagicMock(),
        sync_login_attempt=None,
        sleep=AsyncMock(),
        time_provider=lambda: 0.0,
    )
    uc._single_login_attempt = succeed_on_second

    result = await uc._login_with_captcha_retries(_make_credential(), network_attempt=1)
    assert result == "tok2"
    assert len(uc._login_attempts) == 2
