"""
爬虫 Admin 模块
"""

from .court_document_admin import CourtDocumentAdmin
from .scraper_task_admin import ScraperTaskAdmin
from .test_admin import TestCourtAdmin

__all__ = [
    "ScraperTaskAdmin",
    "CourtDocumentAdmin",
    "TestCourtAdmin",
]
