"""Agent API 层共享的请求上下文 helpers。"""

from __future__ import annotations

from typing import Any


def _current_user(request: Any) -> Any:
    user = getattr(request, "auth", None) or getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return user
    return None


def _user_id(request: Any) -> int | None:
    user = _current_user(request)
    return int(user.pk) if user is not None else None
