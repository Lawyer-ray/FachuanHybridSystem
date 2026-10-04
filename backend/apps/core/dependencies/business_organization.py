"""Module for business organization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.core.protocols import ILawFirmService, ILawyerService, IOrganizationService, IReminderService


def build_lawyer_service() -> ILawyerService:
    from apps.organization.services import LawyerServiceAdapter

    return LawyerServiceAdapter()  # 适配器实现了所有抽象方法


def build_lawfirm_service() -> ILawFirmService:
    from apps.organization.services import LawFirmServiceAdapter

    return LawFirmServiceAdapter()


def build_organization_service() -> IOrganizationService:
    from apps.organization.services import OrganizationServiceAdapter

    return OrganizationServiceAdapter()


def build_reminder_service() -> IReminderService:
    from apps.reminders.services.wiring import get_reminder_service

    return get_reminder_service()


def resolve_request_org_access(request: Any, user: Any = None) -> dict[str, Any] | None:
    """读取 request.org_access；缺失时补算并回填（安全审计第4轮：全局搜索 ACL）。

    纯 JWT 请求在 OrgAccessMiddleware 执行期还未认证（JWT 认证发生在视图期），
    request.org_access 会是 None——若直接透传，按团队/授权的行级过滤会退化成
    「仅本人」，搜索结果异常缩水。这里在缺失且用户已认证时显式补算（带缓存，
    口径与中间件一致），并回填到 request 供后续同请求内复用。
    """
    from apps.core.security.admin_access import get_request_user

    if user is None:
        user = get_request_user(request)

    org_access = getattr(request, "org_access", None)
    if org_access is not None or user is None:
        return org_access

    from apps.organization.middleware import get_or_compute_org_access

    org_access = get_or_compute_org_access(user)
    if org_access is not None:
        request.org_access = org_access
    return org_access
