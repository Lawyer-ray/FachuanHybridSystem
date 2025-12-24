"""
Cases App API 模块
"""
from ninja import Router

from .case_api import router as case_router
from .caseparty_api import router as caseparty_router
from .caseassignment_api import router as caseassignment_router
from .caselog_api import router as caselog_router
from .caseaccess_api import router as caseaccess_router
from .casenumber_api import router as casenumber_router

# 创建模块路由器
router = Router()

# 添加子路由，每个子模块有独立的 tag
router.add_router("", case_router, tags=["案件管理"])
router.add_router("", caseparty_router, tags=["案件当事人"])
router.add_router("", caseassignment_router, tags=["案件指派"])
router.add_router("", caselog_router, tags=["案件日志"])
router.add_router("", caseaccess_router, tags=["案件授权"])
router.add_router("", casenumber_router, tags=["案件案号"])

__all__ = ["router"]
