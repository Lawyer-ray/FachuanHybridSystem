from ninja import Router

from apps.core.security.auth import JWTOrSessionAuth

from .reminder_api import router as reminder_router
from .calendar_feed_api import router as calendar_feed_router

# 支持 JWT 和 Session 认证
router = Router(auth=JWTOrSessionAuth())
router.add_router("", reminder_router, tags=["重要日期提醒"])
router.add_router("", calendar_feed_router, tags=["日历订阅"])

__all__ = ["router"]
