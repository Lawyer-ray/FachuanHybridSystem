"""Evidence Admin 的案件行级访问辅助。

解耦（2026-10-19）：原先 evidence 各 admin（evidence_admin / evidence_item_admin /
group_admin / hearing_mode / evidence/mixins/views）跨 app 直接 import
cases 的 admin 内部 helper（apps.cases.admin.base_admin），改为经
core.security.admin_access 泛型 + Case/CaseAccessPolicy 的一行包装，
本 app 内不再依赖 cases admin 的模块内部结构（Model/Policy 层面的引用保持不变）。
"""

from __future__ import annotations

from typing import Any


def get_admin_accessible_case_queryset(request: Any) -> Any:
    """当前请求用户在 admin 中可访问的 Case queryset（口径同 cases admin 行级过滤）。"""
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


__all__ = ["apply_case_related_admin_access_filter", "get_admin_accessible_case_queryset"]
