"""Contract Admin 行级访问控制辅助。

复用 ContractAccessPolicy（与 REST 链路同口径），供合同详情/归档自定义视图
与关联 ModelAdmin 共用，避免在各视图内重复拼装权限逻辑。
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest


def ensure_admin_contract_access(request: HttpRequest, contract_id: int) -> None:
    """行级权限校验：无权访问该合同时抛 PermissionDenied（Django admin 渲染 403）。"""
    from apps.contracts.services.contract.domain.access_policy import ContractAccessPolicy
    from apps.core.exceptions import PermissionDenied as BizPermissionDenied
    from apps.core.security import get_request_access_context

    ctx = get_request_access_context(request)
    try:
        ContractAccessPolicy().ensure_access_ctx(contract_id=contract_id, ctx=ctx)
    except BizPermissionDenied as exc:
        raise PermissionDenied(str(exc)) from exc


def get_admin_accessible_contract_queryset(request: HttpRequest) -> Any:
    """当前请求用户在 admin 中可访问的 Contract queryset（复用 ContractAdmin 同款行级过滤）。"""
    from apps.contracts.models import Contract
    from apps.contracts.services.contract.domain.access_policy import ContractAccessPolicy
    from apps.core.security.admin_access import apply_admin_access_filter

    return apply_admin_access_filter(request, Contract.objects.all(), ContractAccessPolicy())


def apply_contract_related_admin_access_filter(request: HttpRequest, qs: Any) -> Any:
    """以 contract 外键关联过滤关联模型 queryset：仅保留可访问合同下的记录（is_admin 全量）。"""
    return qs.filter(contract_id__in=get_admin_accessible_contract_queryset(request).values("id"))
