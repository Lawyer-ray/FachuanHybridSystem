"""
买卖纠纷计算 API 端点

工厂函数 + 参数提取，float ↔ Decimal 在此边界层转换。
"""

from __future__ import annotations

import logging

from ninja import Router

from .sales_dispute_assessment_api import router as assessment_router
from .sales_dispute_calculation_api import router as calculation_router
from .sales_dispute_collection_api import router as collection_router
from .sales_dispute_dashboard_api import router as dashboard_router

logger = logging.getLogger(__name__)

router = Router()

# 挂载子路由（URL 前缀不变，前端无感知）
router.add_router("", calculation_router)
router.add_router("", assessment_router)
router.add_router("", collection_router)
router.add_router("", dashboard_router)
