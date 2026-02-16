from ninja import Router

from apps.core.auth import JWTOrSessionAuth

from .reminder_api import router as reminder_router

# 支持 JWT 和 Session 认证
router = Router(auth=JWTOrSessionAuth())
router.add_router("", reminder_router, tags=["重要日期提醒"])

__all__ = ["router"]
