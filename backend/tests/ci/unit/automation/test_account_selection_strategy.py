"""Tests for AccountSelectionStrategy covering blacklist, sorting, and validation."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from plugins.court_automation.token.account_selection_strategy import AccountSelectionStrategy
from apps.core.exceptions import ValidationException
from apps.core.interfaces import AccountCredentialDTO


@pytest.fixture
def strategy():
    return AccountSelectionStrategy(blacklist_duration_hours=1)


# ── blacklist management ──


class TestBlacklistManagement:
    def test_add_to_blacklist(self, strategy):
        with patch("plugins.court_automation.token.account_selection_strategy.cache_manager"):
            strategy.add_to_blacklist("user1")
        assert "user1" in strategy.get_blacklist()

    def test_add_to_blacklist_no_duplicate(self, strategy):
        with patch("plugins.court_automation.token.account_selection_strategy.cache_manager"):
            strategy.add_to_blacklist("user1")
            strategy.add_to_blacklist("user1")
        assert strategy.get_blacklist().count("user1") == 1

    def test_remove_from_blacklist(self, strategy):
        with patch("plugins.court_automation.token.account_selection_strategy.cache_manager"):
            strategy.add_to_blacklist("user1")
            strategy.remove_from_blacklist("user1")
        assert "user1" not in strategy.get_blacklist()

    def test_remove_nonexistent_from_blacklist(self, strategy):
        with patch("plugins.court_automation.token.account_selection_strategy.cache_manager"):
            strategy.remove_from_blacklist("nonexistent")
        assert strategy.get_blacklist() == []

    def test_clear_blacklist(self, strategy):
        with patch("plugins.court_automation.token.account_selection_strategy.cache_manager"):
            strategy.add_to_blacklist("user1")
            strategy.add_to_blacklist("user2")
            strategy.clear_blacklist()
        assert strategy.get_blacklist() == []

    def test_get_blacklist_returns_copy(self, strategy):
        with patch("plugins.court_automation.token.account_selection_strategy.cache_manager"):
            strategy.add_to_blacklist("user1")
        bl = strategy.get_blacklist()
        bl.append("user2")
        assert "user2" not in strategy.get_blacklist()


# ── _select_best_account ──


def _make_dto(
    account: str = "user1",
    last_login_success_at: str | None = None,
    login_success_count: int = 0,
    login_failure_count: int = 0,
) -> AccountCredentialDTO:
    return AccountCredentialDTO(
        id=1,
        lawyer_id=1,
        lawyer_name="Test Lawyer",
        site_name="test",
        url="https://example.com",
        account=account,
        password="test-password",
        last_login_success_at=last_login_success_at,
        login_success_count=login_success_count,
        login_failure_count=login_failure_count,
    )


class TestSelectBestAccount:
    def test_single_account(self, strategy):
        acc = _make_dto(account="only_one")
        result = strategy._select_best_account([acc])
        assert result.account == "only_one"

    def test_prefers_recent_success(self, strategy):
        recent = _make_dto(
            account="recent",
            last_login_success_at=(timezone.now() - timedelta(hours=1)).isoformat(),
            login_success_count=5,
        )
        old = _make_dto(
            account="old",
            last_login_success_at=(timezone.now() - timedelta(hours=48)).isoformat(),
            login_success_count=5,
        )
        result = strategy._select_best_account([old, recent])
        assert result.account == "recent"

    def test_prefers_more_successes(self, strategy):
        high = _make_dto(account="high", login_success_count=20)
        low = _make_dto(account="low", login_success_count=1)
        result = strategy._select_best_account([low, high])
        assert result.account == "high"

    def test_no_success_accounts(self, strategy):
        acc = _make_dto(account="never", login_success_count=0, login_failure_count=5)
        result = strategy._select_best_account([acc])
        assert result.account == "never"

    def test_empty_accounts_raises(self, strategy):
        with pytest.raises(ValidationException, match="没有可用账号"):
            strategy._select_best_account([])

    def test_success_rate_scoring(self, strategy):
        # Account with high success rate should be preferred
        high_rate = _make_dto(
            account="high_rate",
            login_success_count=10,
            login_failure_count=0,
        )
        low_rate = _make_dto(
            account="low_rate",
            login_success_count=10,
            login_failure_count=10,
        )
        result = strategy._select_best_account([low_rate, high_rate])
        assert result.account == "high_rate"


# ── select_account ──


class TestSelectAccount:
    def test_empty_site_name_raises(self, strategy):
        with pytest.raises(ValidationException, match="网站名称不能为空"):
            asyncio.run(strategy.select_account(""))

    def test_no_accounts_returns_none(self, strategy):
        with patch(
            "plugins.court_automation.token.account_selection_strategy.cache_manager"
        ) as mock_cache, \
             patch.object(strategy, "_get_available_accounts", return_value=[]):
            mock_cache.get_cached_blacklist.return_value = None
            mock_cache.get_cached_credentials.return_value = None
            result = asyncio.run(strategy.select_account("test_site"))
        assert result is None

    def test_cached_blacklist_loaded(self, strategy):
        with patch(
            "plugins.court_automation.token.account_selection_strategy.cache_manager"
        ) as mock_cache:
            mock_cache.get_cached_blacklist.return_value = ["blocked_user"]
            mock_cache.get_cached_credentials.return_value = []
            result = asyncio.run(strategy.select_account("test_site"))
        assert "blocked_user" in strategy._blacklist

    def test_cached_credentials_used(self, strategy):
        acc = _make_dto(account="cached_user")
        with patch(
            "plugins.court_automation.token.account_selection_strategy.cache_manager"
        ) as mock_cache:
            mock_cache.get_cached_blacklist.return_value = None
            mock_cache.get_cached_credentials.return_value = [acc]
            result = asyncio.run(strategy.select_account("test_site"))
        assert result is not None
        assert result.account == "cached_user"

    def test_excludes_blacklisted_from_cache(self, strategy):
        acc1 = _make_dto(account="good_user")
        acc2 = _make_dto(account="bad_user", login_success_count=10)
        with patch(
            "plugins.court_automation.token.account_selection_strategy.cache_manager"
        ) as mock_cache:
            mock_cache.get_cached_blacklist.return_value = ["bad_user"]
            mock_cache.get_cached_credentials.return_value = [acc1, acc2]
            result = asyncio.run(strategy.select_account("test_site", exclude_accounts=[]))
        assert result is not None
        assert result.account == "good_user"
