"""
爬虫 Admin 模块
"""

from .court_document_admin import CourtDocumentAdmin
from .quick_download_admin import QuickDownloadAdmin
from .scraper_task_admin import ScraperTaskAdmin
from .test_admin import TestCourtAdmin

__all__ = [
    "ScraperTaskAdmin",
    "QuickDownloadAdmin",
    "CourtDocumentAdmin",
    "TestCourtAdmin",
]
