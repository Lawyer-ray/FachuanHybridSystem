"""
认证 API 模块
提供用户登录和登出接口
"""
from ninja import Router
from ..schemas import LoginIn, LoginOut

router = Router()


def _get_auth_service():
    """工厂函数：创建 AuthService 实例"""
    from ..services import AuthService
    return AuthService()


@router.post("/login", response=LoginOut, auth=None)
def login_view(request, payload: LoginIn):
    """用户登录"""
    service = _get_auth_service()
    user = service.login(request, payload.username, payload.password)
    return {"success": True, "user": user}


@router.post("/logout", auth=None)
def logout_view(request):
    """用户登出"""
    service = _get_auth_service()
    service.logout(request)
    return {"success": True}
