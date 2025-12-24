"""
Automation App API 模块
"""
from ninja import Router

from .document_processor_api import router as document_processor_router
from .auto_namer_api import router as auto_namer_router
from .main_api import router as main_router
from .preservation_quote_api import router as preservation_quote_router
from .captcha_recognition_api import router as captcha_recognition_router
from .court_sms_api import router as court_sms_router
from .document_delivery_api import router as document_delivery_router

# 创建模块路由器
router = Router()

# 添加子路由，每个子模块有独立的 tag
router.add_router("/document-processor", document_processor_router, tags=["文档处理"])
router.add_router("/auto-namer", auto_namer_router, tags=["自动命名"])
router.add_router("/captcha", captcha_recognition_router)  # 验证码识别 API
router.add_router("", preservation_quote_router)  # 财产保全询价 API
router.add_router("", court_sms_router)  # 法院短信处理 API
router.add_router("", document_delivery_router)  # 文书送达自动下载 API
router.add_router("", main_router, tags=["AI工具"])

__all__ = ["router"]
