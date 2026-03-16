"""
Admin模块主文件
统一管理所有自动化工具的Admin界面
"""

# 文档处理 Admin
from .document import DocumentProcessorAdmin

# 文书送达 Admin
from .document_delivery import DocumentDeliveryScheduleAdmin, DocumentQueryHistoryAdmin

# 财产保全询价 Admin
from .insurance import PreservationQuoteAdmin


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
    # 测试工具
    "TestToolsHubAdmin",
]
