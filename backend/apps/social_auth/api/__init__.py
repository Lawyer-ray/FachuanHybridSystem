from ninja import Router

from .social_auth_api import router as social_auth_router

router = Router()
router.add_router("", social_auth_router, tags=["社交登录"])

__all__ = ["router"]
