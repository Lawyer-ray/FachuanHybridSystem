"""
Contracts App API 模块
"""
from ninja import Router

from .contract_api import router as contract_router
from .contractpayment_api import router as contractpayment_router
from .contractfinance_api import router as contractfinance_router
from .contractreminder_api import router as contractreminder_router
from .supplementary_agreement_api import router as supplementary_agreement_router

# 创建模块路由器
router = Router()

# 添加子路由，每个子模块有独立的 tag
router.add_router("", contract_router, tags=["合同管理"])
router.add_router("", contractpayment_router, tags=["合同收款"])
router.add_router("", contractfinance_router, tags=["财务统计"])
router.add_router("", contractreminder_router, tags=["合同提醒"])
router.add_router("", supplementary_agreement_router, tags=["补充协议"])

__all__ = ["router"]
