"""Organization Admin 测试 - LawyerAdmin, LawFirmAdmin, TeamAdmin, AccountCredentialAdmin"""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.organization.admin.accountcredential_admin import AccountCredentialAdmin
from apps.organization.admin.lawfirm_admin import LawFirmAdmin
from apps.organization.admin.lawyer_admin import LawyerAdmin
from apps.organization.admin.team_admin import TeamAdmin
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
            phone="12000000000",
            law_firm=firm,
        )

        admin_obj = LawyerAdmin(Lawyer, AdminSite())
        result = admin_obj.serialize_queryset(Lawyer.objects.filter(pk=lawyer.pk))
        assert len(result) == 1
        assert result[0]["username"] == "serialize_lawyer"
        assert result[0]["real_name"] == "序列化律师"
        assert result[0]["phone"] == "12000000000"


@pytest.mark.django_db
class TestLawyerAdminSecurity:
    """LawyerAdmin 安全审计：密码哈希不回显 + 提权字段仅 superuser 可见可改"""

    def _make_non_superuser_request(self) -> Any:
        factory = RequestFactory()
        request = factory.get("/admin/organization/lawyer/")
        request.user = User(is_superuser=False, is_staff=True, is_admin=True)
        return request

    def test_password_field_removed_from_form_and_fieldsets(self) -> None:
        """password 不应出现在表单字段与 fieldsets 中（readonly widget 也会回显 PBKDF2 哈希）"""
        admin_obj = LawyerAdmin(Lawyer, AdminSite())

        from django.contrib.admin.helpers import flatten_fieldsets

        flattened = flatten_fieldsets(admin_obj.get_fieldsets(_make_request()))
        assert "password" not in flattened
        assert "new_password" in flattened

        form_class = admin_obj.get_form(_make_request())
        assert "password" not in form_class.base_fields
        assert "new_password" in form_class.base_fields

    def test_edit_form_does_not_echo_password_hash(self) -> None:
        """编辑既有律师：渲染的表单不包含密码哈希"""
        firm = LawFirm.objects.create(name="哈希回显测试律所")
        lawyer = Lawyer.objects.create_user(
            username="hash_echo_lawyer",
            real_name="哈希律师",
            law_firm=firm,
            password="secret-pass-123",  # pragma: allowlist secret
        )
        assert lawyer.password.startswith("pbkdf2_")

        admin_obj = LawyerAdmin(Lawyer, AdminSite())
        form_class = admin_obj.get_form(_make_request(), obj=lawyer)
        form = form_class(instance=lawyer)
        rendered = form.as_p()
        assert "pbkdf2_" not in rendered
        # 精确匹配字段名（new_password 的 autocomplete 属性含 "new-password"，不能笼统断言子串）
        assert 'name="password"' not in rendered

    def test_privileged_fields_hidden_for_non_superuser(self) -> None:
        """非 superuser：is_admin/is_staff/is_superuser 不出现在 fieldsets 与表单中"""
        admin_obj = LawyerAdmin(Lawyer, AdminSite())
        request = self._make_non_superuser_request()

        from django.contrib.admin.helpers import flatten_fieldsets

        flattened = flatten_fieldsets(admin_obj.get_fieldsets(request))
        for field in ("is_admin", "is_staff", "is_superuser"):
            assert field not in flattened

        form_class = admin_obj.get_form(request)
        for field in ("is_admin", "is_staff", "is_superuser"):
            assert field not in form_class.base_fields
        # 非提权字段仍可编辑
        assert "is_active" in form_class.base_fields

    def test_privileged_fields_visible_for_superuser(self) -> None:
        """superuser：提权字段照常可见"""
        admin_obj = LawyerAdmin(Lawyer, AdminSite())
        request = _make_request()

        form_class = admin_obj.get_form(request)
        for field in ("is_admin", "is_staff", "is_superuser"):
            assert field in form_class.base_fields

    def test_non_superuser_edit_keeps_privileged_flags_unchanged(self) -> None:
        """非 superuser 提交编辑：提权字段保持库中原值（不进表单即不会被覆盖）"""
        firm = LawFirm.objects.create(name="提权测试律所")
        team = Team.objects.create(name="提权律师团队", team_type="lawyer", law_firm=firm)
        Lawyer.objects.create_user(
            username="target_lawyer",
            real_name="目标律师",
            law_firm=firm,
            password="secret-pass-123",  # pragma: allowlist secret
            is_superuser=False,
            is_staff=False,
            is_admin=False,
        )
        target = Lawyer.objects.get(username="target_lawyer")

        admin_obj = LawyerAdmin(Lawyer, AdminSite())
        request = self._make_non_superuser_request()
        form_class = admin_obj.get_form(request, obj=target)

        post = RequestFactory().post(
            "/admin/organization/lawyer/",
            data={
                "username": "target_lawyer",
                "real_name": "改名律师",
                "is_active": "on",
                "lawyer_team": team.id,
                "is_superuser": "on",  # 恶意提交：字段已不在表单中，应被忽略
                "is_admin": "on",
                "is_staff": "on",
            },
        )
        post.user = request.user
        form = form_class(post.POST, instance=target)
        assert form.is_valid(), form.errors
        saved = form.save()
        saved.refresh_from_db()

        assert saved.is_superuser is False
        assert saved.is_admin is False
        assert saved.is_staff is False
        assert saved.real_name == "改名律师"


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
            lawyer=lawyer,
            site_name="test_site",
            account="test_account",
            password="test_pass",  # allowlist secret
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
            password="test_pass",  # allowlist secret
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
            password="test_pass",  # allowlist secret
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
            lawyer=lawyer,
            site_name="other_site",
            account="btn_account2",
            password="test_pass",  # allowlist secret
        )
        admin_obj = AccountCredentialAdmin(AccountCredential, AdminSite())
        result2 = admin_obj.auto_login_button(cred2)
        assert "不支持" in result2
