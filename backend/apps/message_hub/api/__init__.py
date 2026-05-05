"""收件箱 API 路由注册。"""

from ninja import Router

from apps.core.security.auth import JWTOrSessionAuth

from .inbox_api import router as inbox_router
from .message_source_api import router as source_router

router = Router(auth=JWTOrSessionAuth())
router.add_router("", inbox_router, tags=["收件箱"])
router.add_router("", source_router, tags=["消息来源"])

__all__ = ["router"]
