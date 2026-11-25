"""从 Ninja 请求里取「操作人」。

三条路由都要它：裁决、冻结基线、改策略。写在三个文件里各一份，迟早有一处
用 `request.user` 而另一处用 `request.auth`，于是同一个账号在一条路径上被认成
匿名、在另一条上被认成本人。这里只留一份实现。
"""

from __future__ import annotations

from typing import Any

from apps.core.exceptions import PermissionDenied


def require_operator(request: Any, *, purpose: str) -> Any:
    """取不到真实登录用户就拒绝：没有操作人的留痕在出事时证明不了任何事。

    `request.auth` 是 JWT/会话认证写入的用户对象；`request.user` 是
    AuthenticationMiddleware 留下的那个。两个都拿不到（或都是匿名）即拒绝。
    """
    for candidate in (getattr(request, "auth", None), getattr(request, "user", None)):
        if candidate is not None and getattr(candidate, "is_authenticated", False):
            return candidate
    raise PermissionDenied(
        message=f"无法确认操作人身份，{purpose}必须留痕",
        code="DOC_VERIFY_OPERATOR_REQUIRED",
    )
