"""
Client App API 模块
"""
from ninja import Router

from .client_api import router as client_router
from .clientidentitydoc_api import router as clientidentitydoc_router
from .property_clue_api import router as property_clue_router

# 创建模块路由器
router = Router()

# 添加子路由，每个子模块有独立的 tag
router.add_router("", client_router, tags=["客户管理"])
router.add_router("", clientidentitydoc_router, tags=["客户证件"])
router.add_router("", property_clue_router, tags=["财产线索"])

__all__ = ["router"]
