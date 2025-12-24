"""
爬虫 Admin 模块
"""
from .scraper_task_admin import ScraperTaskAdmin
from .quick_download_admin import QuickDownloadAdmin
from .court_document_admin import CourtDocumentAdmin
from .test_admin import TestCourtAdmin

__all__ = [
    'ScraperTaskAdmin',
    'QuickDownloadAdmin',
    'CourtDocumentAdmin',
    'TestCourtAdmin',
]
