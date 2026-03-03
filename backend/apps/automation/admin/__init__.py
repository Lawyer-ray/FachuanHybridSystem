"""
Admin模块主文件
统一管理所有自动化工具的Admin界面
"""

# 文档处理 Admin
from .document import DocumentProcessorAdmin

# 文书送达 Admin
from .document_delivery import DocumentDeliveryScheduleAdmin, DocumentQueryHistoryAdmin

# 文书识别 Admin
from .document_recognition import DocumentRecognitionAdmin, DocumentRecognitionTaskAdmin

# 交费通知书识别 Admin
from .fee_notice import FeeNoticeTestAdmin

# 图片自动旋转 Admin
from .image_rotation import ImageRotationAdmin

# 财产保全询价 Admin
from .insurance import PreservationQuoteAdmin

# 发票识别 Admin
from .invoice_recognition import InvoiceRecognitionTaskAdmin

# 财产保全日期识别 Admin
from .preservation_date import PreservationDateTestAdmin

# 爬虫 Admin
from .scraper import CourtDocumentAdmin, QuickDownloadAdmin, ScraperTaskAdmin, TestCourtAdmin

# 法院短信 Admin
from .sms import CourtSMSAdmin

# 测试工具 Admin
from .test_tools_hub import TestToolsHubAdmin

# Token 管理 Admin
from .token import CourtTokenAdmin, TokenAcquisitionHistoryAdmin

__all__ = [
    # 文档处理
    "DocumentProcessorAdmin",
    # 爬虫
    "ScraperTaskAdmin",
    "QuickDownloadAdmin",
    "CourtDocumentAdmin",
    "TestCourtAdmin",
    # Token 管理
    "CourtTokenAdmin",
    "TokenAcquisitionHistoryAdmin",
    # 财产保全询价
    "PreservationQuoteAdmin",
    # 法院短信
    "CourtSMSAdmin",
    # 文书送达
    "DocumentDeliveryScheduleAdmin",
    "DocumentQueryHistoryAdmin",
    # 文书识别
    "DocumentRecognitionAdmin",
    "DocumentRecognitionTaskAdmin",
    # 测试工具
    "TestToolsHubAdmin",
    "FeeNoticeTestAdmin",
    "PreservationDateTestAdmin",
    "ImageRotationAdmin",
    "InvoiceRecognitionTaskAdmin",
]
