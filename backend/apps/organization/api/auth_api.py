"""
认证 API 模块
提供用户登录和登出接口
"""

from __future__ import annotations

from django.http import HttpRequest
from ninja import Router

from apps.organization.schemas import LoginIn, LoginOut
from apps.organization.services import AuthService
from apps.core.infrastructure.throttling import rate_limit_from_settings

router = Router()

_auth_service = AuthService()


@router.post("/login", response=LoginOut, auth=None)
@rate_limit_from_settings("AUTH")
def login_view(request: HttpRequest, payload: LoginIn) -> dict[str, object]:
    user = _auth_service.login(request, payload.username, payload.password)
    return {"success": True, "user": user}


@router.post("/logout", auth=None)
def logout_view(request: HttpRequest) -> dict[str, bool]:
    _auth_service.logout(request)
    return {"success": True}
