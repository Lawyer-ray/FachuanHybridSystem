"""
Admin模块主文件
统一管理所有自动化工具的Admin界面
"""

# 文档处理 Admin
from .document import DocumentProcessorAdmin

# 财产保全询价 Admin（已迁移到 plugin）
try:
    from plugins.court_automation.preservation_quote.admin import PreservationQuoteAdmin
except ImportError:
    pass

# 爬虫 Admin
from .scraper import CourtDocumentAdmin, QuickDownloadAdmin, ScraperTaskAdmin, TestCourtAdmin

# 法院短信 Admin
from .sms import CourtSMSAdmin

# 测试工具 Admin
from .tools_hub_admin import TestToolsHubAdmin

# Token 管理 Admin
from .token import CourtTokenAdmin

_admin_all = [
    # 文档处理
    "DocumentProcessorAdmin",
    # 爬虫
    "ScraperTaskAdmin",
    "QuickDownloadAdmin",
    "CourtDocumentAdmin",
    "TestCourtAdmin",
    # Token 管理
    "CourtTokenAdmin",
    # 法院短信
    "CourtSMSAdmin",
    # 测试工具
    "TestToolsHubAdmin",
]
if "PreservationQuoteAdmin" in dir():
    _admin_all.append("PreservationQuoteAdmin")
__all__ = _admin_all
