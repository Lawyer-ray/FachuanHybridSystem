"""Module for admin access."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from apps.core.exceptions import PermissionDenied
from apps.core.security.access_context import get_request_access_context


def get_request_user(request: HttpRequest) -> Any | None:
    user = getattr(request, "user", None)
    if user and getattr(user, "is_authenticated", False):
        return user
    return getattr(request, "auth", None)


def is_admin_user(user: Any | None) -> bool:
    # 2026Q4 审计收紧：is_staff 仅是 Django admin 准入标志，不再视为系统管理员
    return bool(user and (getattr(user, "is_admin", False) or getattr(user, "is_superuser", False)))


def ensure_admin_request(
    request: HttpRequest,
    *,
    message: str = "无权限执行该操作",
    code: str = "PERMISSION_DENIED",
) -> None:
    if is_admin_user(get_request_user(request)):
        return
    raise PermissionDenied(message=message, code=code)


def apply_admin_access_filter(request: HttpRequest, qs: Any, policy: Any) -> Any:
    """在 Django admin get_queryset 中应用行级权限过滤.

    复用 CaseAccessPolicy / ContractAccessPolicy 的 filter_queryset,
    根据用户团队分配和显式授权过滤 queryset.
    """
    org_access = getattr(request, "org_access", None)
    perm_open_access = getattr(request, "perm_open_access", False)
    return policy.filter_queryset(qs, request.user, org_access, perm_open_access)


def admin_accessible_queryset(request: HttpRequest, model: Any, policy: Any) -> Any:
    """当前请求用户在 admin 中可访问的 model 全量 queryset（泛型）.

    解耦（2026-10-19）：收敛 cases/admin/base_admin.py 与
    contracts/admin/access.py 各自的同款实现（两版只差 Model/Policy）——
    perm_open_access 全量、is_admin 全量，其余按团队分配/显式授权过滤
    （apply_admin_access_filter → 各业务 AccessPolicy）。
    """
    return apply_admin_access_filter(request, model.objects.all(), policy)


def apply_related_admin_access_filter(
    request: HttpRequest,
    qs: Any,
    *,
    fk: str,
    model: Any,
    policy: Any,
) -> Any:
    """以 fk 外键关联过滤关联模型 queryset：仅保留可访问父对象下的记录（泛型）.

    解耦（2026-10-19）：等价原 ``apply_case_related_admin_access_filter`` /
    ``apply_contract_related_admin_access_filter`` 的 ``qs.filter(<fk>__in=...)``，
    fk 形如 ``"case_id"`` / ``"contract_id"``。
    """
    accessible_ids = admin_accessible_queryset(request, model, policy).values("pk")
    return qs.filter(**{f"{fk}__in": accessible_ids})


def ensure_admin_object_access(
    request: HttpRequest,
    policy: Any,
    *,
    object_id: Any,
    message: str,
    id_kwarg: str,
    obj: Any | None = None,
    obj_kwarg: str | None = None,
) -> None:
    """Admin 自定义视图行级权限校验（泛型）：无权访问时抛 PermissionDenied（admin 渲染 403）.

    解耦（2026-10-19）：收敛 contracts/admin/access.py 的
    ``ensure_admin_contract_access`` 与 cases/admin/mixins/views.py 的
    ``_ensure_case_access``（方法版）共用的转换逻辑——业务 policy 的
    ``ensure_access_ctx`` 抛出 apps.core.exceptions.PermissionDenied 时，
    统一转换为 django.core.exceptions.PermissionDenied。

    - ``id_kwarg``：policy.ensure_access_ctx 的主键参数名（如 ``"case_id"``）；
    - ``obj`` / ``obj_kwarg``：可选的已加载对象透传（如 ``case=`` / ``contract=``），
      与直接调用 policy 时传 ``None`` 等价（参数有默认值）。
    """
    from django.core.exceptions import PermissionDenied as DjangoPermissionDenied

    from apps.core.exceptions import PermissionDenied as BizPermissionDenied

    policy_kwargs: dict[str, Any] = {id_kwarg: object_id, "ctx": get_request_access_context(request)}
    if obj_kwarg is not None:
        policy_kwargs[obj_kwarg] = obj
    try:
        policy.ensure_access_ctx(**policy_kwargs)
    except BizPermissionDenied as exc:
        raise DjangoPermissionDenied(str(exc) or message) from exc
