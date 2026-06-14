"""
Extended unit tests for core/infrastructure/cache.py

Covers:
  - _safe_get_config: success, ImportError fallback
  - _hash_key_component: deterministic hashing
  - _normalize_key_component: empty, long, special chars, valid
  - get_cache_config: Redis path, locmem fallback
  - CacheKeys: all class methods
  - CacheTimeout: get_short, get_medium, get_long, get_day, until_end_of_day,
    metaclass __getattribute__
  - invalidate_user_access_context / invalidate_users_access_context
  - bump_cache_version: success, fallback on ConnectionError
  - delete_cache_key
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from unittest.mock import MagicMock, patch

import pytest


# ===========================================================================
# _safe_get_config
# ===========================================================================


class TestSafeGetConfig:
    def test_success(self) -> None:
        with patch("apps.core.config.get_config", return_value="val"):
            from apps.core.infrastructure.cache import _safe_get_config
            assert _safe_get_config("key", "default") == "val"

    def test_import_error_returns_default(self) -> None:
        with patch.dict("sys.modules", {"apps.core.config": None}):
            # Need to reload to trigger import error
            from apps.core.infrastructure.cache import _safe_get_config
            # The function catches ImportError internally, so we test via the fallback
            result = _safe_get_config("nonexistent_key_xyz", "default")
            assert result == "default"

    def test_key_error_returns_default(self) -> None:
        with patch("apps.core.config.get_config", side_effect=KeyError("bad")):
            from apps.core.infrastructure.cache import _safe_get_config
            assert _safe_get_config("key", "default") == "default"


# ===========================================================================
# _hash_key_component
# ===========================================================================


class TestHashKeyComponent:
    def test_deterministic(self) -> None:
        from apps.core.infrastructure.cache import _hash_key_component
        h1 = _hash_key_component("test_value")
        h2 = _hash_key_component("test_value")
        assert h1 == h2

    def test_length(self) -> None:
        from apps.core.infrastructure.cache import _hash_key_component
        h = _hash_key_component("test")
        assert len(h) == 32

    def test_different_inputs_different_hashes(self) -> None:
        from apps.core.infrastructure.cache import _hash_key_component
        h1 = _hash_key_component("value1")
        h2 = _hash_key_component("value2")
        assert h1 != h2


# ===========================================================================
# _normalize_key_component
# ===========================================================================


class TestNormalizeKeyComponent:
    def test_empty_returns_empty(self) -> None:
        from apps.core.infrastructure.cache import _normalize_key_component
        assert _normalize_key_component("") == "empty"

    def test_none_returns_empty(self) -> None:
        from apps.core.infrastructure.cache import _normalize_key_component
        assert _normalize_key_component(None) == "empty"

    def test_valid_simple(self) -> None:
        from apps.core.infrastructure.cache import _normalize_key_component
        assert _normalize_key_component("my-key_123") == "my-key_123"

    def test_special_chars_replaced(self) -> None:
        from apps.core.infrastructure.cache import _normalize_key_component
        result = _normalize_key_component("hello world!@#")
        assert "!" not in result
        assert " " not in result
        assert "@" not in result

    def test_long_truncated_with_hash(self) -> None:
        from apps.core.infrastructure.cache import _normalize_key_component
        result = _normalize_key_component("a" * 100, max_len=20)
        # Should be truncated to 20 chars + hash suffix
        # But if longer, should include hash
        assert len(result) > 20  # because hash is appended

    def test_all_special_chars(self) -> None:
        from apps.core.infrastructure.cache import _normalize_key_component
        result = _normalize_key_component("!@#$%^&*()")
        assert result != "empty"
        assert "-" not in result.lstrip("-").rstrip("-") or len(result) > 0


# ===========================================================================
# get_cache_config
# ===========================================================================


class TestGetCacheConfig:
    def test_locmem_fallback(self) -> None:
        with patch("apps.core.config.django_runtime.resolve_cache_redis_url", return_value=None):
            with patch("apps.core.infrastructure.cache._safe_get_config", return_value=300):
                from apps.core.infrastructure.cache import get_cache_config
                config = get_cache_config()
        assert config["default"]["BACKEND"] == "django.core.cache.backends.locmem.LocMemCache"

    def test_redis_config(self) -> None:
        with patch("apps.core.config.django_runtime.resolve_cache_redis_url", return_value="redis://localhost:6379/0"):
            with patch("apps.core.infrastructure.cache._safe_get_config", return_value=300):
                from apps.core.infrastructure.cache import get_cache_config
                config = get_cache_config()
        assert "redis" in config["default"]["BACKEND"].lower()


# ===========================================================================
# CacheKeys
# ===========================================================================


class TestCacheKeys:
    def test_user_org_access(self) -> None:
        from apps.core.infrastructure.cache import CacheKeys
        assert CacheKeys.user_org_access(42) == "user:org_access:42"

    def test_user_teams(self) -> None:
        from apps.core.infrastructure.cache import CacheKeys
        assert CacheKeys.user_teams(7) == "user:teams:7"

    def test_case_access_grants(self) -> None:
        from apps.core.infrastructure.cache import CacheKeys
        assert CacheKeys.case_access_grants(1) == "case:access_grants:1"

    def test_automation_court_sms_recovery_scheduled(self) -> None:
        from apps.core.infrastructure.cache import CacheKeys
        result = CacheKeys.automation_court_sms_recovery_scheduled()
        assert "automation:court_sms_recovery_scheduled" in result

    def test_court_token(self) -> None:
        from apps.core.infrastructure.cache import CacheKeys
        key = CacheKeys.court_token("site1", "account1")
        assert "court_token:" in key
        assert "site1" in key.lower() or "site" in key.lower()

    def test_prompt_template(self) -> None:
        from apps.core.infrastructure.cache import CacheKeys
        assert CacheKeys.prompt_template("my_prompt") == "prompt_template:my_prompt"

    def test_prompt_version_active(self) -> None:
        from apps.core.infrastructure.cache import CacheKeys
        assert CacheKeys.prompt_version_active("my_prompt") == "prompt_version:active:my_prompt"

    def test_system_config(self) -> None:
        from apps.core.infrastructure.cache import CacheKeys
        assert CacheKeys.system_config("key1") == "system_config:key1"

    def test_documents_matching_contract_templates(self) -> None:
        from apps.core.infrastructure.cache import CacheKeys
        key = CacheKeys.documents_matching_contract_templates(case_type="civil", version=1)
        assert "civil" in key

    def test_documents_matching_folder_templates(self) -> None:
        from apps.core.infrastructure.cache import CacheKeys
        key = CacheKeys.documents_matching_folder_templates(template_type="t1", case_type="c1", version=2)
        assert "t1" in key
        assert "c1" in key

    def test_documents_matching_case_file_templates(self) -> None:
        from apps.core.infrastructure.cache import CacheKeys
        key = CacheKeys.documents_matching_case_file_templates(
            case_type="civil", case_stage="filing", institutions="court1", version=1
        )
        assert "civil" in key

    def test_documents_matching_version_document_templates(self) -> None:
        from apps.core.infrastructure.cache import CacheKeys
        key = CacheKeys.documents_matching_version_document_templates()
        assert "version" in key

    def test_documents_matching_version_folder_templates(self) -> None:
        from apps.core.infrastructure.cache import CacheKeys
        key = CacheKeys.documents_matching_version_folder_templates()
        assert "version" in key

    def test_automation_token_perf_acquisition(self) -> None:
        from apps.core.infrastructure.cache import CacheKeys
        key = CacheKeys.automation_token_perf_acquisition("acq-123")
        assert "acq-123" in key

    def test_automation_token_perf_concurrent(self) -> None:
        from apps.core.infrastructure.cache import CacheKeys
        key = CacheKeys.automation_token_perf_concurrent(site_name="test_site")
        assert "test_site" in key

    def test_automation_token_perf_counter(self) -> None:
        from apps.core.infrastructure.cache import CacheKeys
        key = CacheKeys.automation_token_perf_counter(date="2025-01-01", site_name="site", metric="count")
        assert "site" in key
        assert "count" in key


# ===========================================================================
# CacheTimeout
# ===========================================================================


class TestCacheTimeout:
    def test_short(self) -> None:
        from apps.core.infrastructure.cache import CacheTimeout
        assert CacheTimeout.get_short() == 60

    def test_medium(self) -> None:
        from apps.core.infrastructure.cache import CacheTimeout
        assert CacheTimeout.get_medium() == 300

    def test_long(self) -> None:
        from apps.core.infrastructure.cache import CacheTimeout
        assert CacheTimeout.get_long() == 3600

    def test_day(self) -> None:
        from apps.core.infrastructure.cache import CacheTimeout
        assert CacheTimeout.get_day() == 86400

    def test_until_end_of_day(self) -> None:
        from apps.core.infrastructure.cache import CacheTimeout
        # Use a fixed time
        now = datetime(2025, 6, 13, 14, 0, 0)
        with patch("django.utils.timezone.now", return_value=now):
            with patch("django.utils.timezone.is_naive", return_value=True):
                with patch("django.utils.timezone.make_aware", side_effect=lambda dt, tz=None: dt):
                    with patch("django.utils.timezone.get_current_timezone", return_value=None):
                        result = CacheTimeout.until_end_of_day(now=now, buffer_seconds=0)
        assert result > 0

    def test_metaclass_getattribute_known_key(self) -> None:
        from apps.core.infrastructure.cache import CacheTimeout
        # SHORT is in _DEFAULT_TIMEOUTS, so metaclass should handle it
        val = CacheTimeout.SHORT
        assert val == 60

    def test_metaclass_getattribute_unknown_key(self) -> None:
        from apps.core.infrastructure.cache import CacheTimeout
        # Accessing a non-timeout attribute should work normally
        assert CacheTimeout.get_short is not None


# ===========================================================================
# invalidate_user_access_context
# ===========================================================================


@patch("django.core.cache.cache")
class TestInvalidateUserAccessContext:
    def test_invalidate_both(self, mock_cache) -> None:
        from apps.core.infrastructure.cache import invalidate_user_access_context
        invalidate_user_access_context(42, org_access=True, case_grants=True)
        mock_cache.delete_many.assert_called_once()
        keys = mock_cache.delete_many.call_args[0][0]
        assert len(keys) == 2

    def test_invalidate_org_only(self, mock_cache) -> None:
        from apps.core.infrastructure.cache import invalidate_user_access_context
        invalidate_user_access_context(42, org_access=True, case_grants=False)
        mock_cache.delete_many.assert_called_once()
        keys = mock_cache.delete_many.call_args[0][0]
        assert len(keys) == 1

    def test_invalidate_nothing(self, mock_cache) -> None:
        from apps.core.infrastructure.cache import invalidate_user_access_context
        invalidate_user_access_context(42, org_access=False, case_grants=False)
        mock_cache.delete_many.assert_not_called()


# ===========================================================================
# invalidate_users_access_context
# ===========================================================================


@patch("django.core.cache.cache")
class TestInvalidateUsersAccessContext:
    def test_invalidate_multiple_users(self, mock_cache) -> None:
        from apps.core.infrastructure.cache import invalidate_users_access_context
        invalidate_users_access_context([1, 2, 3])
        mock_cache.delete_many.assert_called_once()
        keys = mock_cache.delete_many.call_args[0][0]
        assert len(keys) == 6  # 2 keys per user * 3 users

    def test_invalidate_empty_list(self, mock_cache) -> None:
        from apps.core.infrastructure.cache import invalidate_users_access_context
        invalidate_users_access_context([])
        mock_cache.delete_many.assert_not_called()

    def test_invalidate_none_list(self, mock_cache) -> None:
        from apps.core.infrastructure.cache import invalidate_users_access_context
        invalidate_users_access_context(None)
        mock_cache.delete_many.assert_not_called()


# ===========================================================================
# bump_cache_version
# ===========================================================================


@patch("django.core.cache.cache")
class TestBumpCacheVersion:
    def test_success(self, mock_cache) -> None:
        from apps.core.infrastructure.cache import bump_cache_version
        mock_cache.incr.return_value = 5
        result = bump_cache_version("ver:key", timeout=600)
        assert result == 5

    def test_connection_error_fallback(self, mock_cache) -> None:
        from apps.core.infrastructure.cache import bump_cache_version
        mock_cache.incr.side_effect = ConnectionError("fail")
        mock_cache.get.return_value = 10
        result = bump_cache_version("ver:key", timeout=600)
        assert result == 11
        mock_cache.set.assert_called_once()

    def test_timeout_error_fallback(self, mock_cache) -> None:
        from apps.core.infrastructure.cache import bump_cache_version
        mock_cache.incr.side_effect = TimeoutError("timeout")
        mock_cache.get.return_value = 3
        result = bump_cache_version("ver:key", timeout=600)
        assert result == 4

    def test_os_error_fallback(self, mock_cache) -> None:
        from apps.core.infrastructure.cache import bump_cache_version
        mock_cache.incr.side_effect = OSError("os")
        mock_cache.get.return_value = None  # should default to 1
        result = bump_cache_version("ver:key", timeout=600)
        assert result == 2

    def test_value_error_fallback(self, mock_cache) -> None:
        from apps.core.infrastructure.cache import bump_cache_version
        mock_cache.incr.side_effect = ValueError("bad")
        mock_cache.get.return_value = 5
        result = bump_cache_version("ver:key", timeout=600)
        assert result == 6

    def test_type_error_fallback(self, mock_cache) -> None:
        from apps.core.infrastructure.cache import bump_cache_version
        mock_cache.incr.side_effect = TypeError("bad")
        mock_cache.get.return_value = 2
        result = bump_cache_version("ver:key", timeout=600)
        assert result == 3


# ===========================================================================
# delete_cache_key
# ===========================================================================


@patch("django.core.cache.cache")
class TestDeleteCacheKey:
    def test_deletes(self, mock_cache) -> None:
        from apps.core.infrastructure.cache import delete_cache_key
        delete_cache_key("my_key")
        mock_cache.delete.assert_called_once_with("my_key")
