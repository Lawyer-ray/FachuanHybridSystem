"""Cases Admin 公共基类与行级访问 helper。

解耦（2026-10-19）：
- nested_admin 兜底别名上提到 ``apps.core.admin.base``，本模块仅 re-export，
  cases admin 内既有 import（BaseModelAdmin / BaseStackedInline / BaseTabularInline）零改动；
- ``get_admin_accessible_case_queryset`` / ``apply_case_related_admin_access_filter``
  改为 ``apps.core.security.admin_access`` 泛型的薄包装（保留原函数名与签名，
  contracts/admin/access.py 同款收敛），调用方零改动。
"""

from __future__ import annotations

from typing import Any

from apps.core.admin.base import BaseModelAdmin, BaseStackedInline, BaseTabularInline


def get_admin_accessible_case_queryset(request: Any) -> Any:
    """当前请求用户在 admin 中可访问的 Case queryset（复用 CaseAdmin 同款行级过滤）。

    与 CaseAdmin.get_queryset 一致：perm_open_access 全量、is_admin 全量，
    其余按团队分配/显式授权过滤（apply_admin_access_filter → CaseAccessPolicy）。
    """
    from apps.cases.models import Case
    from apps.cases.services.case.case_access_policy import CaseAccessPolicy
    from apps.core.security.admin_access import admin_accessible_queryset

    return admin_accessible_queryset(request, Case, CaseAccessPolicy())


def apply_case_related_admin_access_filter(request: Any, qs: Any) -> Any:
    """以 case 外键关联过滤关联模型 queryset：仅保留可访问案件下的记录（is_admin 全量）。"""
    from apps.cases.models import Case
    from apps.cases.services.case.case_access_policy import CaseAccessPolicy
    from apps.core.security.admin_access import apply_related_admin_access_filter

    return apply_related_admin_access_filter(request, qs, fk="case_id", model=Case, policy=CaseAccessPolicy())


__all__ = [
    "BaseModelAdmin",
    "BaseStackedInline",
    "BaseTabularInline",
    "apply_case_related_admin_access_filter",
    "get_admin_accessible_case_queryset",
]
