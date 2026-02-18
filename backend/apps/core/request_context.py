from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.core.permissions import AccessContext


@dataclass(frozen=True)
class RequestContext:
    """请求上下文 DTO"""

    user: Any | None
    org_access: dict[str, Any] | None
    perm_open_access: bool

    def to_access_context(self) -> AccessContext:
        """转换为 AccessContext（供 PermissionMixin 使用）"""
        from apps.core.permissions import AccessContext as _AccessContext

        return _AccessContext(
            user=self.user,
            org_access=self.org_access,
            perm_open_access=self.perm_open_access,
        )


def extract_request_context(request: Any) -> RequestContext:
    """
    从 HTTP 请求中提取上下文信息

    统一替代各 API 端点中的:
    - getattr(request, "user", None)
    - getattr(request, "org_access", None)
    - getattr(request, "perm_open_access", False)
    """
    return RequestContext(
        user=getattr(request, "user", None),
        org_access=getattr(request, "org_access", None),
        perm_open_access=getattr(request, "perm_open_access", False),
    )
