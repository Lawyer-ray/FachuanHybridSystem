"""Additional unit tests for PasswordResetService."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest
from django.contrib.auth.hashers import make_password
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.organization.models import Lawyer
from apps.organization.services.auth.password_reset_service import (
    CustomPasswordResetTokenGenerator,
    PasswordResetService,
    password_reset_token_generator,
)


@pytest.fixture
def user(db):
    return Lawyer.objects.create_user(
        username="reset_user",
        phone="13800001111",
        email="reset@example.com",
        password="OldP@ss123",
    )


class TestCustomTokenGenerator:
    def test_make_hash_value_includes_password(self, user):
        gen = CustomPasswordResetTokenGenerator()
        hash_val = gen._make_hash_value(user, 1234567890)
        assert user.password in hash_val
        assert str(user.pk) in hash_val

    def test_token_changes_after_password_change(self, user):
        token1 = password_reset_token_generator.make_token(user)
        user.set_password("NewP@ss456")
        user.save(update_fields=["password"])
        # Old token should be invalid
        assert not password_reset_token_generator.check_token(user, token1)


class TestVerifyResetTokenEdgeCases:
    def test_invalid_uid(self, user):
        is_valid, u, msg = PasswordResetService.verify_reset_token("!!!invalid!!!", "token")
        assert is_valid is False
        assert u is None

    def test_nonexistent_user(self, user):
        uid = urlsafe_base64_encode(force_bytes(999999))
        is_valid, u, msg = PasswordResetService.verify_reset_token(uid, "any-token")
        assert is_valid is False
        assert u is None

    def test_valid_token(self, user):
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = password_reset_token_generator.make_token(user)
        is_valid, u, msg = PasswordResetService.verify_reset_token(uid, token)
        assert is_valid is True
        assert u.pk == user.pk


class TestResetPasswordEdgeCases:
    def test_invalid_uid_returns_false(self):
        success, msg = PasswordResetService.reset_password("bad-uid", "bad-token", "NewP@ss1")
        assert success is False

    @patch("apps.organization.services.auth.password_reset_service.EmailService.send_password_changed_notification")
    def test_password_actually_changed(self, mock_notify, user):
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = password_reset_token_generator.make_token(user)
        success, _ = PasswordResetService.reset_password(uid, token, "BrandNewP@ss1")
        assert success is True
        user.refresh_from_db()
        assert user.check_password("BrandNewP@ss1")

    @patch("apps.organization.services.auth.password_reset_service.EmailService.send_password_changed_notification")
    def test_old_password_no_longer_works(self, mock_notify, user):
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = password_reset_token_generator.make_token(user)
        PasswordResetService.reset_password(uid, token, "BrandNewP@ss1")
        user.refresh_from_db()
        assert not user.check_password("OldP@ss123")


class TestRequestPasswordResetRateLimiting:
    @patch("apps.organization.services.auth.password_reset_service.cache")
    @patch("apps.organization.services.auth.password_reset_service.EmailService.send_password_reset_email", return_value=True)
    def test_rate_limit_returns_false(self, mock_email, mock_cache, db):
        # Use a unique email and clear rate limit cache
        user = Lawyer.objects.create_user(
            username="rate_limit_user",
            phone="13800009998",
            email="ratelimit@example.com",
            password="Pass123!",
        )
        # Clear any rate limit cache
        mock_cache.get.return_value = None
        mock_cache.set.return_value = None

        success1, _ = PasswordResetService.request_password_reset("ratelimit@example.com")
        assert success1 is True

        # Simulate rate limit: cache.get returns a recent timestamp
        from django.utils import timezone
        mock_cache.get.return_value = timezone.now()

        # Second immediate request should be rate limited
        success2, msg = PasswordResetService.request_password_reset("ratelimit@example.com")
        assert success2 is False
        assert "稍后" in msg

    @patch("apps.organization.services.auth.password_reset_service.EmailService.send_password_reset_email", return_value=True)
    def test_nonexistent_email_always_succeeds(self, mock_email, db):
        success, msg = PasswordResetService.request_password_reset("noone@example.com")
        assert success is True
        assert "已发送" in msg

    @patch("apps.organization.services.auth.password_reset_service.EmailService.send_password_reset_email", return_value=False)
    def test_email_send_failure(self, mock_email, user):
        success, msg = PasswordResetService.request_password_reset("reset@example.com")
        assert success is False
        assert "失败" in msg

    def test_inactive_user_not_found(self, db):
        Lawyer.objects.create_user(
            username="inactive",
            phone="13900009999",
            email="inactive@example.com",
            password="Pass123!",
            is_active=False,
        )
        success, msg = PasswordResetService.request_password_reset("inactive@example.com")
        # Even for inactive user, returns success (prevent enumeration)
        assert success is True


class TestPasswordResetServiceConstants:
    def test_token_expiry(self):
        assert PasswordResetService.TOKEN_EXPIRY_MINUTES == 30

    def test_send_cooldown(self):
        assert PasswordResetService.SEND_COOLDOWN_SECONDS == 60
