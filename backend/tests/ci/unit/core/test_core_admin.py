"""Core Admin 测试 - SystemConfigAdmin, CourtAdmin, CauseOfActionAdmin"""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.core.admin.system_config_admin import SystemConfigAdmin
from apps.core.admin.court_admin import CourtAdmin
from apps.core.admin.cause_of_action_admin import CauseOfActionAdmin
from apps.core.models import CauseOfAction, Court, SystemConfig

User = get_user_model()


def _make_request(path: str = "/admin/") -> Any:
    factory = RequestFactory()
    request = factory.get(path)
    request.user = User(is_superuser=True, is_staff=True)
    return request


@pytest.mark.django_db
class TestSystemConfigAdmin:
    """SystemConfigAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = SystemConfigAdmin(SystemConfig, AdminSite())
        assert "key" in admin_obj.list_display
        assert "category_display" in admin_obj.list_display
        assert "masked_value" in admin_obj.list_display

    def test_list_filter(self) -> None:
        """list_filter 包含 category"""
        admin_obj = SystemConfigAdmin(SystemConfig, AdminSite())
        assert "category" in admin_obj.list_filter
        assert "is_secret" in admin_obj.list_filter

    def test_category_display_normal(self) -> None:
        """category_display 应返回带颜色的标签"""
        config = SystemConfig.objects.create(
            key="test_key", value="test_value", category="general", description="测试配置"
        )
        admin_obj = SystemConfigAdmin(SystemConfig, AdminSite())
        result = admin_obj.category_display(config)
        assert "background-color" in result

    def test_masked_value_non_secret(self) -> None:
        """非密钥配置应显示完整值"""
        config = SystemConfig.objects.create(
            key="test_key", value="short_value", category="general", description="测试配置", is_secret=False
        )
        admin_obj = SystemConfigAdmin(SystemConfig, AdminSite())
        result = admin_obj.masked_value(config)
        assert result == "short_value"

    def test_masked_value_secret(self) -> None:
        """密钥配置应显示脱敏值"""
        config = SystemConfig.objects.create(
            key="test_secret", value="super_secret_key_12345", category="general", description="密钥配置", is_secret=True
        )
        admin_obj = SystemConfigAdmin(SystemConfig, AdminSite())
        result = admin_obj.masked_value(config)
        # 应该包含遮罩字符
        assert "*" in result

    def test_masked_value_empty(self) -> None:
        """空值应显示'未设置'"""
        config = SystemConfig.objects.create(
            key="empty_key", value="", category="general", description="空配置"
        )
        admin_obj = SystemConfigAdmin(SystemConfig, AdminSite())
        result = admin_obj.masked_value(config)
        assert "未设置" in result

    def test_masked_value_long_non_secret(self) -> None:
        """长非密钥值应截断显示"""
        long_value = "a" * 100
        config = SystemConfig.objects.create(
            key="long_key", value=long_value, category="general", description="长配置", is_secret=False
        )
        admin_obj = SystemConfigAdmin(SystemConfig, AdminSite())
        result = admin_obj.masked_value(config)
        assert "..." in result


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
        parent = CauseOfAction.objects.create(
            code="01", name="一级案由", case_type="civil", level=1, is_active=True
        )
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
        coa = CauseOfAction.objects.create(
            code="01", name="民事案由", case_type="civil", level=1, is_active=True
        )

        admin_obj = CauseOfActionAdmin(CauseOfAction, AdminSite())
        result = admin_obj.case_type_display(coa)
        assert "background-color" in result

    def test_parent_display_with_parent(self) -> None:
        """parent_display 应显示父级案由名称"""
        parent = CauseOfAction.objects.create(
            code="01", name="父级案由", case_type="civil", level=1, is_active=True
        )
        child = CauseOfAction.objects.create(
            code="0101", name="子级案由", case_type="civil", level=2, parent=parent, is_active=True
        )

        admin_obj = CauseOfActionAdmin(CauseOfAction, AdminSite())
        result = admin_obj.parent_display(child)
        assert "父级案由" in result

    def test_parent_display_without_parent(self) -> None:
        """parent_display 无父级时应显示破折号"""
        coa = CauseOfAction.objects.create(
            code="01", name="顶级案由", case_type="civil", level=1, is_active=True
        )

        admin_obj = CauseOfActionAdmin(CauseOfAction, AdminSite())
        result = admin_obj.parent_display(coa)
        assert "—" in result

    def test_status_display_active(self) -> None:
        """status_display 应显示正常状态"""
        coa = CauseOfAction.objects.create(
            code="01", name="正常案由", case_type="civil", level=1, is_active=True
        )

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
