"""Finance Admin 测试 - LPRRateAdmin"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.finance.admin.lpr_admin import LPRRateAdmin
from apps.finance.models.lpr_rate import LPRRate

User = get_user_model()


def _make_request(path: str = "/admin/") -> Any:
    factory = RequestFactory()
    request = factory.get(path)
    request.user = User(is_superuser=True, is_staff=True)
    return request


@pytest.mark.django_db
class TestFinanceLPRRateAdmin:
    """Finance LPRRateAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = LPRRateAdmin(LPRRate, AdminSite())
        assert "effective_date" in admin_obj.list_display
        assert "rate_1y" in admin_obj.list_display
        assert "rate_5y" in admin_obj.list_display
        assert "is_auto_synced" in admin_obj.list_display

    def test_list_filter(self) -> None:
        """list_filter 包含 effective_date"""
        admin_obj = LPRRateAdmin(LPRRate, AdminSite())
        assert "effective_date" in admin_obj.list_filter

    def test_ordering(self) -> None:
        """排序应按 effective_date 降序"""
        admin_obj = LPRRateAdmin(LPRRate, AdminSite())
        assert admin_obj.ordering == ("-effective_date",)

    def test_has_add_permission_disabled(self) -> None:
        """禁用手动添加"""
        admin_obj = LPRRateAdmin(LPRRate, AdminSite())
        assert admin_obj.has_add_permission(_make_request()) is False

    def test_has_change_permission_disabled(self) -> None:
        """禁用修改"""
        admin_obj = LPRRateAdmin(LPRRate, AdminSite())
        assert admin_obj.has_change_permission(_make_request()) is False

    def test_has_delete_permission_disabled(self) -> None:
        """禁用删除"""
        admin_obj = LPRRateAdmin(LPRRate, AdminSite())
        assert admin_obj.has_delete_permission(_make_request()) is False
