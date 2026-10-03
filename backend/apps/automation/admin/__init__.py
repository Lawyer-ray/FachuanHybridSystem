"""
Admin模块主文件
统一管理所有自动化工具的Admin界面
"""

# 财产保全询价 Admin（已迁移到 plugin）
try:
    from plugins.court_automation.preservation_quote.admin import PreservationQuoteAdmin
except ImportError:
    pass

# 爬虫 Admin
from .scraper import CourtDocumentAdmin, ScraperTaskAdmin, TestCourtAdmin

# 法院短信 Admin
from .sms import CourtSMSAdmin

# 测试工具 Admin
from .tools_hub_admin import TestToolsHubAdmin

# Token 管理 Admin（已迁移到 plugin）
try:
    from .token import CourtTokenAdmin
except ImportError:
    pass

_admin_all = [
    # 爬虫
    "ScraperTaskAdmin",
    "CourtDocumentAdmin",
    "TestCourtAdmin",
    # 法院短信
    "CourtSMSAdmin",
    # 测试工具
    "TestToolsHubAdmin",
]
if "PreservationQuoteAdmin" in dir():
    _admin_all.append("PreservationQuoteAdmin")
if "CourtTokenAdmin" in dir():
    _admin_all.append("CourtTokenAdmin")
__all__ = _admin_all
