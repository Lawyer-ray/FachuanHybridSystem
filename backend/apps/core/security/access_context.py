"""Module for access context."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AccessContext:
    user: Any | None
    org_access: dict[str, Any] | None
    perm_open_access: bool = False


def get_request_access_context(request: Any) -> AccessContext:
    existing = getattr(request, "access_ctx", None)
    if isinstance(existing, AccessContext):
        return existing

    return AccessContext(
        user=getattr(request, "user", None),
        org_access=getattr(request, "org_access", None),
        perm_open_access=bool(getattr(request, "perm_open_access", False)),
    )
