"""Tests for social_auth services."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


class TestSocialAuthServiceHelpers:
    def test_generate_password_length(self):
        from apps.social_auth.services.social_auth_service import _generate_password
        pw = _generate_password()
        assert len(pw) == 32

    def test_generate_username(self):
        from apps.social_auth.services.social_auth_service import _generate_username
        assert _generate_username("wx_12345") == "soc_wx_12345"

    def test_generate_username_long_id(self):
        from apps.social_auth.services.social_auth_service import _generate_username
        result = _generate_username("a" * 20)
        assert result.startswith("soc_")
        assert len(result) <= 16


class TestSocialAuthServiceEnsureUniqueUsername:
    def test_unique_first_try(self):
        from apps.social_auth.services.social_auth_service import _ensure_unique_username
        with patch("apps.social_auth.services.social_auth_service.Lawyer") as MockLawyer:
            MockLawyer.objects.filter.return_value.exists.return_value = False
            assert _ensure_unique_username("test_user") == "test_user"

    def test_unique_second_try(self):
        from apps.social_auth.services.social_auth_service import _ensure_unique_username
        with patch("apps.social_auth.services.social_auth_service.Lawyer") as MockLawyer:
            MockLawyer.objects.filter.return_value.exists.side_effect = [True, False]
            assert _ensure_unique_username("test_user") == "test_user_1"


class TestSocialAuthServiceLinkOrCreateUser:
    @pytest.mark.django_db
    def test_existing_account_updates(self):
        from apps.social_auth.services.social_auth_service import link_or_create_user
        from apps.social_auth.providers.base import SocialProfile

        profile = SocialProfile(
            provider="wechat",
            provider_user_id="wx_12345",
            email="test@example.com",
            display_name="测试用户",
            avatar_url="https://example.com/avatar.jpg",
            raw_data={"openid": "wx_12345"},
        )

        mock_account = MagicMock()
        mock_user = MagicMock()
        mock_account.user = mock_user

        with patch("apps.social_auth.services.social_auth_service.SocialAccount") as MockSA:
            MockSA.objects.select_related.return_value.filter.return_value.first.return_value = mock_account
            result = link_or_create_user(profile)
            assert result is mock_user
            mock_account.save.assert_called_once()
