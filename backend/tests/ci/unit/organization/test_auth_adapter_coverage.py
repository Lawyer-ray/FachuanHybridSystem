"""Tests for organization/services/organization_service_adapter.py (missing: 3 lines) +
organization/services/access/org_access_computation_service.py (missing: 1 line) +
organization/services/auth/auth_service.py (missing: 4 lines) +
organization/services/auth/password_reset_service.py (missing: 16 lines).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import AuthenticationError, NotFoundError, PermissionDenied


# ── AuthService deep branches ────────────────────────────────────────────


class TestAuthServiceDeep:
    def test_login_success(self) -> None:
        from apps.organization.services.auth.auth_service import AuthService
        svc = AuthService()
        request = MagicMock()
        # Need to return a real Lawyer instance to pass isinstance check
        from apps.organization.models import Lawyer
        mock_user = MagicMock(spec=Lawyer)
        mock_user.is_authenticated = True
        with patch("apps.organization.services.auth.auth_service.authenticate", return_value=mock_user), \
             patch("apps.organization.services.auth.auth_service.login") as mock_login:
            result = svc.login(request, "user", "pass")
            mock_login.assert_called_once()

    def test_login_failure(self) -> None:
        from apps.organization.services.auth.auth_service import AuthService
        svc = AuthService()
        request = MagicMock()
        with patch("apps.organization.services.auth.auth_service.authenticate", return_value=None):
            with pytest.raises(AuthenticationError, match="用户名或密码错误"):
                svc.login(request, "user", "wrong")

    def test_logout(self) -> None:
        from apps.organization.services.auth.auth_service import AuthService
        svc = AuthService()
        request = MagicMock()
        with patch("apps.organization.services.auth.auth_service.logout") as mock_logout:
            svc.logout(request)
            mock_logout.assert_called_once_with(request)

    @pytest.mark.django_db
    def test_register_first_user_grants_admin(self) -> None:
        from apps.organization.services.auth.auth_service import AuthService
        svc = AuthService()
        with patch("apps.organization.services.auth.auth_service.Lawyer") as MockLawyer:
            MockLawyer.objects.exists.return_value = False
            with patch("apps.organization.services.auth.auth_service.settings") as mock_settings:
                mock_settings.ALLOW_FIRST_USER_SUPERUSER = True
                mock_settings.DEBUG = True
                MockLawyer.objects.create_user.return_value = MagicMock()
                result = svc.register("admin", "pass", real_name="Admin")
                assert result.user is not None

    @pytest.mark.django_db
    def test_register_not_first_user(self) -> None:
        from apps.organization.services.auth.auth_service import AuthService
        svc = AuthService()
        with patch("apps.organization.services.auth.auth_service.Lawyer") as MockLawyer:
            MockLawyer.objects.exists.return_value = True
            with patch("apps.organization.services.auth.auth_service.settings") as mock_settings:
                mock_settings.ALLOW_FIRST_USER_SUPERUSER = False
                MockLawyer.objects.create_user.return_value = MagicMock()
                result = svc.register("user", "pass")
                assert result.user is not None

    @pytest.mark.django_db
    def test_register_bootstrap_token_required(self) -> None:
        from apps.organization.services.auth.auth_service import AuthService
        svc = AuthService()
        with patch("apps.organization.services.auth.auth_service.Lawyer") as MockLawyer:
            MockLawyer.objects.exists.return_value = False
            with patch("apps.organization.services.auth.auth_service.settings") as mock_settings:
                mock_settings.ALLOW_FIRST_USER_SUPERUSER = True
                mock_settings.DEBUG = False
                mock_settings.BOOTSTRAP_ADMIN_TOKEN = "secret_token"
                with pytest.raises(PermissionDenied, match="引导令牌"):
                    svc.register("admin", "pass", bootstrap_token="wrong")

    @pytest.mark.django_db
    def test_auto_register_not_first_user(self) -> None:
        from apps.organization.services.auth.auth_service import AuthService
        svc = AuthService()
        with patch("apps.organization.services.auth.auth_service.Lawyer") as MockLawyer:
            MockLawyer.objects.exists.return_value = True
            with pytest.raises(PermissionDenied, match="自动注册"):
                svc.auto_register_superadmin()

    @pytest.mark.django_db
    def test_auto_register_success(self) -> None:
        from apps.organization.services.auth.auth_service import AuthService
        svc = AuthService()
        with patch("apps.organization.services.auth.auth_service.Lawyer") as MockLawyer:
            MockLawyer.objects.exists.return_value = False
            MockLawyer.objects.create_user.return_value = MagicMock()
            result = svc.auto_register_superadmin()
            assert result.user is not None


# ── PasswordResetService ─────────────────────────────────────────────────


class TestPasswordResetService:
    def test_request_password_reset_no_user(self) -> None:
        from apps.organization.services.auth.password_reset_service import PasswordResetService
        with patch("apps.organization.services.auth.password_reset_service.Lawyer") as MockLawyer:
            MockLawyer.objects.filter.return_value.first.return_value = None
            success, msg = PasswordResetService.request_password_reset("noexist@test.com")
            assert success is True
            assert "发送重置链接" in msg

    @patch("apps.organization.services.auth.password_reset_service.cache")
    def test_request_password_reset_rate_limited(self, mock_cache: MagicMock) -> None:
        from apps.organization.services.auth.password_reset_service import PasswordResetService
        from django.utils import timezone
        mock_cache.get.return_value = timezone.now()  # within cooldown
        with patch("apps.organization.services.auth.password_reset_service.Lawyer") as MockLawyer:
            mock_user = MagicMock()
            mock_user.pk = 1
            MockLawyer.objects.filter.return_value.first.return_value = mock_user
            success, msg = PasswordResetService.request_password_reset("user@test.com")
            assert success is False
            assert "请稍后再试" in msg

    @patch("apps.organization.services.auth.password_reset_service.cache")
    @patch("apps.organization.services.auth.password_reset_service.EmailService")
    def test_request_password_reset_email_success(self, mock_email: MagicMock, mock_cache: MagicMock) -> None:
        from apps.organization.services.auth.password_reset_service import PasswordResetService
        mock_cache.get.return_value = None  # no rate limit
        mock_email.send_password_reset_email.return_value = True
        with patch("apps.organization.services.auth.password_reset_service.Lawyer") as MockLawyer:
            mock_user = MagicMock()
            mock_user.pk = 1
            mock_user.username = "testuser"
            mock_user.last_login = None
            MockLawyer.objects.filter.return_value.first.return_value = mock_user
            success, msg = PasswordResetService.request_password_reset("user@test.com")
            assert success is True

    @patch("apps.organization.services.auth.password_reset_service.cache")
    @patch("apps.organization.services.auth.password_reset_service.EmailService")
    def test_request_password_reset_email_failure(self, mock_email: MagicMock, mock_cache: MagicMock) -> None:
        from apps.organization.services.auth.password_reset_service import PasswordResetService
        mock_cache.get.return_value = None
        mock_email.send_password_reset_email.return_value = False
        with patch("apps.organization.services.auth.password_reset_service.Lawyer") as MockLawyer:
            mock_user = MagicMock()
            mock_user.pk = 1
            mock_user.username = "testuser"
            mock_user.last_login = None
            MockLawyer.objects.filter.return_value.first.return_value = mock_user
            success, msg = PasswordResetService.request_password_reset("user@test.com")
            assert success is False
            assert "邮件发送失败" in msg

    def test_verify_reset_token_invalid_uid(self) -> None:
        from apps.organization.services.auth.password_reset_service import PasswordResetService
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        # Use a valid base64 but non-existent user ID
        uid = urlsafe_base64_encode(force_bytes(999999))
        with patch("apps.organization.services.auth.password_reset_service.Lawyer") as MockLawyer:
            MockLawyer.objects.filter.return_value.first.return_value = None
            valid, user, msg = PasswordResetService.verify_reset_token(uid, "token")
            assert valid is False
            assert user is None

    def test_verify_reset_token_invalid_token(self) -> None:
        from apps.organization.services.auth.password_reset_service import PasswordResetService
        with patch("apps.organization.services.auth.password_reset_service.Lawyer") as MockLawyer, \
             patch("apps.organization.services.auth.password_reset_service.password_reset_token_generator") as mock_gen:
            mock_user = MagicMock()
            mock_user.pk = 1
            MockLawyer.objects.filter.return_value.first.return_value = mock_user
            mock_gen.check_token.return_value = False
            valid, user, msg = PasswordResetService.verify_reset_token("MQ==", "bad_token")
            assert valid is False

    def test_verify_reset_token_valid(self) -> None:
        from apps.organization.services.auth.password_reset_service import PasswordResetService
        with patch("apps.organization.services.auth.password_reset_service.Lawyer") as MockLawyer, \
             patch("apps.organization.services.auth.password_reset_service.password_reset_token_generator") as mock_gen:
            mock_user = MagicMock()
            mock_user.pk = 1
            MockLawyer.objects.filter.return_value.first.return_value = mock_user
            mock_gen.check_token.return_value = True
            valid, user, msg = PasswordResetService.verify_reset_token("MQ==", "good_token")
            assert valid is True
            assert user is mock_user

    def test_reset_password_invalid_token(self) -> None:
        from apps.organization.services.auth.password_reset_service import PasswordResetService
        with patch("apps.organization.services.auth.password_reset_service.PasswordResetService.verify_reset_token") as mock_verify:
            mock_verify.return_value = (False, None, "invalid")
            success, msg = PasswordResetService.reset_password("uid", "token", "new_pass")
            assert success is False

    def test_reset_password_success(self) -> None:
        from apps.organization.services.auth.password_reset_service import PasswordResetService
        with patch("apps.organization.services.auth.password_reset_service.PasswordResetService.verify_reset_token") as mock_verify, \
             patch("apps.organization.services.auth.password_reset_service.EmailService") as mock_email:
            mock_user = MagicMock()
            mock_user.email = "user@test.com"
            mock_user.username = "testuser"
            mock_verify.return_value = (True, mock_user, "valid")
            success, msg = PasswordResetService.reset_password("uid", "token", "new_pass")
            assert success is True
            mock_user.set_password.assert_called_once_with("new_pass")
            mock_user.save.assert_called_once()

    def test_reset_password_no_email(self) -> None:
        from apps.organization.services.auth.password_reset_service import PasswordResetService
        with patch("apps.organization.services.auth.password_reset_service.PasswordResetService.verify_reset_token") as mock_verify, \
             patch("apps.organization.services.auth.password_reset_service.EmailService") as mock_email:
            mock_user = MagicMock()
            mock_user.email = None
            mock_user.username = "testuser"
            mock_verify.return_value = (True, mock_user, "valid")
            success, msg = PasswordResetService.reset_password("uid", "token", "new_pass")
            assert success is True
            mock_email.send_password_changed_notification.assert_not_called()


# ── OrganizationServiceAdapter ───────────────────────────────────────────


class TestOrganizationServiceAdapter:
    def test_lazy_properties(self) -> None:
        from apps.organization.services.organization_service_adapter import OrganizationServiceAdapter
        adapter = OrganizationServiceAdapter()
        # Access properties to trigger lazy init
        _ = adapter.lawfirm_service
        _ = adapter.team_service
        _ = adapter.lawyer_service

    def test_get_law_firm_found(self) -> None:
        from apps.organization.services.organization_service_adapter import OrganizationServiceAdapter
        adapter = OrganizationServiceAdapter()
        mock_lawfirm = MagicMock()
        adapter._lawfirm_service = MagicMock()
        adapter._lawfirm_service.get_lawfirm_by_id.return_value = mock_lawfirm
        with patch("apps.organization.services.organization_service_adapter.LawFirmDTO") as MockDTO:
            MockDTO.from_model.return_value = MagicMock()
            result = adapter.get_law_firm(1)
            assert result is not None

    def test_get_law_firm_not_found(self) -> None:
        from apps.organization.services.organization_service_adapter import OrganizationServiceAdapter
        adapter = OrganizationServiceAdapter()
        adapter._lawfirm_service = MagicMock()
        adapter._lawfirm_service.get_lawfirm_by_id.return_value = None
        result = adapter.get_law_firm(999)
        assert result is None

    def test_get_team_found(self) -> None:
        from apps.organization.services.organization_service_adapter import OrganizationServiceAdapter
        adapter = OrganizationServiceAdapter()
        adapter._team_service = MagicMock()
        mock_team = MagicMock()
        adapter._team_service.get_team.return_value = mock_team
        with patch("apps.organization.services.organization_service_adapter.TeamDTO") as MockDTO:
            MockDTO.from_model.return_value = MagicMock()
            result = adapter.get_team(1)
            assert result is not None

    def test_get_team_not_found(self) -> None:
        from apps.organization.services.organization_service_adapter import OrganizationServiceAdapter
        adapter = OrganizationServiceAdapter()
        adapter._team_service = MagicMock()
        adapter._team_service.get_team.side_effect = NotFoundError("not found")
        result = adapter.get_team(999)
        assert result is None

    def test_get_default_lawyer_id_admin(self) -> None:
        from apps.organization.services.organization_service_adapter import OrganizationServiceAdapter
        adapter = OrganizationServiceAdapter()
        adapter._lawyer_service = MagicMock()
        mock_admin = MagicMock()
        mock_admin.id = 5
        adapter._lawyer_service.get_lawyer_queryset.return_value.filter.return_value.order_by.return_value.first.return_value = mock_admin
        result = adapter.get_default_lawyer_id()
        assert result == 5

    def test_get_default_lawyer_id_fallback(self) -> None:
        from apps.organization.services.organization_service_adapter import OrganizationServiceAdapter
        adapter = OrganizationServiceAdapter()
        adapter._lawyer_service = MagicMock()
        # No admin found
        adapter._lawyer_service.get_lawyer_queryset.return_value.filter.return_value.order_by.return_value.first.return_value = None
        mock_lawyer = MagicMock()
        mock_lawyer.id = 1
        adapter._lawyer_service.get_lawyer_queryset.return_value.order_by.return_value.first.return_value = mock_lawyer
        result = adapter.get_default_lawyer_id()
        assert result == 1

    def test_get_default_lawyer_id_none(self) -> None:
        from apps.organization.services.organization_service_adapter import OrganizationServiceAdapter
        adapter = OrganizationServiceAdapter()
        adapter._lawyer_service = MagicMock()
        adapter._lawyer_service.get_lawyer_queryset.return_value.filter.return_value.order_by.return_value.first.return_value = None
        adapter._lawyer_service.get_lawyer_queryset.return_value.order_by.return_value.first.return_value = None
        result = adapter.get_default_lawyer_id()
        assert result is None

    def test_has_credential_for_lawyer(self) -> None:
        from apps.organization.services.organization_service_adapter import OrganizationServiceAdapter
        adapter = OrganizationServiceAdapter()
        adapter._account_credential_service = MagicMock()
        mock_cred = MagicMock()
        mock_cred.lawyer_id = 1
        adapter._account_credential_service.get_credentials_by_site.return_value = [mock_cred]
        result = adapter.has_credential_for_lawyer(1, "site")
        assert result is True

    def test_get_credential_for_lawyer_found(self) -> None:
        from apps.organization.services.organization_service_adapter import OrganizationServiceAdapter
        adapter = OrganizationServiceAdapter()
        adapter._account_credential_service = MagicMock()
        mock_cred = MagicMock()
        mock_cred.lawyer_id = 1
        adapter._account_credential_service.get_credentials_by_site.return_value = [mock_cred]
        with patch("apps.organization.services.organization_service_adapter.AccountCredentialDTO") as MockDTO:
            MockDTO.from_model.return_value = MagicMock(lawyer_id=1)
            result = adapter.get_credential_for_lawyer(1, "site")
            assert result is not None

    def test_get_credential_for_lawyer_not_found(self) -> None:
        from apps.organization.services.organization_service_adapter import OrganizationServiceAdapter
        adapter = OrganizationServiceAdapter()
        adapter._account_credential_service = MagicMock()
        mock_cred = MagicMock()
        mock_cred.lawyer_id = 2
        adapter._account_credential_service.get_credentials_by_site.return_value = [mock_cred]
        with patch("apps.organization.services.organization_service_adapter.AccountCredentialDTO") as MockDTO:
            MockDTO.from_model.return_value = MagicMock(lawyer_id=2)
            result = adapter.get_credential_for_lawyer(1, "site")
            assert result is None

    def test_internal_methods(self) -> None:
        from apps.organization.services.organization_service_adapter import OrganizationServiceAdapter
        adapter = OrganizationServiceAdapter()
        adapter._account_credential_service = MagicMock()
        adapter._account_credential_service.list_all_credentials.return_value = []
        adapter._account_credential_service.list_sites_for_lawyer.return_value = []

        assert adapter.get_all_credentials_internal() == []
        assert adapter.list_sites_for_lawyer(1) == []
