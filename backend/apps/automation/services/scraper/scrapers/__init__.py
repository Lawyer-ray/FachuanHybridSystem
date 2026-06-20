"""
爬虫实现模块
"""

from .base import BaseScraper
from .court_document import CourtDocumentScraper

try:
    from plugins.court_automation.filing.playwright_filing.service import (
        CourtZxfwFilingService as CourtFilingScraper,
    )
except ImportError:
    from .court_filing import CourtFilingScraper  # type: ignore[assignment]

__all__ = [
    "BaseScraper",
    "CourtDocumentScraper",
    "CourtFilingScraper",
]
