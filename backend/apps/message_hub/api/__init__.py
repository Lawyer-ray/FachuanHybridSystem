"""收件箱 API 路由注册。"""

from ninja import Router

from apps.core.security.auth import JWTOrSessionAuth

from .inbox_api import router as inbox_router

router = Router(auth=JWTOrSessionAuth())
router.add_router("", inbox_router, tags=["收件箱"])

__all__ = ["router"]
