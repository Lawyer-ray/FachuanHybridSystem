"""Finance Admin 测试 - LPRRateAdmin"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory

from apps.finance.admin.lpr_admin import LPRRateAdmin
from apps.finance.models.lpr_rate import LPRRate

User = get_user_model()


def _make_request(path: str = "/admin/") -> Any:
    factory = RequestFactory()
    request = factory.get(path)
    request.user = User(is_superuser=True, is_staff=True)
    return request


def _make_sync_request(method: str = "post", user: Any = None) -> Any:
    factory = RequestFactory()
    request = getattr(factory, method)("/admin/finance/lprrate/sync/")
    request.user = user if user is not None else User(is_superuser=True, is_staff=True)
    # sync_view 会调 message_user，需要消息框架的存储后端
    request.session = "session"
    request._messages = FallbackStorage(request)
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


@pytest.mark.django_db
class TestLPRRateAdminSyncView:
    """sync_view 权限门回归（2026-10-20 修复：同步按钮 403）

    2026-10-19 安全审计给 sync_view 加了 has_change_permission 校验，而该方法在
    本 Admin 被写死返回 False（LPR 数据只读），导致同步入口对所有人 403。
    """

    def test_get_denied_even_for_superuser(self) -> None:
        """GET 一律拒绝（防跨站 <img> 诱导触发）"""
        admin_obj = LPRRateAdmin(LPRRate, AdminSite())
        with pytest.raises(PermissionDenied):
            admin_obj.sync_view(_make_request("/admin/finance/lprrate/sync/"))

    def test_post_without_change_perm_denied(self) -> None:
        """无 change_lprrate 权限的 staff 用户 POST 被拒"""
        staff = User.objects.create_user(username="lpr-staff", password="x", is_staff=True)
        admin_obj = LPRRateAdmin(LPRRate, AdminSite())
        with pytest.raises(PermissionDenied):
            admin_obj.sync_view(_make_sync_request(user=staff))

    def test_post_superuser_syncs_and_redirects(self) -> None:
        """superuser POST 放行执行同步并跳回列表页（回归：此前恒 403）"""
        admin_obj = LPRRateAdmin(LPRRate, AdminSite())
        with patch("apps.finance.services.lpr.LPRSyncService") as mock_svc:
            mock_svc.return_value.sync_latest.return_value = {
                "created": 1,
                "updated": 2,
                "skipped": 3,
            }
            response = admin_obj.sync_view(_make_sync_request())
        assert response.status_code == 302
        assert response["Location"] == "../"
        mock_svc.return_value.sync_latest.assert_called_once_with()
