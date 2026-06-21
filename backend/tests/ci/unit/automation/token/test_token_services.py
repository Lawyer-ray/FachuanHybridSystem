"""Token 服务测试（缓存管理、账号选择策略）。"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from plugins.court_automation.token.cache_manager import TokenCacheManager
from plugins.court_automation.token.account_selection_strategy import AccountSelectionStrategy


class TestTokenCacheManager:
    """TokenCacheManager 测试。"""

    def setup_method(self) -> None:
        self.manager = TokenCacheManager()

    def test_get_token_cache_key(self) -> None:
        """生成 Token 缓存键。"""
        key = self.manager._get_token_cache_key("court_zxfw", "test_account")
        assert "auto_token" in key
        assert "token" in key
        assert "court_zxfw" in key
        # account 应该被哈希化
        assert "test_account" not in key

    def test_get_token_cache_key_special_chars(self) -> None:
        """site_name 中的特殊字符被替换。"""
        key = self.manager._get_token_cache_key("court/zxfw", "account")
        assert "/" not in key

    def test_get_credentials_cache_key(self) -> None:
        """生成凭证缓存键。"""
        key = self.manager._get_credentials_cache_key("court_zxfw")
        assert "credentials" in key
        assert "court_zxfw" in key

    def test_get_account_stats_cache_key(self) -> None:
        """生成账号统计缓存键。"""
        key = self.manager._get_account_stats_cache_key("account1", "site1")
        assert "account_stats" in key
        assert "account1" in key
        assert "site1" in key

    @patch("plugins.court_automation.token.cache_manager.cache")
    @patch("plugins.court_automation.token.cache_manager.performance_monitor")
    @patch("plugins.court_automation.token.cache_manager.record_cache_access")
    def test_get_cached_token_hit(self, mock_record, mock_perf, mock_cache) -> None:
        """缓存命中。"""
        mock_cache.get.return_value = {"token": "test_token_123"}
        result = self.manager.get_cached_token("site1", "account1")
        assert result == "test_token_123"

    @patch("plugins.court_automation.token.cache_manager.cache")
    @patch("plugins.court_automation.token.cache_manager.performance_monitor")
    @patch("plugins.court_automation.token.cache_manager.record_cache_access")
    def test_get_cached_token_miss(self, mock_record, mock_perf, mock_cache) -> None:
        """缓存未命中。"""
        mock_cache.get.return_value = None
        result = self.manager.get_cached_token("site1", "account1")
        assert result is None

    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_get_cached_token_exception(self, mock_cache) -> None:
        """缓存异常返回 None。"""
        mock_cache.get.side_effect = Exception("cache error")
        result = self.manager.get_cached_token("site1", "account1")
        assert result is None

    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_cache_token(self, mock_cache) -> None:
        """缓存 Token。"""
        self.manager.cache_token("site1", "account1", "test_token")
        mock_cache.set.assert_called_once()

    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_invalidate_token_cache(self, mock_cache) -> None:
        """使 Token 缓存失效。"""
        self.manager.invalidate_token_cache("site1", "account1")
        mock_cache.delete.assert_called_once()

    @patch("plugins.court_automation.token.cache_manager.cache")
    @patch("plugins.court_automation.token.cache_manager.performance_monitor")
    def test_get_cached_credentials_hit(self, mock_perf, mock_cache) -> None:
        """凭证缓存命中。"""
        mock_cache.get.return_value = [
            {"id": 1, "lawyer_id": 1, "lawyer_name": "test", "site_name": "site1",
             "url": None, "account": "test", "password": "",
             "login_success_count": 0, "login_failure_count": 0,
             "last_login_success_at": None}
        ]
        result = self.manager.get_cached_credentials("site1")
        assert result is not None
        assert len(result) == 1

    @patch("plugins.court_automation.token.cache_manager.cache")
    @patch("plugins.court_automation.token.cache_manager.performance_monitor")
    def test_get_cached_credentials_miss(self, mock_perf, mock_cache) -> None:
        """凭证缓存未命中。"""
        mock_cache.get.return_value = None
        result = self.manager.get_cached_credentials("site1")
        assert result is None

    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_cache_blacklist(self, mock_cache) -> None:
        """缓存黑名单。"""
        self.manager.cache_blacklist(["account1", "account2"])
        mock_cache.set.assert_called_once()

    @patch("plugins.court_automation.token.cache_manager.cache")
    @patch("plugins.court_automation.token.cache_manager.performance_monitor")
    def test_get_cached_blacklist_hit(self, mock_perf, mock_cache) -> None:
        """黑名单缓存命中。"""
        mock_cache.get.return_value = ["account1"]
        result = self.manager.get_cached_blacklist()
        assert result == ["account1"]

    @patch("plugins.court_automation.token.cache_manager.cache")
    @patch("plugins.court_automation.token.cache_manager.performance_monitor")
    def test_get_cached_blacklist_miss(self, mock_perf, mock_cache) -> None:
        """黑名单缓存未命中。"""
        mock_cache.get.return_value = None
        result = self.manager.get_cached_blacklist()
        assert result is None

    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_invalidate_blacklist_cache(self, mock_cache) -> None:
        """使黑名单缓存失效。"""
        self.manager.invalidate_blacklist_cache()
        mock_cache.delete.assert_called_once()

    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_invalidate_site_cache(self, mock_cache) -> None:
        """定向失效站点缓存。"""
        self.manager.invalidate_site_cache("site1", accounts=["acc1", "acc2"])
        # 应该调用 delete 多次（credentials + 2 accounts）
        assert mock_cache.delete.call_count >= 3

    def test_get_cache_statistics(self) -> None:
        """获取缓存统计。"""
        stats = self.manager.get_cache_statistics()
        assert "cache_backend" in stats


class TestAccountSelectionStrategy:
    """AccountSelectionStrategy 测试。"""

    def setup_method(self) -> None:
        self.strategy = AccountSelectionStrategy(blacklist_duration_hours=1)

    def test_blacklist_add_remove(self) -> None:
        """添加和移除黑名单。"""
        with patch("plugins.court_automation.token.account_selection_strategy.cache_manager") as mock_cm:
            mock_cm.cache_blacklist = MagicMock()
            mock_cm.invalidate_blacklist_cache = MagicMock()

            self.strategy.add_to_blacklist("account1")
            assert "account1" in self.strategy.get_blacklist()

            self.strategy.remove_from_blacklist("account1")
            assert "account1" not in self.strategy.get_blacklist()

    def test_blacklist_add_duplicate(self) -> None:
        """重复添加黑名单。"""
        with patch("plugins.court_automation.token.account_selection_strategy.cache_manager") as mock_cm:
            mock_cm.cache_blacklist = MagicMock()
            self.strategy.add_to_blacklist("account1")
            self.strategy.add_to_blacklist("account1")
            assert self.strategy.get_blacklist().count("account1") == 1

    def test_clear_blacklist(self) -> None:
        """清空黑名单。"""
        with patch("plugins.court_automation.token.account_selection_strategy.cache_manager") as mock_cm:
            mock_cm.cache_blacklist = MagicMock()
            mock_cm.invalidate_blacklist_cache = MagicMock()

            self.strategy.add_to_blacklist("account1")
            self.strategy.clear_blacklist()
            assert len(self.strategy.get_blacklist()) == 0

    def test_select_best_account(self) -> None:
        """选择最优账号。"""
        from apps.core.dto.organization import AccountCredentialDTO

        accounts = [
            AccountCredentialDTO(
                id=1, lawyer_id=1, lawyer_name="律师1",
                site_name="site1", url=None, account="acc1", password="",
                login_success_count=10,
                login_failure_count=1,
                last_login_success_at="2025-01-01T12:00:00",
            ),
            AccountCredentialDTO(
                id=2, lawyer_id=2, lawyer_name="律师2",
                site_name="site1", url=None, account="acc2", password="",
                login_success_count=1,
                login_failure_count=5,
                last_login_success_at="2025-01-01T12:00:00",
            ),
        ]
        result = self.strategy._select_best_account(accounts)
        assert result.account == "acc1"

    def test_select_best_account_single(self) -> None:
        """只有一个账号时直接返回。"""
        from apps.core.dto.organization import AccountCredentialDTO

        accounts = [
            AccountCredentialDTO(
                id=1, lawyer_id=1, lawyer_name="律师1",
                site_name="site1", url=None, account="acc1", password="",
                login_success_count=5,
                login_failure_count=0,
            ),
        ]
        result = self.strategy._select_best_account(accounts)
        assert result.account == "acc1"

    def test_remove_from_blacklist_not_exists(self) -> None:
        """移除不存在的黑名单项。"""
        self.strategy.remove_from_blacklist("nonexistent")
        # 不应报错
