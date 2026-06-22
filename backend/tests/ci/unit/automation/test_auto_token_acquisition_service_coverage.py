"""Tests for auto_token_acquisition_service uncovered branches."""

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

pytestmark = pytest.mark.skipif(not _HAS_LOGIN, reason="court_login plugin not installed")


@pytest.fixture
def mock_service():
    """Create a service with mocked dependencies."""
    from plugins.court_automation.token.auto_token_acquisition_service import AutoTokenAcquisitionService
    from plugins.court_automation.token.concurrency_optimizer import ConcurrencyConfig

    strategy = AsyncMock()
    login_svc = AsyncMock()
    token_svc = AsyncMock()

    svc = AutoTokenAcquisitionService(
        account_selection_strategy=strategy,
        auto_login_service=login_svc,
        token_service=token_svc,
        concurrency_config=ConcurrencyConfig(acquisition_timeout=5.0),
    )
    svc.clear_locks()
    yield svc, strategy, login_svc, token_svc
    svc.clear_locks()


class TestGetStatistics:
    """Cover get_statistics and reset_statistics."""

    def test_initial_statistics(self, mock_service):
        svc, *_ = mock_service
        stats = svc.get_statistics()
        assert stats["acquisition_count"] == 0
        assert stats["success_count"] == 0
        assert stats["failure_count"] == 0
        assert stats["success_rate"] == 0

    def test_statistics_with_counts(self, mock_service):
        svc, *_ = mock_service
        svc._acquisition_count = 10
        svc._success_count = 7
        svc._failure_count = 3
        stats = svc.get_statistics()
        assert stats["success_rate"] == 0.7

    def test_reset_statistics(self, mock_service):
        svc, *_ = mock_service
        svc._acquisition_count = 5
        svc._success_count = 3
        svc._failure_count = 2
        svc.reset_statistics()
        assert svc._acquisition_count == 0
        assert svc._success_count == 0
        assert svc._failure_count == 0


class TestClearLocks:
    """Cover clear_locks class method."""

    def test_clear_locks(self, mock_service):
        svc, *_ = mock_service
        svc._active_acquisitions.add("test")
        svc._acquisition_locks["test"] = asyncio.Lock()
        svc.clear_locks()
        assert len(svc._active_acquisitions) == 0
        assert len(svc._acquisition_locks) == 0


class TestLazyProperties:
    """Cover lazy-loaded properties."""

    @patch("apps.core.dependencies.build_account_selection_strategy", return_value="strat")
    @patch("apps.core.dependencies.build_auto_login_service", return_value="login")
    @patch("apps.core.dependencies.build_token_service", return_value="token")
    def test_lazy_load_all(self, mock_token, mock_login, mock_strat):
        from plugins.court_automation.token.auto_token_acquisition_service import AutoTokenAcquisitionService

        svc = AutoTokenAcquisitionService()
        assert svc.account_selection_strategy == "strat"
        assert svc.auto_login_service == "login"
        assert svc.token_service == "token"


class TestAcquireTokenIfNeededValidation:
    """Cover validation branch."""

    @pytest.mark.asyncio
    async def test_empty_site_name_raises(self, mock_service):
        svc, *_ = mock_service
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException, match="网站名称不能为空"):
            await svc.acquire_token_if_needed("")

    @pytest.mark.asyncio
    async def test_whitespace_site_name_raises(self, mock_service):
        svc, *_ = mock_service
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException, match="网站名称不能为空"):
            await svc.acquire_token_if_needed("   ")


class TestGetAcquisitionLock:
    """Cover _get_acquisition_lock."""

    @pytest.mark.asyncio
    async def test_creates_new_lock(self, mock_service):
        svc, *_ = mock_service
        lock = await svc._get_acquisition_lock("test_site")
        assert isinstance(lock, asyncio.Lock)
        assert "test_site" in svc._acquisition_locks

    @pytest.mark.asyncio
    async def test_returns_existing_lock(self, mock_service):
        svc, *_ = mock_service
        lock1 = await svc._get_acquisition_lock("test_site")
        lock2 = await svc._get_acquisition_lock("test_site")
        assert lock1 is lock2


class TestCheckAnyValidToken:
    """Cover _check_any_valid_token."""

    @pytest.mark.asyncio
    async def test_returns_token_when_found(self, mock_service):
        svc, strategy, _, token_svc = mock_service
        cred = MagicMock()
        cred.account = "test_account"
        strategy.select_account.return_value = cred
        token_svc.get_token_internal.return_value = "valid_token"

        result = await svc._check_any_valid_token("test_site")
        assert result == "valid_token"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_accounts(self, mock_service):
        svc, strategy, _, _ = mock_service
        strategy.select_account.return_value = None
        result = await svc._check_any_valid_token("test_site")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_token(self, mock_service):
        svc, strategy, _, token_svc = mock_service
        cred = MagicMock()
        cred.account = "test_account"
        strategy.select_account.return_value = cred
        token_svc.get_token_internal.return_value = None
        result = await svc._check_any_valid_token("test_site")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self, mock_service):
        svc, strategy, _, _ = mock_service
        strategy.select_account.side_effect = Exception("boom")
        result = await svc._check_any_valid_token("test_site")
        assert result is None


class TestGetCachedOrDbToken:
    """Cover _get_cached_or_db_token."""

    @pytest.mark.asyncio
    async def test_returns_cached_token(self, mock_service):
        svc, _, _, _ = mock_service
        with patch("plugins.court_automation.token.auto_token_acquisition_service.cache_manager") as cache:
            cache.get_cached_token.return_value = "cached"
            result = await svc._get_cached_or_db_token("site", "account")
            assert result == "cached"

    @pytest.mark.asyncio
    async def test_falls_back_to_db(self, mock_service):
        svc, _, _, token_svc = mock_service
        with patch("plugins.court_automation.token.auto_token_acquisition_service.cache_manager") as cache:
            cache.get_cached_token.return_value = None
            token_svc.get_token_internal.return_value = "db_token"
            result = await svc._get_cached_or_db_token("site", "account")
            assert result == "db_token"
            cache.cache_token.assert_called_once_with("site", "account", "db_token")

    @pytest.mark.asyncio
    async def test_returns_none_when_nothing_found(self, mock_service):
        svc, _, _, token_svc = mock_service
        with patch("plugins.court_automation.token.auto_token_acquisition_service.cache_manager") as cache:
            cache.get_cached_token.return_value = None
            token_svc.get_token_internal.return_value = None
            result = await svc._get_cached_or_db_token("site", "account")
            assert result is None


class TestResolveCredentialAndToken:
    """Cover _resolve_credential_and_token."""

    @pytest.mark.asyncio
    async def test_with_credential_id_existing_token(self, mock_service):
        svc, _, _, token_svc = mock_service
        with patch.object(svc, "_get_login_handler") as mock_handler:
            mock_login = MagicMock()
            cred = MagicMock()
            cred.account = "test_account"
            mock_login._get_credential_by_id = AsyncMock(return_value=cred)
            mock_handler.return_value = mock_login

            with patch.object(svc, "_get_cached_or_db_token", return_value="existing_token"):
                cred_result, token = await svc._resolve_credential_and_token("site", 1, "aid")
                assert token == "existing_token"
                assert cred_result is cred

    @pytest.mark.asyncio
    async def test_with_credential_id_no_token(self, mock_service):
        svc, _, _, token_svc = mock_service
        with patch.object(svc, "_get_login_handler") as mock_handler:
            mock_login = MagicMock()
            cred = MagicMock()
            cred.account = "test_account"
            mock_login._get_credential_by_id = AsyncMock(return_value=cred)
            mock_handler.return_value = mock_login

            with patch.object(svc, "_get_cached_or_db_token", return_value=None):
                cred_result, token = await svc._resolve_credential_and_token("site", 1, "aid")
                assert token is None

    @pytest.mark.asyncio
    async def test_with_credential_id_invalid_raises(self, mock_service):
        svc, _, _, _ = mock_service
        with patch.object(svc, "_get_login_handler") as mock_handler:
            mock_login = MagicMock()
            mock_login._get_credential_by_id = AsyncMock(return_value=None)
            mock_handler.return_value = mock_login

            from apps.core.exceptions import ValidationException
            with pytest.raises(ValidationException, match="无效的凭证ID"):
                await svc._resolve_credential_and_token("site", 999, "aid")

    @pytest.mark.asyncio
    async def test_auto_select_existing_token(self, mock_service):
        svc, strategy, _, _ = mock_service
        cred = MagicMock()
        cred.account = "auto_account"
        strategy.select_account.return_value = cred

        with patch.object(svc, "_get_cached_or_db_token", return_value="auto_token"):
            cred_result, token = await svc._resolve_credential_and_token("site", None, "aid")
            assert token == "auto_token"

    @pytest.mark.asyncio
    async def test_auto_select_no_account_raises(self, mock_service):
        svc, strategy, _, _ = mock_service
        strategy.select_account.return_value = None

        from apps.core.exceptions import NoAvailableAccountError
        with pytest.raises(NoAvailableAccountError):
            await svc._resolve_credential_and_token("site", None, "aid")


class TestGetLoginHandler:
    """Cover _get_login_handler."""

    def test_creates_login_handler(self, mock_service):
        svc, *_ = mock_service
        with patch("plugins.court_automation.token._login_handler.LoginHandler") as mock_cls:
            handler = svc._get_login_handler()
            mock_cls.assert_called_once()
