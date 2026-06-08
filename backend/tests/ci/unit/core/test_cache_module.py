"""Tests for core infrastructure cache module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.infrastructure.cache import (
    CacheKeys,
    CacheTimeout,
    _normalize_key_component,
    bump_cache_version,
    delete_cache_key,
    invalidate_user_access_context,
    invalidate_users_access_context,
)


class TestNormalizeKeyComponent:
    def test_simple_alphanumeric(self) -> None:
        assert _normalize_key_component("abc123") == "abc123"

    def test_with_dots_dashes(self) -> None:
        assert _normalize_key_component("my-key.name") == "my-key.name"

    def test_special_chars(self) -> None:
        result = _normalize_key_component("key with spaces!@#")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_empty_string(self) -> None:
        assert _normalize_key_component("") == "empty"

    def test_whitespace_only(self) -> None:
        assert _normalize_key_component("   ") == "empty"

    def test_long_key_truncated(self) -> None:
        long_key = "a" * 100
        result = _normalize_key_component(long_key, max_len=20)
        assert len(result) <= 64

    def test_chinese_chars(self) -> None:
        result = _normalize_key_component("中文键名")
        assert isinstance(result, str)


class TestCacheKeys:
    def test_user_org_access(self) -> None:
        assert CacheKeys.user_org_access(42) == "user:org_access:42"

    def test_user_teams(self) -> None:
        assert CacheKeys.user_teams(1) == "user:teams:1"

    def test_case_access_grants(self) -> None:
        assert CacheKeys.case_access_grants(5) == "case:access_grants:5"

    def test_automation_court_sms_recovery_scheduled(self) -> None:
        result = CacheKeys.automation_court_sms_recovery_scheduled()
        assert result == "automation:court_sms_recovery_scheduled"

    def test_court_token(self) -> None:
        result = CacheKeys.court_token("site1", "account1")
        assert "court_token:" in result

    def test_automation_token_perf_acquisition(self) -> None:
        result = CacheKeys.automation_token_perf_acquisition("acq123")
        assert "acq123" in result

    def test_automation_token_perf_concurrent(self) -> None:
        result = CacheKeys.automation_token_perf_concurrent(site_name="test_site")
        assert "test_site" in result

    def test_automation_token_perf_counter(self) -> None:
        result = CacheKeys.automation_token_perf_counter(
            date="2024-01-01", site_name="site1", metric="count"
        )
        assert "2024-01-01" in result

    def test_prompt_template(self) -> None:
        assert CacheKeys.prompt_template("my_prompt") == "prompt_template:my_prompt"

    def test_prompt_version_active(self) -> None:
        assert CacheKeys.prompt_version_active("v1") == "prompt_version:active:v1"

    def test_system_config(self) -> None:
        assert CacheKeys.system_config("app.name") == "system_config:app.name"

    def test_documents_matching_contract_templates(self) -> None:
        result = CacheKeys.documents_matching_contract_templates(case_type="civil", version=1)
        assert "civil" in result

    def test_documents_matching_folder_templates(self) -> None:
        result = CacheKeys.documents_matching_folder_templates(
            template_type="contract", case_type="civil", version=1
        )
        assert "contract" in result

    def test_documents_matching_case_file_templates(self) -> None:
        result = CacheKeys.documents_matching_case_file_templates(
            case_type="civil", case_stage="first_trial", version=1
        )
        assert "civil" in result

    def test_documents_matching_version_document_templates(self) -> None:
        result = CacheKeys.documents_matching_version_document_templates()
        assert "document_templates" in result

    def test_documents_matching_version_folder_templates(self) -> None:
        result = CacheKeys.documents_matching_version_folder_templates()
        assert "folder_templates" in result


class TestCacheTimeout:
    def test_short(self) -> None:
        assert CacheTimeout.get_short() == 60

    def test_medium(self) -> None:
        assert CacheTimeout.get_medium() == 300

    def test_long(self) -> None:
        assert CacheTimeout.get_long() == 3600

    def test_day(self) -> None:
        assert CacheTimeout.get_day() == 86400

    def test_constants(self) -> None:
        assert CacheTimeout.SHORT == 60
        assert CacheTimeout.MEDIUM == 300
        assert CacheTimeout.LONG == 3600
        assert CacheTimeout.DAY == 86400

    def test_until_end_of_day(self) -> None:
        from django.utils import timezone

        now = timezone.now()
        result = CacheTimeout.until_end_of_day(now=now)
        assert result > 0

    def test_until_end_of_day_with_buffer(self) -> None:
        from django.utils import timezone

        now = timezone.now()
        result1 = CacheTimeout.until_end_of_day(now=now, buffer_seconds=0)
        result2 = CacheTimeout.until_end_of_day(now=now, buffer_seconds=3600)
        assert result2 >= result1


class TestInvalidateUserAccessContext:
    @patch("django.core.cache.cache")
    def test_invalidate_single(self, mock_cache: MagicMock) -> None:
        invalidate_user_access_context(42)
        mock_cache.delete_many.assert_called_once()

    @patch("django.core.cache.cache")
    def test_invalidate_org_access_only(self, mock_cache: MagicMock) -> None:
        invalidate_user_access_context(42, org_access=True, case_grants=False)
        mock_cache.delete_many.assert_called_once()
        keys = mock_cache.delete_many.call_args[0][0]
        assert len(keys) == 1

    @patch("django.core.cache.cache")
    def test_invalidate_case_grants_only(self, mock_cache: MagicMock) -> None:
        invalidate_user_access_context(42, org_access=False, case_grants=True)
        mock_cache.delete_many.assert_called_once()
        keys = mock_cache.delete_many.call_args[0][0]
        assert len(keys) == 1


class TestInvalidateUsersAccessContext:
    @patch("django.core.cache.cache")
    def test_invalidate_multiple(self, mock_cache: MagicMock) -> None:
        invalidate_users_access_context([1, 2, 3])
        mock_cache.delete_many.assert_called_once()
        keys = mock_cache.delete_many.call_args[0][0]
        assert len(keys) == 6  # 2 keys per user

    @patch("django.core.cache.cache")
    def test_empty_list(self, mock_cache: MagicMock) -> None:
        invalidate_users_access_context([])
        mock_cache.delete_many.assert_not_called()


class TestBumpCacheVersion:
    @patch("django.core.cache.cache")
    def test_incr_success(self, mock_cache: MagicMock) -> None:
        mock_cache.incr.return_value = 2
        result = bump_cache_version("version_key", timeout=300)
        assert result == 2

    @patch("django.core.cache.cache")
    def test_incr_fails_fallback(self, mock_cache: MagicMock) -> None:
        mock_cache.incr.side_effect = ConnectionError("no connection")
        mock_cache.get.return_value = 5
        result = bump_cache_version("version_key", timeout=300)
        assert result == 6
        mock_cache.set.assert_called()


class TestDeleteCacheKey:
    @patch("django.core.cache.cache")
    def test_deletes(self, mock_cache: MagicMock) -> None:
        delete_cache_key("my_key")
        mock_cache.delete.assert_called_once_with("my_key")
