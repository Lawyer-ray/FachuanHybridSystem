"""Targeted tests for AutoTokenAcquisitionService and AutoLoginService."""

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

from apps.core.exceptions import (
    AutoTokenAcquisitionError,
    NoAvailableAccountError,
    ValidationException,
)

pytestmark = pytest.mark.skipif(not _HAS_LOGIN, reason="court_login plugin not installed")


# ── AutoTokenAcquisitionService ───────────────────────────────────


class TestAutoTokenAcquisitionService:
    def _make_service(self):
        from plugins.court_automation.token.auto_token_acquisition_service import AutoTokenAcquisitionService

        svc = AutoTokenAcquisitionService(
            account_selection_strategy=MagicMock(),
            auto_login_service=MagicMock(),
            token_service=MagicMock(),
        )
        svc.clear_locks()
        return svc

    def test_init_with_defaults(self):
        from plugins.court_automation.token.auto_token_acquisition_service import AutoTokenAcquisitionService

        svc = AutoTokenAcquisitionService()
        assert svc._acquisition_count == 0
        assert svc._success_count == 0
        assert svc._failure_count == 0

    def test_get_statistics(self):
        svc = self._make_service()
        stats = svc.get_statistics()
        assert stats["acquisition_count"] == 0
        assert stats["success_rate"] == 0

    def test_reset_statistics(self):
        svc = self._make_service()
        svc._acquisition_count = 5
        svc._success_count = 3
        svc._failure_count = 2
        svc.reset_statistics()
        assert svc._acquisition_count == 0
        assert svc._success_count == 0
        assert svc._failure_count == 0

    def test_clear_locks(self):
        from plugins.court_automation.token.auto_token_acquisition_service import AutoTokenAcquisitionService

        AutoTokenAcquisitionService._active_acquisitions.add("test")
        AutoTokenAcquisitionService._acquisition_locks["test"] = asyncio.Lock()
        AutoTokenAcquisitionService.clear_locks()
        assert len(AutoTokenAcquisitionService._active_acquisitions) == 0
        assert len(AutoTokenAcquisitionService._acquisition_locks) == 0

    def test_empty_site_name_raises(self):
        svc = self._make_service()
        with pytest.raises(ValidationException, match="网站名称不能为空"):
            asyncio.run(svc.acquire_token_if_needed(""))

    def test_whitespace_site_name_raises(self):
        svc = self._make_service()
        with pytest.raises(ValidationException, match="网站名称不能为空"):
            asyncio.run(svc.acquire_token_if_needed("   "))


# ── AutoLoginService ──────────────────────────────────────────────


class TestAutoLoginService:
    def _make_service(self, usecase=None):
        from plugins.court_automation.token.auto_login_service import AutoLoginService, RetryConfig

        return AutoLoginService(
            retry_config=RetryConfig(max_network_retries=1, max_captcha_retries=1, login_timeout=5.0),
            browser_service=MagicMock(),
            usecase=usecase,
        )

    def test_init_defaults(self):
        from plugins.court_automation.token.auto_login_service import AutoLoginService

        svc = AutoLoginService()
        assert svc.retry_config.max_network_retries == 3
        assert svc._login_attempts == []

    def test_get_login_attempts_empty(self):
        svc = self._make_service()
        assert svc.get_login_attempts() == []

    def test_clear_login_attempts(self):
        svc = self._make_service()
        svc._login_attempts.append(MagicMock())
        svc.clear_login_attempts()
        assert svc._login_attempts == []

    def test_delegates_to_usecase(self):
        mock_usecase = MagicMock()
        mock_usecase.execute = AsyncMock(return_value="test-token")
        svc = self._make_service(usecase=mock_usecase)

        credential = MagicMock()
        credential.account = "test_account"
        result = asyncio.run(svc.login_and_get_token(credential))
        assert result == "test-token"
        mock_usecase.execute.assert_called_once_with(credential)


# ── RetryConfig ───────────────────────────────────────────────────


class TestRetryConfig:
    def test_defaults(self):
        from plugins.court_automation.token.auto_login_service import RetryConfig

        config = RetryConfig()
        assert config.max_network_retries == 3
        assert config.max_captcha_retries == 3
        assert config.network_retry_delay_base == 1.0
        assert config.captcha_retry_delay == 2.0
        assert config.login_timeout == 60.0

    def test_custom_values(self):
        from plugins.court_automation.token.auto_login_service import RetryConfig

        config = RetryConfig(max_network_retries=5, login_timeout=120.0)
        assert config.max_network_retries == 5
        assert config.login_timeout == 120.0


# ── BaoquanTokenProvider ──────────────────────────────────────────


class TestBaoquanTokenProvider:
    def _make_provider(self, **kwargs):
        from plugins.court_automation.preservation_quote.preservation_quote.token_provider import BaoquanTokenProvider

        return BaoquanTokenProvider(**kwargs)

    def test_init_defaults(self):
        provider = self._make_provider()
        assert provider._baoquan_token_service is None

    def test_with_token_service_returns_token(self):
        mock_token_service = MagicMock()
        mock_token_service.get_token.return_value = "valid-token-123"
        provider = self._make_provider(token_service=mock_token_service)

        result = asyncio.run(provider.get_token())
        assert result == "valid-token-123"
        mock_token_service.get_token.assert_called_once_with(site_name="court_zxfw", account=None)

    def test_with_token_service_no_token_raises(self):
        mock_token_service = MagicMock()
        mock_token_service.get_token.return_value = None
        provider = self._make_provider(token_service=mock_token_service)

        from plugins.court_automation.preservation_quote.exceptions import TokenError

        with pytest.raises(TokenError, match="Token 不存在"):
            asyncio.run(provider.get_token())

    def test_with_baoquan_token_service(self):
        mock_baoquan = MagicMock()
        mock_baoquan.get_valid_baoquan_token = AsyncMock(return_value="baoquan-token")
        provider = self._make_provider(baoquan_token_service=mock_baoquan)

        result = asyncio.run(provider.get_token(credential_id=42))
        assert result == "baoquan-token"

    def test_with_auto_token_service(self):
        mock_auto = MagicMock()
        mock_auto.acquire_token_if_needed = AsyncMock(return_value="auto-token")
        mock_baoquan = MagicMock()
        mock_baoquan.get_valid_baoquan_token = AsyncMock(return_value="baoquan-token")
        provider = self._make_provider(
            auto_token_service=mock_auto,
            baoquan_token_service=mock_baoquan,
        )

        result = asyncio.run(provider.get_token(credential_id=42))
        assert result == "baoquan-token"
        mock_auto.acquire_token_if_needed.assert_called_once()

    def test_baoquan_failure_raises_token_error(self):
        mock_baoquan = MagicMock()
        mock_baoquan.get_valid_baoquan_token = AsyncMock(side_effect=Exception("API error"))
        provider = self._make_provider(baoquan_token_service=mock_baoquan)

        from plugins.court_automation.preservation_quote.exceptions import TokenError

        with pytest.raises(TokenError, match="保全系统 Token 获取失败"):
            asyncio.run(provider.get_token())
