"""Organization Admin 测试 - LawyerAdmin, LawFirmAdmin, TeamAdmin, AccountCredentialAdmin"""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.organization.admin.lawyer_admin import LawyerAdmin
from apps.organization.admin.lawfirm_admin import LawFirmAdmin
from apps.organization.admin.team_admin import TeamAdmin
from apps.organization.admin.accountcredential_admin import AccountCredentialAdmin
from apps.organization.models import AccountCredential, LawFirm, Lawyer, Team

User = get_user_model()


def _make_request(path: str = "/admin/") -> Any:
    factory = RequestFactory()
    request = factory.get(path)
    request.user = User(is_superuser=True, is_staff=True)
    return request


@pytest.mark.django_db
class TestLawyerAdmin:
    """LawyerAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = LawyerAdmin(Lawyer, AdminSite())
        assert "id" in admin_obj.list_display
        assert "username" in admin_obj.list_display
        assert "real_name" in admin_obj.list_display
        assert "phone" in admin_obj.list_display
        assert "is_admin" in admin_obj.list_display
        assert "is_active" in admin_obj.list_display

    def test_search_fields(self) -> None:
        """search_fields 包含必要字段"""
        admin_obj = LawyerAdmin(Lawyer, AdminSite())
        assert "username" in admin_obj.search_fields
        assert "real_name" in admin_obj.search_fields

    def test_list_filter(self) -> None:
        """list_filter 包含必要字段"""
        admin_obj = LawyerAdmin(Lawyer, AdminSite())
        assert "is_admin" in admin_obj.list_filter
        assert "is_active" in admin_obj.list_filter

    def test_serialize_queryset(self) -> None:
        """serialize_queryset 应返回正确的数据结构"""
        firm = LawFirm.objects.create(name="序列化测试律所")
        lawyer = Lawyer.objects.create_user(
            username="serialize_lawyer",
            real_name="序列化律师",
            phone="13800138000",
            law_firm=firm,
        )

        admin_obj = LawyerAdmin(Lawyer, AdminSite())
        result = admin_obj.serialize_queryset(Lawyer.objects.filter(pk=lawyer.pk))
        assert len(result) == 1
        assert result[0]["username"] == "serialize_lawyer"
        assert result[0]["real_name"] == "序列化律师"
        assert result[0]["phone"] == "13800138000"


@pytest.mark.django_db
class TestLawFirmAdmin:
    """LawFirmAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = LawFirmAdmin(LawFirm, AdminSite())
        assert "id" in admin_obj.list_display
        assert "name" in admin_obj.list_display

    def test_search_fields(self) -> None:
        """search_fields 包含 name"""
        admin_obj = LawFirmAdmin(LawFirm, AdminSite())
        assert "name" in admin_obj.search_fields


@pytest.mark.django_db
class TestTeamAdmin:
    """TeamAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = TeamAdmin(Team, AdminSite())
        assert "id" in admin_obj.list_display
        assert "name" in admin_obj.list_display
        assert "team_type" in admin_obj.list_display

    def test_list_filter(self) -> None:
        """list_filter 包含 team_type"""
        admin_obj = TeamAdmin(Team, AdminSite())
        assert "team_type" in admin_obj.list_filter


@pytest.mark.django_db
class TestAccountCredentialAdmin:
    """AccountCredentialAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = AccountCredentialAdmin(AccountCredential, AdminSite())
        assert "id" in admin_obj.list_display
        assert "lawyer" in admin_obj.list_display
        assert "site_name" in admin_obj.list_display
        assert "account" in admin_obj.list_display

    def test_get_queryset_select_related(self) -> None:
        """get_queryset 应使用 select_related"""
        firm = LawFirm.objects.create(name="凭证测试律所")
        lawyer = Lawyer.objects.create_user(username="cred_lawyer", real_name="凭证律师", law_firm=firm)
        AccountCredential.objects.create(
            lawyer=lawyer, site_name="test_site", account="test_account", password="test_pass"
        )

        admin_obj = AccountCredentialAdmin(AccountCredential, AdminSite())
        qs = admin_obj.get_queryset(_make_request())
        results = list(qs)
        assert len(results) == 1
        assert results[0].lawyer.username == "cred_lawyer"

    def test_login_statistics_display(self) -> None:
        """login_statistics_display 应返回格式化 HTML"""
        firm = LawFirm.objects.create(name="统计测试律所")
        lawyer = Lawyer.objects.create_user(username="stat_lawyer", real_name="统计律师", law_firm=firm)
        cred = AccountCredential.objects.create(
            lawyer=lawyer,
            site_name="test_site",
            account="stat_account",
            password="test_pass",
            login_success_count=10,
            login_failure_count=2,
        )

        admin_obj = AccountCredentialAdmin(AccountCredential, AdminSite())
        result = admin_obj.login_statistics_display(cred)
        assert "10" in result
        assert "2" in result

    def test_success_rate_display(self) -> None:
        """success_rate_display 应返回格式化的成功率"""
        firm = LawFirm.objects.create(name="成功率测试律所")
        lawyer = Lawyer.objects.create_user(username="rate_lawyer", real_name="成功率律师", law_firm=firm)
        cred = AccountCredential.objects.create(
            lawyer=lawyer,
            site_name="test_site",
            account="rate_account",
            password="test_pass",
            login_success_count=8,
            login_failure_count=2,
        )

        admin_obj = AccountCredentialAdmin(AccountCredential, AdminSite())
        result = admin_obj.success_rate_display(cred)
        assert "80.0%" in result

    def test_auto_login_button(self) -> None:
        """auto_login_button 应返回正确的链接"""
        firm = LawFirm.objects.create(name="按钮测试律所")
        lawyer = Lawyer.objects.create_user(username="btn_lawyer", real_name="按钮律师", law_firm=firm)

        # 其他站点应返回"不支持"
        cred2 = AccountCredential.objects.create(
            lawyer=lawyer, site_name="other_site", account="btn_account2", password="test_pass"
        )
        admin_obj = AccountCredentialAdmin(AccountCredential, AdminSite())
        result2 = admin_obj.auto_login_button(cred2)
        assert "不支持" in result2
