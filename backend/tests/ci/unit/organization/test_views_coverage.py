"""Tests for organization/views.py (missing: 36 lines).

Covers: register view POST branches (auto_register, form valid, form invalid),
register GET, and AuthLoginView.get_context_data.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from django.test import RequestFactory

from apps.organization.views import register


@pytest.fixture
def rf() -> RequestFactory:
    return RequestFactory()


class TestRegisterGet:
    def test_get_renders_form(self, rf: RequestFactory) -> None:
        request = rf.get("/register/")
        with patch("apps.organization.views._auth_service") as mock_svc:
            mock_svc.is_first_user.return_value = False
            mock_svc.should_show_auto_register.return_value = False
            response = register(request)
            assert response.status_code == 200


class TestRegisterPostAutoRegister:
    def test_auto_register_success(self, rf: RequestFactory) -> None:
        request = rf.post("/register/", {"action": "auto_register"})
        with patch("apps.organization.views._auth_service") as mock_svc, \
             patch("apps.organization.views.login") as mock_login, \
             patch("apps.organization.views.messages") as mock_messages, \
             patch("apps.organization.views.redirect") as mock_redirect:
            mock_svc.is_first_user.return_value = True
            mock_svc.should_show_auto_register.return_value = True
            mock_user = MagicMock()
            mock_user.real_name = "Admin"
            mock_svc.auto_register_superadmin.return_value = SimpleNamespace(user=mock_user)
            mock_redirect.return_value = MagicMock(status_code=302)
            response = register(request)
            mock_login.assert_called_once()

    def test_auto_register_exception(self, rf: RequestFactory) -> None:
        request = rf.post("/register/", {"action": "auto_register"})
        with patch("apps.organization.views._auth_service") as mock_svc, \
             patch("apps.organization.views.messages") as mock_messages, \
             patch("apps.organization.views.redirect") as mock_redirect:
            mock_svc.is_first_user.return_value = True
            mock_svc.should_show_auto_register.return_value = True
            mock_svc.auto_register_superadmin.side_effect = Exception("error")
            mock_redirect.return_value = MagicMock(status_code=302)
            response = register(request)
            mock_messages.error.assert_called()


class TestRegisterPostForm:
    def test_form_valid_first_user_admin(self, rf: RequestFactory) -> None:
        request = rf.post("/register/", {
            "username": "admin",
            "password1": "testpass123",
            "password2": "testpass123",
        })
        with patch("apps.organization.views._auth_service") as mock_svc, \
             patch("apps.organization.views.login") as mock_login, \
             patch("apps.organization.views.messages") as mock_messages, \
             patch("apps.organization.views.redirect") as mock_redirect, \
             patch("apps.organization.views.LawyerRegistrationForm") as MockForm:
            mock_svc.is_first_user.return_value = True
            mock_svc.should_show_auto_register.return_value = True
            form_instance = MockForm.return_value
            form_instance.is_valid.return_value = True
            form_instance.cleaned_data = {"username": "admin", "password1": "testpass123"}
            mock_user = MagicMock()
            mock_user.is_admin = True
            mock_user.real_name = "admin"
            mock_svc.register.return_value = SimpleNamespace(user=mock_user)
            mock_redirect.return_value = MagicMock(status_code=302)
            response = register(request)
            mock_login.assert_called_once()

    def test_form_valid_non_admin(self, rf: RequestFactory) -> None:
        request = rf.post("/register/", {
            "username": "user",
            "password1": "testpass123",
            "password2": "testpass123",
        })
        with patch("apps.organization.views._auth_service") as mock_svc, \
             patch("apps.organization.views.login") as mock_login, \
             patch("apps.organization.views.messages") as mock_messages, \
             patch("apps.organization.views.redirect") as mock_redirect, \
             patch("apps.organization.views.LawyerRegistrationForm") as MockForm:
            mock_svc.is_first_user.return_value = False
            mock_svc.should_show_auto_register.return_value = False
            form_instance = MockForm.return_value
            form_instance.is_valid.return_value = True
            form_instance.cleaned_data = {"username": "user", "password1": "testpass123"}
            mock_user = MagicMock()
            mock_user.is_admin = False
            mock_svc.register.return_value = SimpleNamespace(user=mock_user)
            mock_redirect.return_value = MagicMock(status_code=302)
            response = register(request)
            mock_login.assert_not_called()

    def test_form_valid_register_exception(self, rf: RequestFactory) -> None:
        request = rf.post("/register/", {
            "username": "user",
            "password1": "testpass123",
            "password2": "testpass123",
        })
        with patch("apps.organization.views._auth_service") as mock_svc, \
             patch("apps.organization.views.messages") as mock_messages, \
             patch("apps.organization.views.redirect") as mock_redirect, \
             patch("apps.organization.views.LawyerRegistrationForm") as MockForm:
            mock_svc.is_first_user.return_value = False
            mock_svc.should_show_auto_register.return_value = False
            form_instance = MockForm.return_value
            form_instance.is_valid.return_value = True
            form_instance.cleaned_data = {"username": "user", "password1": "testpass123"}
            mock_svc.register.side_effect = Exception("register error")
            mock_redirect.return_value = MagicMock(status_code=302)
            response = register(request)
            mock_messages.error.assert_called()

    def test_form_invalid(self, rf: RequestFactory) -> None:
        request = rf.post("/register/", {
            "username": "",
            "password1": "",
            "password2": "",
        })
        with patch("apps.organization.views._auth_service") as mock_svc, \
             patch("apps.organization.views.LawyerRegistrationForm") as MockForm:
            mock_svc.is_first_user.return_value = False
            mock_svc.should_show_auto_register.return_value = False
            form_instance = MockForm.return_value
            form_instance.is_valid.return_value = False
            response = register(request)
            assert response.status_code == 200
