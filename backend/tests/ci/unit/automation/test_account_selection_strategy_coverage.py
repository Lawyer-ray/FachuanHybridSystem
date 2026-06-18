"""Tests for account_selection_strategy — coverage for uncovered branches."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.utils import timezone

from apps.automation.services.token.account_selection_strategy import AccountSelectionStrategy
from apps.core.interfaces import AccountCredentialDTO

# 固定当前时间，避免 recency_score 随真实时间漂移导致 flaky
_FROZEN_NOW = datetime(2026, 6, 15, tzinfo=UTC)


def _make_credential(
    account: str = "test@test.com",
    last_login_success_at: str | None = None,
    login_success_count: int = 0,
    login_failure_count: int = 0,
    site_name: str = "court",
) -> AccountCredentialDTO:
    return AccountCredentialDTO(
        id=1,
        lawyer_id=1,
        lawyer_name="Test",
        site_name=site_name,
        url=None,
        account=account,
        password="pass",
        last_login_success_at=last_login_success_at,
        login_success_count=login_success_count,
        login_failure_count=login_failure_count,
    )


class TestSelectBestAccount:
    def test_empty_raises(self) -> None:
        strategy = AccountSelectionStrategy()
        with pytest.raises(Exception):
            strategy._select_best_account([])

    def test_single_account(self) -> None:
        strategy = AccountSelectionStrategy()
        cred = _make_credential()
        result = strategy._select_best_account([cred])
        assert result.account == "test@test.com"

    def test_prefers_recent_login(self) -> None:
        strategy = AccountSelectionStrategy()
        old_cred = _make_credential(
            account="old@test.com",
            last_login_success_at="2024-01-01T00:00:00Z",
            login_success_count=10,
        )
        new_cred = _make_credential(
            account="new@test.com",
            last_login_success_at="2026-06-14T00:00:00Z",
            login_success_count=1,
        )
        with patch.object(timezone, "now", return_value=_FROZEN_NOW):
            result = strategy._select_best_account([old_cred, new_cred])
        assert result.account == "new@test.com"

    def test_prefers_higher_success_count(self) -> None:
        strategy = AccountSelectionStrategy()
        low_cred = _make_credential(account="low@test.com", login_success_count=2)
        high_cred = _make_credential(account="high@test.com", login_success_count=50)
        result = strategy._select_best_account([low_cred, high_cred])
        assert result.account == "high@test.com"

    def test_new_account_gets_medium_score(self) -> None:
        strategy = AccountSelectionStrategy()
        new_cred = _make_credential(
            account="new@test.com",
            last_login_success_at=None,
            login_success_count=0,
            login_failure_count=0,
        )
        old_cred = _make_credential(
            account="old@test.com",
            last_login_success_at="2024-01-01T00:00:00Z",
            login_success_count=1,
            login_failure_count=10,
        )
        result = strategy._select_best_account([old_cred, new_cred])
        # New account should get decent score from success_rate_score=10
        assert result.account == "new@test.com"

    def test_considers_success_rate(self) -> None:
        strategy = AccountSelectionStrategy()
        # 5 successes, 0 failures = 100% rate
        good_rate = _make_credential(
            account="good@test.com",
            login_success_count=5,
            login_failure_count=0,
        )
        # 5 successes, 5 failures = 50% rate
        bad_rate = _make_credential(
            account="bad@test.com",
            login_success_count=5,
            login_failure_count=5,
        )
        result = strategy._select_best_account([bad_rate, good_rate])
        assert result.account == "good@test.com"


class TestBlacklistManagement:
    def test_add_to_blacklist(self) -> None:
        strategy = AccountSelectionStrategy()
        strategy.add_to_blacklist("bad@test.com")
        assert "bad@test.com" in strategy.get_blacklist()

    def test_add_to_blacklist_no_duplicate(self) -> None:
        strategy = AccountSelectionStrategy()
        strategy.add_to_blacklist("bad@test.com")
        strategy.add_to_blacklist("bad@test.com")
        assert strategy.get_blacklist().count("bad@test.com") == 1

    def test_remove_from_blacklist(self) -> None:
        strategy = AccountSelectionStrategy()
        strategy.add_to_blacklist("bad@test.com")
        strategy.remove_from_blacklist("bad@test.com")
        assert "bad@test.com" not in strategy.get_blacklist()

    def test_remove_nonexistent(self) -> None:
        strategy = AccountSelectionStrategy()
        strategy.remove_from_blacklist("nonexistent@test.com")  # Should not raise

    def test_clear_blacklist(self) -> None:
        strategy = AccountSelectionStrategy()
        strategy.add_to_blacklist("a@test.com")
        strategy.add_to_blacklist("b@test.com")
        strategy.clear_blacklist()
        assert strategy.get_blacklist() == []

    def test_get_blacklist_returns_copy(self) -> None:
        strategy = AccountSelectionStrategy()
        strategy.add_to_blacklist("a@test.com")
        bl = strategy.get_blacklist()
        bl.append("x@test.com")
        assert "x@test.com" not in strategy.get_blacklist()


class TestSelectAccountAsync:
    @pytest.mark.asyncio
    async def test_empty_site_name_raises(self) -> None:
        strategy = AccountSelectionStrategy()
        with patch("apps.automation.services.token.account_selection_strategy.cache_manager") as mock_cache:
            mock_cache.get_cached_blacklist.return_value = []
            with pytest.raises(Exception):
                await strategy.select_account("")

    @pytest.mark.asyncio
    async def test_no_accounts_available(self) -> None:
        strategy = AccountSelectionStrategy()
        with (
            patch("apps.automation.services.token.account_selection_strategy.cache_manager") as mock_cache,
        ):
            mock_cache.get_cached_blacklist.return_value = []
            mock_cache.get_cached_credentials.return_value = []
            result = await strategy.select_account("court")
            assert result is None

    @pytest.mark.asyncio
    async def test_cached_accounts_filtered(self) -> None:
        strategy = AccountSelectionStrategy()
        cred = _make_credential()
        with patch("apps.automation.services.token.account_selection_strategy.cache_manager") as mock_cache:
            mock_cache.get_cached_blacklist.return_value = []
            mock_cache.get_cached_credentials.return_value = [cred]
            result = await strategy.select_account("court")
            assert result is not None
            assert result.account == "test@test.com"

    @pytest.mark.asyncio
    async def test_blacklist_filters_accounts(self) -> None:
        strategy = AccountSelectionStrategy()
        cred = _make_credential(account="bad@test.com")
        with patch("apps.automation.services.token.account_selection_strategy.cache_manager") as mock_cache:
            mock_cache.get_cached_blacklist.return_value = ["bad@test.com"]
            mock_cache.get_cached_credentials.return_value = [cred]
            result = await strategy.select_account("court")
            assert result is None

    @pytest.mark.asyncio
    async def test_exclude_accounts(self) -> None:
        strategy = AccountSelectionStrategy()
        cred = _make_credential(account="excluded@test.com")
        with patch("apps.automation.services.token.account_selection_strategy.cache_manager") as mock_cache:
            mock_cache.get_cached_blacklist.return_value = []
            mock_cache.get_cached_credentials.return_value = [cred]
            result = await strategy.select_account("court", exclude_accounts=["excluded@test.com"])
            assert result is None


class TestUpdateAccountStatistics:
    @pytest.mark.asyncio
    async def test_success_updates_statistics(self) -> None:
        strategy = AccountSelectionStrategy()
        cred = _make_credential()
        with (
            patch("apps.automation.services.token.account_selection_strategy.cache_manager") as mock_cache,
            patch("apps.core.interfaces.ServiceLocator") as mock_locator,
        ):
            org_svc = MagicMock()
            mock_locator.get_organization_service.return_value = org_svc
            org_svc.get_credential_by_account.return_value = cred
            org_svc.get_credential.return_value = cred

            await strategy.update_account_statistics("test@test.com", "court", success=True)
            org_svc.update_login_success.assert_called_once()

    @pytest.mark.asyncio
    async def test_failure_updates_statistics(self) -> None:
        strategy = AccountSelectionStrategy()
        cred = _make_credential()
        with (
            patch("apps.automation.services.token.account_selection_strategy.cache_manager") as mock_cache,
            patch("apps.core.interfaces.ServiceLocator") as mock_locator,
        ):
            org_svc = MagicMock()
            mock_locator.get_organization_service.return_value = org_svc
            org_svc.get_credential_by_account.return_value = cred
            org_svc.get_credential.return_value = cred

            await strategy.update_account_statistics("test@test.com", "court", success=False)
            org_svc.update_login_failure.assert_called_once()

    @pytest.mark.asyncio
    async def test_exception_handled(self) -> None:
        strategy = AccountSelectionStrategy()
        with (
            patch("apps.automation.services.token.account_selection_strategy.cache_manager") as mock_cache,
            patch("apps.core.interfaces.ServiceLocator") as mock_locator,
        ):
            org_svc = MagicMock()
            mock_locator.get_organization_service.return_value = org_svc
            org_svc.get_credential_by_account.side_effect = Exception("db error")
            # Should not raise
            await strategy.update_account_statistics("test@test.com", "court", success=True)
