"""
Organization App API 模块
"""
from ninja import Router

from .auth_api import router as auth_router
from .lawyer_api import router as lawyer_router
from .accountcredential_api import router as accountcredential_router
from .lawfirm_api import router as lawfirm_router
from .team_api import router as team_router

# 创建模块路由器
router = Router()

# 添加子路由，每个子模块有独立的 tag
router.add_router("", auth_router, tags=["认证登录"])
router.add_router("", lawyer_router, tags=["律师管理"])
router.add_router("", accountcredential_router, tags=["账号凭证"])
router.add_router("", lawfirm_router, tags=["律所管理"])
router.add_router("", team_router, tags=["团队管理"])

__all__ = ["router"]
