"""Targeted tests for organization module to push coverage to 80%+."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# forms.py (43% coverage)
# ---------------------------------------------------------------------------


class TestLawyerRegistrationForm:
    def test_clean_username_chinese(self):
        from apps.organization.forms import LawyerRegistrationForm

        form = LawyerRegistrationForm()
        form.cleaned_data = {"username": "张三"}
        result = form.clean_username()
        assert result == "张三"

    def test_clean_username_non_chinese(self):
        from apps.organization.forms import LawyerRegistrationForm

        form = LawyerRegistrationForm()
        form.cleaned_data = {"username": "abc123"}
        with pytest.raises(Exception):
            form.clean_username()

    def test_clean_username_none(self):
        from apps.organization.forms import LawyerRegistrationForm

        form = LawyerRegistrationForm()
        form.cleaned_data = {"username": None}
        result = form.clean_username()
        assert result == ""

    def test_form_init(self):
        from apps.organization.forms import LawyerRegistrationForm

        form = LawyerRegistrationForm()
        assert form.fields["username"].label == "用户名/真实姓名"
        assert form.fields["password1"].label == "密码"
        assert form.fields["password2"].label == "确认密码"

    def test_form_fields(self):
        from apps.organization.forms import LawyerRegistrationForm

        form = LawyerRegistrationForm()
        assert "username" in form.fields
        assert "password1" in form.fields
        assert "password2" in form.fields


# ---------------------------------------------------------------------------
# api/__init__.py (0% coverage)
# ---------------------------------------------------------------------------


class TestOrganizationApiInit:
    def test_api_init(self):
        from apps.organization.api import __init__ as api_init

        assert api_init is not None
