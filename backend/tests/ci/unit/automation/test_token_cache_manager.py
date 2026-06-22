"""TokenCacheManager 全覆盖测试。"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

try:
    from plugins import has_court_login_plugin
    _HAS_LOGIN = has_court_login_plugin()
except ImportError:
    _HAS_LOGIN = False

if _HAS_LOGIN:
    from plugins.court_automation.token.cache_manager import TokenCacheManager
else:
    TokenCacheManager = None  # type: ignore[assignment,misc]

pytestmark = pytest.mark.skipif(not _HAS_LOGIN, reason="court_login plugin not installed")


class TestTokenCacheManager:
    """TokenCacheManager 核心方法测试。"""

    def _make_manager(self) -> TokenCacheManager:
        return TokenCacheManager.__new__(TokenCacheManager)

    # ─── _get_token_cache_key ───

    def test_get_token_cache_key_normal(self) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        key = mgr._get_token_cache_key("zxfw", "user1")
        assert "auto_token:token:zxfw:" in key

    def test_get_token_cache_key_special_chars(self) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        key = mgr._get_token_cache_key("test@site!", "acct")
        # Special chars replaced
        assert "test_site_" in key

    # ─── get_cached_token ───

    @patch("plugins.court_automation.token.cache_manager.record_cache_result")
    @patch("plugins.court_automation.token.cache_manager.record_cache_access")
    @patch("plugins.court_automation.token.cache_manager.performance_monitor")
    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_get_cached_token_hit(self, mock_cache: MagicMock, mock_pm: MagicMock,
                                   mock_rec_access: MagicMock, mock_rec_result: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mock_cache.get.return_value = {"token": "abc123"}
        result = mgr.get_cached_token("site", "acct")
        assert result == "abc123"

    @patch("plugins.court_automation.token.cache_manager.record_cache_result")
    @patch("plugins.court_automation.token.cache_manager.record_cache_access")
    @patch("plugins.court_automation.token.cache_manager.performance_monitor")
    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_get_cached_token_miss(self, mock_cache: MagicMock, mock_pm: MagicMock,
                                    mock_rec_access: MagicMock, mock_rec_result: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mock_cache.get.return_value = None
        result = mgr.get_cached_token("site", "acct")
        assert result is None

    @patch("plugins.court_automation.token.cache_manager.record_cache_result")
    @patch("plugins.court_automation.token.cache_manager.record_cache_access")
    @patch("plugins.court_automation.token.cache_manager.performance_monitor")
    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_get_cached_token_exception(self, mock_cache: MagicMock, mock_pm: MagicMock,
                                         mock_rec_access: MagicMock, mock_rec_result: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mock_cache.get.side_effect = RuntimeError("cache down")
        result = mgr.get_cached_token("site", "acct")
        assert result is None

    # ─── cache_token ───

    @patch("plugins.court_automation.token.cache_manager.timezone")
    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_cache_token_no_expiry(self, mock_cache: MagicMock, mock_tz: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mock_tz.now.return_value = datetime(2025, 1, 1, 12, 0, 0)
        mgr.cache_token("site", "acct", "token123")
        mock_cache.set.assert_called_once()
        call_kwargs = mock_cache.set.call_args
        assert call_kwargs[0][1]["token"] == "token123"

    @patch("plugins.court_automation.token.cache_manager.timezone")
    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_cache_token_with_future_expiry(self, mock_cache: MagicMock, mock_tz: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mock_tz.now.return_value = datetime(2025, 1, 1, 12, 0, 0)
        expires = datetime(2025, 1, 1, 14, 0, 0)  # 2 hours from now
        mgr.cache_token("site", "acct", "tok", expires_at=expires)
        mock_cache.set.assert_called_once()
        timeout = mock_cache.set.call_args[1]["timeout"]
        # 2 hours - 5 minutes = 7200 - 300 = 6900
        assert timeout == 6900

    @patch("plugins.court_automation.token.cache_manager.timezone")
    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_cache_token_expiring_soon_skipped(self, mock_cache: MagicMock, mock_tz: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mock_tz.now.return_value = datetime(2025, 1, 1, 12, 0, 0)
        expires = datetime(2025, 1, 1, 12, 3, 0)  # 3 minutes from now < 5 min buffer
        mgr.cache_token("site", "acct", "tok", expires_at=expires)
        mock_cache.set.assert_not_called()

    @patch("plugins.court_automation.token.cache_manager.timezone")
    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_cache_token_exception(self, mock_cache: MagicMock, mock_tz: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mock_tz.now.return_value = datetime(2025, 1, 1, 12, 0, 0)
        mock_cache.set.side_effect = RuntimeError("fail")
        # Should not raise
        mgr.cache_token("site", "acct", "tok")

    # ─── invalidate_token_cache ───

    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_invalidate_token_cache(self, mock_cache: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mgr.invalidate_token_cache("site", "acct")
        mock_cache.delete.assert_called_once()

    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_invalidate_token_cache_exception(self, mock_cache: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mock_cache.delete.side_effect = RuntimeError("fail")
        mgr.invalidate_token_cache("site", "acct")

    # ─── get_cached_credentials ───

    @patch("plugins.court_automation.token.cache_manager.performance_monitor")
    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_get_cached_credentials_hit(self, mock_cache: MagicMock, mock_pm: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        cred_data = [{"id": 1, "lawyer_id": 1, "lawyer_name": "张三", "site_name": "s", "url": None, "account": "a", "password": ""}]
        mock_cache.get.return_value = cred_data
        result = mgr.get_cached_credentials("s")
        assert result is not None
        assert len(result) == 1

    @patch("plugins.court_automation.token.cache_manager.performance_monitor")
    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_get_cached_credentials_miss(self, mock_cache: MagicMock, mock_pm: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mock_cache.get.return_value = None
        result = mgr.get_cached_credentials("s")
        assert result is None

    @patch("plugins.court_automation.token.cache_manager.performance_monitor")
    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_get_cached_credentials_exception(self, mock_cache: MagicMock, mock_pm: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mock_cache.get.side_effect = RuntimeError("fail")
        result = mgr.get_cached_credentials("s")
        assert result is None

    # ─── cache_credentials ───

    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_cache_credentials(self, mock_cache: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        cred = SimpleNamespace(site_name="s", account="a", password="secret123", extra="x")  # pragma: allowlist secret
        mgr.cache_credentials("s", [cred])
        mock_cache.set.assert_called_once()
        saved = mock_cache.set.call_args[0][1]
        assert saved[0]["password"] == ""  # password blanked

    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_cache_credentials_exception(self, mock_cache: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mock_cache.set.side_effect = RuntimeError("fail")
        mgr.cache_credentials("s", [])

    # ─── invalidate_credentials_cache ───

    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_invalidate_credentials_cache(self, mock_cache: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mgr.invalidate_credentials_cache("site")
        mock_cache.delete.assert_called_once()

    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_invalidate_credentials_cache_exception(self, mock_cache: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mock_cache.delete.side_effect = RuntimeError("fail")
        mgr.invalidate_credentials_cache("site")

    # ─── get_cached_account_stats ───

    @patch("plugins.court_automation.token.cache_manager.performance_monitor")
    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_get_cached_account_stats_hit(self, mock_cache: MagicMock, mock_pm: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mock_cache.get.return_value = {"total": 10}
        result = mgr.get_cached_account_stats("acct", "site")
        assert result == {"total": 10}

    @patch("plugins.court_automation.token.cache_manager.performance_monitor")
    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_get_cached_account_stats_miss(self, mock_cache: MagicMock, mock_pm: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mock_cache.get.return_value = None
        result = mgr.get_cached_account_stats("acct", "site")
        assert result is None

    @patch("plugins.court_automation.token.cache_manager.performance_monitor")
    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_get_cached_account_stats_exception(self, mock_cache: MagicMock, mock_pm: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mock_cache.get.side_effect = RuntimeError("fail")
        result = mgr.get_cached_account_stats("acct", "site")
        assert result is None

    # ─── cache_account_stats ───

    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_cache_account_stats(self, mock_cache: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mgr.cache_account_stats("acct", "site", {"total": 5})
        mock_cache.set.assert_called_once()

    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_cache_account_stats_exception(self, mock_cache: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mock_cache.set.side_effect = RuntimeError("fail")
        mgr.cache_account_stats("acct", "site", {})

    # ─── invalidate_account_stats_cache ───

    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_invalidate_account_stats_cache(self, mock_cache: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mgr.invalidate_account_stats_cache("acct", "site")
        mock_cache.delete.assert_called_once()

    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_invalidate_account_stats_cache_exception(self, mock_cache: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mock_cache.delete.side_effect = RuntimeError("fail")
        mgr.invalidate_account_stats_cache("acct", "site")

    # ─── blacklist ───

    @patch("plugins.court_automation.token.cache_manager.performance_monitor")
    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_get_cached_blacklist_hit(self, mock_cache: MagicMock, mock_pm: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mock_cache.get.return_value = ["bad1", "bad2"]
        result = mgr.get_cached_blacklist()
        assert result == ["bad1", "bad2"]

    @patch("plugins.court_automation.token.cache_manager.performance_monitor")
    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_get_cached_blacklist_miss(self, mock_cache: MagicMock, mock_pm: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mock_cache.get.return_value = None
        assert mgr.get_cached_blacklist() is None

    @patch("plugins.court_automation.token.cache_manager.performance_monitor")
    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_get_cached_blacklist_exception(self, mock_cache: MagicMock, mock_pm: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mock_cache.get.side_effect = RuntimeError("fail")
        assert mgr.get_cached_blacklist() is None

    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_cache_blacklist(self, mock_cache: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mgr.cache_blacklist(["a", "b"])
        mock_cache.set.assert_called_once()

    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_cache_blacklist_exception(self, mock_cache: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mock_cache.set.side_effect = RuntimeError("fail")
        mgr.cache_blacklist(["a"])

    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_invalidate_blacklist_cache(self, mock_cache: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mgr.invalidate_blacklist_cache()
        mock_cache.delete.assert_called_once()

    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_invalidate_blacklist_cache_exception(self, mock_cache: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mock_cache.delete.side_effect = RuntimeError("fail")
        mgr.invalidate_blacklist_cache()

    # ─── invalidate_site_cache ───

    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_invalidate_site_cache_no_accounts(self, mock_cache: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mgr.invalidate_site_cache("site")
        # Just credentials cache invalidated
        mock_cache.delete.assert_called()

    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_invalidate_site_cache_with_accounts(self, mock_cache: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mgr.invalidate_site_cache("site", accounts=["acct1", "acct2"])
        assert mock_cache.delete.call_count >= 3  # creds + 2 accounts

    # ─── _is_cache_clear_allowed ───

    @patch("django.conf.settings")
    def test_is_cache_clear_allowed_debug(self, mock_settings: MagicMock) -> None:
        mgr = self._make_manager()
        mock_settings.DEBUG = True
        assert mgr._is_cache_clear_allowed() is True

    @patch.dict("os.environ", {"ALLOW_CACHE_CLEAR": "true"})
    @patch("django.conf.settings")
    def test_is_cache_clear_allowed_env(self, mock_settings: MagicMock) -> None:
        mgr = self._make_manager()
        mock_settings.DEBUG = False
        assert mgr._is_cache_clear_allowed() is True

    @patch.dict("os.environ", {"ALLOW_CACHE_CLEAR": ""})
    @patch("django.conf.settings")
    def test_is_cache_clear_not_allowed(self, mock_settings: MagicMock) -> None:
        mgr = self._make_manager()
        mock_settings.DEBUG = False
        assert mgr._is_cache_clear_allowed() is False

    # ─── clear_all_cache ───

    @patch("django.conf.settings")
    def test_clear_all_cache_not_allowed(self, mock_settings: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mock_settings.DEBUG = False
        # No-op when not allowed
        with patch.dict("os.environ", {"ALLOW_CACHE_CLEAR": ""}):
            mgr.clear_all_cache()

    @patch("plugins.court_automation.token.cache_manager.cache")
    @patch("django.conf.settings")
    def test_clear_all_cache_non_redis(self, mock_settings: MagicMock, mock_cache: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mock_settings.DEBUG = True
        mock_settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
        mgr.clear_all_cache()
        mock_cache.clear.assert_called_once()

    @patch("plugins.court_automation.token.cache_manager.cache")
    @patch("django.conf.settings")
    def test_clear_all_cache_redis(self, mock_settings: MagicMock, mock_cache: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mock_settings.DEBUG = True
        mock_settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": "redis://localhost"}}
        with patch("plugins.court_automation.token.cache_manager.TokenCacheManager._clear_redis_namespace_cache") as mock_clear:
            mgr.clear_all_cache()
            mock_clear.assert_called_once()

    # ─── _clear_redis_namespace_cache ───

    def test_clear_redis_no_location(self) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        # No location, should warn
        mgr._clear_redis_namespace_cache({})

    def test_clear_redis_with_valkey(self) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mock_valkey = MagicMock()
        mock_client = MagicMock()
        mock_valkey.from_url.return_value = mock_client
        mock_client.keys.return_value = [b"key1", b"key2"]
        with patch.dict("sys.modules", {"valkey": mock_valkey}):
            mgr._clear_redis_namespace_cache(
                {"LOCATION": "redis://localhost", "KEY_PREFIX": "lf", "VERSION": 1},
                backend="django.core.cache.backends.redis.RedisCache"
            )
            mock_client.keys.assert_called_once()
            mock_client.delete.assert_called_once()

    def test_clear_redis_no_prefix(self) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mock_valkey = MagicMock()
        mock_client = MagicMock()
        mock_valkey.from_url.return_value = mock_client
        mock_client.keys.return_value = []
        with patch.dict("sys.modules", {"valkey": mock_valkey}):
            mgr._clear_redis_namespace_cache(
                {"LOCATION": "redis://localhost"},
            )
            pattern = mock_client.keys.call_args[0][0]
            assert "auto_token:*" in pattern

    def test_clear_redis_module_not_found(self) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        import sys
        # Remove valkey from modules to simulate not found
        with patch.dict("sys.modules", {"valkey": None}):
            mgr._clear_redis_namespace_cache({"LOCATION": "redis://localhost"})

    def test_clear_redis_exception(self) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mock_valkey = MagicMock()
        mock_valkey.from_url.side_effect = RuntimeError("conn fail")
        with patch.dict("sys.modules", {"valkey": mock_valkey}):
            mgr._clear_redis_namespace_cache({"LOCATION": "redis://localhost"})

    # ─── get_cache_statistics ───

    def test_get_cache_statistics(self) -> None:
        mgr = self._make_manager()
        stats = mgr.get_cache_statistics()
        assert "cache_backend" in stats

    # ─── warm_up_cache ───

    def test_warm_up_cache_success(self) -> None:
        mgr = self._make_manager()
        with patch("plugins.court_automation.token.account_selection_strategy.AccountSelectionStrategy"):
            mgr.warm_up_cache("site")

    def test_warm_up_cache_exception(self) -> None:
        mgr = self._make_manager()
        with patch("plugins.court_automation.token.account_selection_strategy.AccountSelectionStrategy", side_effect=RuntimeError("fail")):
            mgr.warm_up_cache("site")

    # ─── get_cached_token cache_data with None token ───

    @patch("plugins.court_automation.token.cache_manager.record_cache_result")
    @patch("plugins.court_automation.token.cache_manager.record_cache_access")
    @patch("plugins.court_automation.token.cache_manager.performance_monitor")
    @patch("plugins.court_automation.token.cache_manager.cache")
    def test_get_cached_token_data_present_but_token_none(self, mock_cache: MagicMock, mock_pm: MagicMock,
                                                           mock_rec_access: MagicMock, mock_rec_result: MagicMock) -> None:
        mgr = self._make_manager()
        mgr.cache_prefix = "auto_token"
        mock_cache.get.return_value = {"token": None}
        result = mgr.get_cached_token("site", "acct")
        assert result is None
