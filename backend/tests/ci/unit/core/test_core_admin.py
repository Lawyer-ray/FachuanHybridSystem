"""Core Admin 测试 - SystemConfigAdmin, CourtAdmin, CauseOfActionAdmin"""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.core.admin.cause_of_action_admin import CauseOfActionAdmin
from apps.core.admin.court_admin import CourtAdmin
from apps.core.admin.document_parse_provider_admin import DocumentParseProviderAdmin
from apps.core.admin.llm_provider_admin import LLMProviderAdmin
from apps.core.admin.system_config_admin import SystemConfigAdmin
from apps.core.models import CauseOfAction, Court, DocumentParseProvider, LLMProvider, SystemConfig

User = get_user_model()


def _make_request(path: str = "/admin/") -> Any:
    factory = RequestFactory()
    request = factory.get(path)
    request.user = User(is_superuser=True, is_staff=True)
    return request


@pytest.mark.django_db
class TestSystemConfigAdmin:
    """SystemConfigAdmin 测试"""

    def test_category_choices_keep_onlyoffice(self) -> None:
        """`onlyoffice` 分类必须留在枚举里。

        0036 加过，0038（删 docspace 时整份重写 choices）误删 → 3 条 ONLYOFFICE_* 活配置
        分类值变非法，admin 列表页不显示、编辑页下拉里没有当前值（一保存就被改分类）。
        0042 已恢复，这条测试防止再被"整份复制旧列表"式改动抹掉。
        """
        assert "onlyoffice" in SystemConfig.Category.values
        assert dict(SystemConfig.Category.choices)["onlyoffice"] == "OnlyOffice 编辑器配置"

    def test_list_helpers_removed(self) -> None:
        """列表页 result_list 整块重写后，list_display / list_filter / 两个展示方法都不需要了。

        留着只会制造「看似生效、其实没人调用」的死代码：旧版 category_display 27 行全仓无
        调用者，list_filter 的侧栏还被 CSS 隐藏、每次加载仍白跑两次 DISTINCT 查询。
        值列的展示口径已收进 security 层（value_cell），单测见
        test_system_config_stored_value.py::TestValueCell。
        """
        admin_obj = SystemConfigAdmin(SystemConfig, AdminSite())

        assert not hasattr(admin_obj, "category_display")
        assert not hasattr(admin_obj, "masked_value")
        assert admin_obj.list_display == ("__str__",)
        assert admin_obj.list_filter == ()


@pytest.mark.django_db
class TestCourtAdmin:
    """CourtAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = CourtAdmin(Court, AdminSite())
        assert "code" in admin_obj.list_display
        assert "name" in admin_obj.list_display
        assert "level" in admin_obj.list_display

    def test_list_select_related(self) -> None:
        """list_select_related 包含 parent"""
        admin_obj = CourtAdmin(Court, AdminSite())
        assert "parent" in admin_obj.list_select_related

    def test_get_queryset_select_related_deep(self) -> None:
        """get_queryset 应使用多级 select_related"""
        court1 = Court.objects.create(code="000001", name="最高法院", level=1, is_active=True)
        court2 = Court.objects.create(code="110000", name="北京高院", level=2, parent=court1, is_active=True)
        court3 = Court.objects.create(code="110100", name="北京一中院", level=3, parent=court2, is_active=True)

        admin_obj = CourtAdmin(Court, AdminSite())
        qs = admin_obj.get_queryset(_make_request())
        results = list(qs)
        assert len(results) == 3

    def test_has_add_permission_disabled(self) -> None:
        """禁用手动添加"""
        admin_obj = CourtAdmin(Court, AdminSite())
        assert admin_obj.has_add_permission(_make_request()) is False

    def test_has_delete_permission_disabled(self) -> None:
        """禁用删除"""
        admin_obj = CourtAdmin(Court, AdminSite())
        assert admin_obj.has_delete_permission(_make_request()) is False

    def test_parent_display_with_parent(self) -> None:
        """parent_display 应显示父级法院名称"""
        parent = Court.objects.create(code="000001", name="父级法院", level=1, is_active=True)
        child = Court.objects.create(code="000002", name="子级法院", level=2, parent=parent, is_active=True)

        admin_obj = CourtAdmin(Court, AdminSite())
        result = admin_obj.parent_display(child)
        assert "父级法院" in result

    def test_parent_display_without_parent(self) -> None:
        """parent_display 无父级时应显示破折号"""
        court = Court.objects.create(code="000003", name="顶级法院", level=1, is_active=True)

        admin_obj = CourtAdmin(Court, AdminSite())
        result = admin_obj.parent_display(court)
        assert "—" in result

    def test_status_display_active(self) -> None:
        """status_display 应显示正常状态"""
        court = Court.objects.create(code="000004", name="正常法院", level=1, is_active=True)

        admin_obj = CourtAdmin(Court, AdminSite())
        result = admin_obj.status_display(court)
        assert "正常" in result

    def test_status_display_inactive(self) -> None:
        """status_display 应显示禁用状态"""
        court = Court.objects.create(code="000005", name="禁用法院", level=1, is_active=False)

        admin_obj = CourtAdmin(Court, AdminSite())
        result = admin_obj.status_display(court)
        assert "已禁用" in result


@pytest.mark.django_db
class TestCauseOfActionAdmin:
    """CauseOfActionAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = CauseOfActionAdmin(CauseOfAction, AdminSite())
        assert "code" in admin_obj.list_display
        assert "name" in admin_obj.list_display
        assert "case_type_display" in admin_obj.list_display
        assert "level" in admin_obj.list_display

    def test_get_queryset_select_related(self) -> None:
        """get_queryset 应使用 select_related"""
        parent = CauseOfAction.objects.create(code="01", name="一级案由", case_type="civil", level=1, is_active=True)
        child = CauseOfAction.objects.create(
            code="0101", name="二级案由", case_type="civil", level=2, parent=parent, is_active=True
        )

        admin_obj = CauseOfActionAdmin(CauseOfAction, AdminSite())
        qs = admin_obj.get_queryset(_make_request())
        results = list(qs)
        assert len(results) == 2

    def test_has_add_permission_disabled(self) -> None:
        """禁用手动添加"""
        admin_obj = CauseOfActionAdmin(CauseOfAction, AdminSite())
        assert admin_obj.has_add_permission(_make_request()) is False

    def test_has_delete_permission_disabled(self) -> None:
        """禁用删除"""
        admin_obj = CauseOfActionAdmin(CauseOfAction, AdminSite())
        assert admin_obj.has_delete_permission(_make_request()) is False

    def test_case_type_display(self) -> None:
        """case_type_display 应返回带颜色的标签"""
        coa = CauseOfAction.objects.create(code="01", name="民事案由", case_type="civil", level=1, is_active=True)

        admin_obj = CauseOfActionAdmin(CauseOfAction, AdminSite())
        result = admin_obj.case_type_display(coa)
        assert "background-color" in result

    def test_parent_display_with_parent(self) -> None:
        """parent_display 应显示父级案由名称"""
        parent = CauseOfAction.objects.create(code="01", name="父级案由", case_type="civil", level=1, is_active=True)
        child = CauseOfAction.objects.create(
            code="0101", name="子级案由", case_type="civil", level=2, parent=parent, is_active=True
        )

        admin_obj = CauseOfActionAdmin(CauseOfAction, AdminSite())
        result = admin_obj.parent_display(child)
        assert "父级案由" in result

    def test_parent_display_without_parent(self) -> None:
        """parent_display 无父级时应显示破折号"""
        coa = CauseOfAction.objects.create(code="01", name="顶级案由", case_type="civil", level=1, is_active=True)

        admin_obj = CauseOfActionAdmin(CauseOfAction, AdminSite())
        result = admin_obj.parent_display(coa)
        assert "—" in result

    def test_status_display_active(self) -> None:
        """status_display 应显示正常状态"""
        coa = CauseOfAction.objects.create(code="01", name="正常案由", case_type="civil", level=1, is_active=True)

        admin_obj = CauseOfActionAdmin(CauseOfAction, AdminSite())
        result = admin_obj.status_display(coa)
        assert "正常" in result

    def test_status_display_deprecated(self) -> None:
        """status_display 应显示废弃状态"""
        coa = CauseOfAction.objects.create(
            code="01", name="废弃案由", case_type="civil", level=1, is_active=True, is_deprecated=True
        )

        admin_obj = CauseOfActionAdmin(CauseOfAction, AdminSite())
        result = admin_obj.status_display(coa)
        assert "已废弃" in result


@pytest.mark.django_db
class TestLLMProviderAdminCredentials:
    """安全审计：api_keys 明文不回显，留空=不修改"""

    def _make_admin(self) -> LLMProviderAdmin:
        return LLMProviderAdmin(LLMProvider, AdminSite())

    def test_change_form_initial_blanks_api_keys(self) -> None:
        """编辑页 initial 不回填明文 Key（EncryptedTextField 透明解密不再进 HTML）"""
        provider = LLMProvider.objects.create(
            name="回显测试平台",
            base_url="http://gw.example/v1",
            api_keys="sk-secret-echo",  # pragma: allowlist secret
        )
        admin_obj = self._make_admin()

        initial = admin_obj.get_changeform_initial_data(_make_request())

        assert initial["api_keys"] == ""
        # 表单渲染不含明文 Key
        form_class = admin_obj.get_form(_make_request(), obj=provider)
        form = form_class(initial=initial, instance=provider)
        assert "sk-secret-echo" not in form.as_p()

    def test_save_model_blank_keeps_saved_keys(self) -> None:
        """编辑时 api_keys 留空 → 保留库中原值"""
        provider = LLMProvider.objects.create(
            name="留空测试平台",
            base_url="http://gw.example/v1",
            api_keys="sk-keep-me",  # pragma: allowlist secret
        )
        admin_obj = self._make_admin()

        provider.api_keys = ""
        form = type("F", (), {"cleaned_data": {"api_keys": ""}})()
        admin_obj.save_model(_make_request(), provider, form, change=True)
        provider.refresh_from_db()

        assert provider.api_keys == "sk-keep-me"  # pragma: allowlist secret

    def test_save_model_non_blank_updates_keys(self) -> None:
        """编辑时 api_keys 非空 → 更新为新值"""
        provider = LLMProvider.objects.create(
            name="更新测试平台",
            base_url="http://gw.example/v1",
            api_keys="sk-old-key",  # pragma: allowlist secret
        )
        admin_obj = self._make_admin()

        provider.api_keys = "sk-new-key"  # pragma: allowlist secret
        form = type("F", (), {"cleaned_data": {"api_keys": "sk-new-key"}})()  # pragma: allowlist secret
        admin_obj.save_model(_make_request(), provider, form, change=True)
        provider.refresh_from_db()

        assert provider.api_keys == "sk-new-key"  # pragma: allowlist secret


@pytest.mark.django_db
class TestDocumentParseProviderAdminCredentials:
    """安全审计：credentials 明文不回显、不进 search_fields，留空=不修改"""

    def _make_admin(self) -> DocumentParseProviderAdmin:
        return DocumentParseProviderAdmin(DocumentParseProvider, AdminSite())

    def test_search_fields_exclude_credentials(self) -> None:
        assert "credentials" not in self._make_admin().search_fields

    def test_change_form_initial_blanks_credentials(self) -> None:
        provider = DocumentParseProvider.objects.create(
            name="回显解析平台",
            provider_type="mineru",
            credentials="k-echo-secret",  # pragma: allowlist secret
        )
        admin_obj = self._make_admin()

        initial = admin_obj.get_changeform_initial_data(_make_request())

        assert initial["credentials"] == ""
        form_class = admin_obj.get_form(_make_request(), obj=provider)
        form = form_class(initial=initial, instance=provider)
        assert "k-echo-secret" not in form.as_p()

    def test_save_model_blank_keeps_saved_credentials(self) -> None:
        provider = DocumentParseProvider.objects.create(
            name="留空解析平台",
            provider_type="mineru",
            credentials="k-keep-me",  # pragma: allowlist secret
        )
        admin_obj = self._make_admin()

        provider.credentials = ""
        form = type("F", (), {"cleaned_data": {"credentials": ""}})()
        admin_obj.save_model(_make_request(), provider, form, change=True)
        provider.refresh_from_db()

        assert provider.credentials == "k-keep-me"

    def test_save_model_non_blank_updates_credentials(self) -> None:
        provider = DocumentParseProvider.objects.create(
            name="更新解析平台",
            provider_type="mineru",
            credentials="k-old",  # pragma: allowlist secret
        )
        admin_obj = self._make_admin()

        provider.credentials = "k-new"  # pragma: allowlist secret
        form = type("F", (), {"cleaned_data": {"credentials": "k-new"}})()  # pragma: allowlist secret
        admin_obj.save_model(_make_request(), provider, form, change=True)
        provider.refresh_from_db()

        assert provider.credentials == "k-new"  # pragma: allowlist secret
