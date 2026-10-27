from __future__ import annotations

"""
Contracts App API 模块
"""

from ninja import Router

from .archive_api import router as archive_router
from .contract_api import router as contract_router
from .contract_folder_browse_api import router as contract_folder_browse_router
from .contractfinance_api import router as contractfinance_router
from .contractpayment_api import router as contractpayment_router

# 增强路由必须**先**注册：`/finance/invoices/{invoice_id}` 前缀与基础路由无冲突，
# 但 parse-text 与 `{payment_id}` 路径同层，晚注册会被通配先吃掉（405 DELETE/PUT）。
from .contractpayment_enhance_api import router as contractpayment_enhance_router
from .folder_binding_api import router as folder_binding_router
from .folder_scan_api import router as folder_scan_router
from .supplementary_agreement_api import router as supplementary_agreement_router

# 创建模块路由器
router = Router()

# 添加子路由，每个子模块有独立的 tag
router.add_router("", contract_router, tags=["合同管理"])
router.add_router("", contractpayment_enhance_router, tags=["合同收款"])
router.add_router("", contractpayment_router, tags=["合同收款"])
router.add_router("", contractfinance_router, tags=["财务统计"])
router.add_router("", supplementary_agreement_router, tags=["补充协议"])
router.add_router("", folder_binding_router, tags=["文件夹绑定"])
router.add_router("", folder_scan_router, tags=["文件夹自动捕获"])
router.add_router("", archive_router, tags=["归档材料管理"])
router.add_router("", contract_folder_browse_router, tags=["合同文件夹浏览"])

__all__ = ["router"]
