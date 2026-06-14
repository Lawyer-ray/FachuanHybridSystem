"""Tests for automation.models.token uncovered branches."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.models.token import (
    CourtToken,
    TokenAcquisitionHistory,
)


class TestCourtToken:
    """Cover CourtToken model branches."""

    def test_str_with_site_and_account(self):
        obj = SimpleNamespace(site_name="zxfw", account="test_user")
        result = str(CourtToken.__str__(obj))
        assert "zxfw" in result
        assert "test_user" in result

    def test_is_expired_true(self):
        from django.utils import timezone
        import datetime

        obj = SimpleNamespace(
            expires_at=timezone.now() - datetime.timedelta(hours=1),
        )
        assert CourtToken.is_expired(obj) is True

    def test_is_expired_false(self):
        from django.utils import timezone
        import datetime

        obj = SimpleNamespace(
            expires_at=timezone.now() + datetime.timedelta(hours=1),
        )
        assert CourtToken.is_expired(obj) is False


class TestTokenAcquisitionHistory:
    """Cover TokenAcquisitionHistory model branches."""

    def test_str_basic(self):
        obj = SimpleNamespace(
            site_name="zxfw",
            account="test_user",
            status="success",
        )
        # get_status_display needs to be mocked
        obj.get_status_display = lambda: "成功"
        result = str(TokenAcquisitionHistory.__str__(obj))
        assert "zxfw" in result
        assert "test_user" in result

    def test_get_success_rate_display_success(self):
        obj = SimpleNamespace(status="success")
        result = TokenAcquisitionHistory.get_success_rate_display(obj)
        assert result == "100%"

    def test_get_success_rate_display_failed(self):
        obj = SimpleNamespace(status="failed")
        result = TokenAcquisitionHistory.get_success_rate_display(obj)
        assert result == "0%"

    def test_on_save_scrub_with_token_preview(self):
        obj = SimpleNamespace(
            token_preview="some_token_preview",
            error_message=None,
            error_details=None,
            token_fingerprint=None,
            token_redacted=None,
        )
        with patch("apps.core.security.scrub.fingerprint_sha256", return_value="fp") as mock_fp, \
             patch("apps.core.security.scrub.mask_secret", return_value="masked") as mock_mask:
            TokenAcquisitionHistory.on_save_scrub_sensitive_fields(obj)
            assert obj.token_fingerprint == "fp"
            assert obj.token_redacted == "masked"
            assert obj.token_preview is None

    def test_on_save_scrub_without_token_preview(self):
        obj = SimpleNamespace(
            token_preview=None,
            error_message=None,
            error_details=None,
            token_fingerprint=None,
            token_redacted=None,
        )
        TokenAcquisitionHistory.on_save_scrub_sensitive_fields(obj)
        assert obj.token_fingerprint is None

    def test_on_save_scrub_with_error_message(self):
        obj = SimpleNamespace(
            token_preview=None,
            error_message="some error with sensitive data",
            error_details=None,
            token_fingerprint=None,
            token_redacted=None,
        )
        with patch("apps.core.security.scrub.scrub_text", return_value="scrubbed error") as mock_scrub:
            TokenAcquisitionHistory.on_save_scrub_sensitive_fields(obj)
            assert obj.error_message == "scrubbed error"

    def test_on_save_scrub_with_error_details(self):
        obj = SimpleNamespace(
            token_preview=None,
            error_message=None,
            error_details={"key": "value"},
            token_fingerprint=None,
            token_redacted=None,
        )
        with patch("apps.core.security.scrub.scrub_obj", return_value={"key": "scrubbed"}) as mock_scrub:
            TokenAcquisitionHistory.on_save_scrub_sensitive_fields(obj)
            assert obj.error_details == {"key": "scrubbed"}

    def test_on_save_scrub_all_fields(self):
        obj = SimpleNamespace(
            token_preview="preview",
            error_message="error",
            error_details={"detail": "info"},
            token_fingerprint=None,
            token_redacted=None,
        )
        with patch("apps.core.security.scrub.fingerprint_sha256", return_value="fp"), \
             patch("apps.core.security.scrub.mask_secret", return_value="masked"), \
             patch("apps.core.security.scrub.scrub_text", return_value="scrubbed_err"), \
             patch("apps.core.security.scrub.scrub_obj", return_value={"detail": "scrubbed"}):
            TokenAcquisitionHistory.on_save_scrub_sensitive_fields(obj)
            assert obj.token_fingerprint == "fp"
            assert obj.token_redacted == "masked"
            assert obj.token_preview is None
            assert obj.error_message == "scrubbed_err"
            assert obj.error_details == {"detail": "scrubbed"}
