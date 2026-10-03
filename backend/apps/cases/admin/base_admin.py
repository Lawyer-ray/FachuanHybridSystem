from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import admin

if TYPE_CHECKING:
    from typing import TypeAlias

    BaseModelAdmin: TypeAlias = admin.ModelAdmin
    BaseStackedInline: TypeAlias = admin.StackedInline[Any, Any]
    BaseTabularInline: TypeAlias = admin.TabularInline[Any, Any]
else:
    try:
        import nested_admin

        BaseModelAdmin = nested_admin.NestedModelAdmin
        BaseStackedInline = nested_admin.NestedStackedInline
        BaseTabularInline = nested_admin.NestedTabularInline
    except ImportError:
        BaseModelAdmin = admin.ModelAdmin
        BaseStackedInline = admin.StackedInline
        BaseTabularInline = admin.TabularInline


def get_admin_accessible_case_queryset(request: Any) -> Any:
    """当前请求用户在 admin 中可访问的 Case queryset（复用 CaseAdmin 同款行级过滤）。

    与 CaseAdmin.get_queryset 一致：perm_open_access 全量、is_admin 全量，
    其余按团队分配/显式授权过滤（apply_admin_access_filter → CaseAccessPolicy）。
    """
    from apps.cases.models import Case
    from apps.cases.services.case.case_access_policy import CaseAccessPolicy
    from apps.core.security.admin_access import apply_admin_access_filter

    return apply_admin_access_filter(request, Case.objects.all(), CaseAccessPolicy())


def apply_case_related_admin_access_filter(request: Any, qs: Any) -> Any:
    """以 case 外键关联过滤关联模型 queryset：仅保留可访问案件下的记录（is_admin 全量）。"""
    return qs.filter(case_id__in=get_admin_accessible_case_queryset(request).values("id"))
