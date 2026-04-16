from ninja import Router

from apps.core.security.auth import JWTOrSessionAuth

from .animation_api import router as animation_router

router = Router(auth=JWTOrSessionAuth())
router.add_router("", animation_router, tags=["故事可视化"])

__all__ = ["router"]
