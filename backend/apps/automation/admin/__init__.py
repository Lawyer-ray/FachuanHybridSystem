"""
Admin模块主文件
统一管理所有自动化工具的Admin界面
"""

# 文档处理 Admin
from .document import DocumentProcessorAdmin

# 爬虫 Admin
from .scraper import (
    ScraperTaskAdmin,
    QuickDownloadAdmin,
    CourtDocumentAdmin,
    TestCourtAdmin,
)

# Token 管理 Admin
from .token import (
    CourtTokenAdmin,
    TokenAcquisitionHistoryAdmin,
)

# 财产保全询价 Admin
from .insurance import PreservationQuoteAdmin

# 法院短信 Admin
from .sms import CourtSMSAdmin

# 文书送达 Admin
from .document_delivery import (
    DocumentDeliveryScheduleAdmin,
    DocumentQueryHistoryAdmin,
)

# 文书识别 Admin
from .document_recognition import DocumentRecognitionAdmin, DocumentRecognitionTaskAdmin

__all__ = [
    # 文档处理
    'DocumentProcessorAdmin',
    # 爬虫
    'ScraperTaskAdmin',
    'QuickDownloadAdmin',
    'CourtDocumentAdmin',
    'TestCourtAdmin',
    # Token 管理
    'CourtTokenAdmin',
    'TokenAcquisitionHistoryAdmin',
    # 财产保全询价
    'PreservationQuoteAdmin',
    # 法院短信
    'CourtSMSAdmin',
    # 文书送达
    'DocumentDeliveryScheduleAdmin',
    'DocumentQueryHistoryAdmin',
    # 文书识别
    'DocumentRecognitionAdmin',
    'DocumentRecognitionTaskAdmin',
]
