"""
认证 API 模块
提供用户登录和登出接口
"""

from django.http import HttpRequest
from ninja import Router

from apps.core.infrastructure.throttling import rate_limit_from_settings
from apps.organization.schemas import LoginIn, LoginOut
from apps.organization.services import AuthService

router = Router()


def _get_auth_service() -> AuthService:
    """工厂函数：获取认证服务实例"""
    return AuthService()


_auth_service = _get_auth_service()


@router.post("/login", response=LoginOut, auth=None)
@rate_limit_from_settings("AUTH")
def login_view(request: HttpRequest, payload: LoginIn) -> LoginOut:
    user = _auth_service.login(request, payload.username, payload.password)
    return LoginOut(success=True, user=user)  # type: ignore[arg-type]


@router.post("/logout", auth=None)
def logout_view(request: HttpRequest) -> dict[str, bool]:
    _auth_service.logout(request)
    return {"success": True}
