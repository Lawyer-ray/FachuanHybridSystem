"""CourtSMSAdmin add 页面虚拟字段回归测试。

覆盖 Django 6.1 中 _changeform_view 会将 get_fieldsets() 扁平化后以
fields= 显式传给 get_form 的行为，防止虚拟字段 sfdw_phone_tail6 触发
Unknown field(s) FieldError。
"""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.admin.utils import flatten_fieldsets
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.automation.admin.sms.court_sms_admin import CourtSMSAdmin
from apps.automation.models import CourtSMS

User = get_user_model()


def _make_add_request() -> Any:
    request = RequestFactory().get("/admin/automation/courtsms/add/")
    request.user = User(is_superuser=True, is_staff=True)
    return request


@pytest.mark.django_db
class TestCourtSMSAdminAddForm:
    """CourtSMSAdmin add 页面虚拟字段回归测试"""

    def test_add_get_form_injects_virtual_field(self) -> None:
        """add 页 get_form 应注入虚拟字段 sfdw_phone_tail6"""
        admin_obj = CourtSMSAdmin(CourtSMS, AdminSite())
        form_cls = admin_obj.get_form(_make_add_request(), obj=None, change=False)
        assert "sfdw_phone_tail6" in form_cls.base_fields

    def test_add_get_form_with_flattened_fieldset(self) -> None:
        """Django 6.1 显式传扁平化字段组时不抛 FieldError"""
        admin_obj = CourtSMSAdmin(CourtSMS, AdminSite())
        request = _make_add_request()
        fieldset_fields = flatten_fieldsets(admin_obj.get_fieldsets(request, None))
        assert "sfdw_phone_tail6" in fieldset_fields

        form_cls = admin_obj.get_form(request, obj=None, change=False, fields=fieldset_fields)
        readonly = set(admin_obj.get_readonly_fields(request, None))
        resolvable = set(form_cls.base_fields) | readonly
        assert set(fieldset_fields) <= resolvable
