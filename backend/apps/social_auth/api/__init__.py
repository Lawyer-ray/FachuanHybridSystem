from ninja import Router

from .passkey_api import router as passkey_router
from .social_auth_api import router as social_auth_router

router = Router()
router.add_router("", social_auth_router, tags=["社交登录"])
# /passkey 前缀与 social_auth_router 的 /{provider}/... 动态路由天然隔离：
# passkey 全部端点都是 /passkey/<2 段以上>，不会撞上 {provider} 单段匹配
router.add_router("/passkey", passkey_router, tags=["通行密钥"])

__all__ = ["router"]
