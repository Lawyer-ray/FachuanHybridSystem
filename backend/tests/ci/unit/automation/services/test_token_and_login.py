"""Tests for token service and auto_login_usecase."""

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:
    from plugins import has_court_login_plugin
    _HAS_LOGIN = has_court_login_plugin()
except ImportError:
    _HAS_LOGIN = False

pytestmark = pytest.mark.skipif(not _HAS_LOGIN, reason="court_login plugin not installed")


# ============================================================
# token_service.py - TokenService._get_cache_key
# ============================================================

class TestTokenServiceCacheKey:
    def test_get_cache_key(self):
        from apps.automation.services.scraper.core.token_service import TokenService
        svc = TokenService.__new__(TokenService)
        with patch("apps.core.infrastructure.cache.CacheKeys.court_token") as mock_ck:
            mock_ck.return_value = "court_token:court_zxfw:user1"
            result = svc._get_cache_key("court_zxfw", "user1")
            assert result == "court_token:court_zxfw:user1"
            mock_ck.assert_called_once_with(site_name="court_zxfw", account="user1")


# ============================================================
# TokenServiceAdapter
# ============================================================

class TestTokenServiceAdapter:
    def test_service_property_lazy_load(self):
        from apps.automation.services.scraper.core.token_service import TokenService, TokenServiceAdapter
        adapter = TokenServiceAdapter.__new__(TokenServiceAdapter)
        adapter._service = None
        with patch("apps.automation.services.scraper.core.token_service.TokenService") as MockTS:
            mock_instance = MagicMock()
            MockTS.return_value = mock_instance
            result = adapter.service
            assert result is mock_instance

    def test_service_property_already_set(self):
        from apps.automation.services.scraper.core.token_service import TokenService, TokenServiceAdapter
        adapter = TokenServiceAdapter.__new__(TokenServiceAdapter)
        mock_svc = MagicMock()
        adapter._service = mock_svc
        assert adapter.service is mock_svc


# ============================================================
# auto_login_usecase.py - RetryConfig
# ============================================================

class TestRetryConfig:
    def test_default_values(self):
        from apps.automation.usecases.token.auto_login_usecase import RetryConfig
        cfg = RetryConfig()
        assert cfg.max_network_retries == 3
        assert cfg.max_captcha_retries == 3
        assert cfg.network_retry_delay_base == 1.0
        assert cfg.captcha_retry_delay == 2.0
        assert cfg.login_timeout == 60.0

    def test_custom_values(self):
        from apps.automation.usecases.token.auto_login_usecase import RetryConfig
        cfg = RetryConfig(max_network_retries=5, login_timeout=120.0)
        assert cfg.max_network_retries == 5
        assert cfg.login_timeout == 120.0


class TestAutoLoginUsecase:
    def _make_usecase(self):
        from apps.automation.usecases.token.auto_login_usecase import AutoLoginUsecase, RetryConfig
        return AutoLoginUsecase(
            retry_config=RetryConfig(max_network_retries=1, max_captcha_retries=1, login_timeout=5.0),
            browser_context_factory=MagicMock(),
            login_gateway=MagicMock(),
            sync_login_attempt=None,
            sleep=AsyncMock(),
            time_provider=lambda: 100.0,
        )

    def test_get_login_attempts_empty(self):
        uc = self._make_usecase()
        assert uc.get_login_attempts() == []

    def test_clear_login_attempts(self):
        uc = self._make_usecase()
        uc._login_attempts.append(MagicMock())
        uc.clear_login_attempts()
        assert uc.get_login_attempts() == []
