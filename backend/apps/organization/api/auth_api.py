"""
认证 API 模块
提供用户登录和登出接口
"""

from typing import Any
from ninja import Router
from apps.organization.schemas import LoginIn, LoginOut
from apps.organization.services import AuthService
from apps.core.infrastructure.throttling import rate_limit_from_settings

router = Router()


def _get_auth_service() -> AuthService:
    """工厂函数：创建 AuthService 实例"""
    from apps.organization.services import AuthService

    return AuthService()


@router.post("/login", response=LoginOut, auth=None)
@rate_limit_from_settings("AUTH")
def login_view(request: Any, payload: LoginIn) -> dict[str, Any]:
    """用户登录"""
    service = _get_auth_service()
    user = service.login(request, payload.username, payload.password)
    return {"success": True, "user": user}


@router.post("/logout", auth=None)
def logout_view(request: Any) -> dict[str, bool]:
    """用户登出"""
    service = _get_auth_service()
    service.logout(request)
    return {"success": True}
