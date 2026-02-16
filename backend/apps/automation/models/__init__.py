"""Automation Models - 统一导出

向后兼容:所有 Model 都可以通过 `from apps.automation.models import X` 导入
"""

# Base (Virtual Models)
from .base import AutomationTool, FeeNoticeTest, ImageRotation, NamerTool, PreservationDateTest, TestCourt, TestToolsHub

# Court Document
from .court_document import CourtDocument, DocumentDeliverySchedule, DocumentDownloadStatus, DocumentQueryHistory

# Court SMS
from .court_sms import CourtSMS, CourtSMSStatus, CourtSMSType

# Preservation Quote
from .preservation import InsuranceQuote, PreservationQuote, QuoteItemStatus, QuoteStatus

# Document Recognition
from .recognition import DocumentRecognitionStatus, DocumentRecognitionTask

# Scraper Tasks
from .scraper import ScraperTask, ScraperTaskStatus, ScraperTaskType

# Token Management
from .token import CourtToken, TokenAcquisitionHistory, TokenAcquisitionStatus

__all__ = [
    # Base
    "AutomationTool",
    "NamerTool",
    "TestCourt",
    "FeeNoticeTest",
    "TestToolsHub",
    "PreservationDateTest",
    "ImageRotation",
    # Token
    "CourtToken",
    "TokenAcquisitionStatus",
    "TokenAcquisitionHistory",
    # Scraper
    "ScraperTaskType",
    "ScraperTaskStatus",
    "ScraperTask",
    # Preservation
    "QuoteStatus",
    "QuoteItemStatus",
    "PreservationQuote",
    "InsuranceQuote",
    # Recognition
    "DocumentRecognitionStatus",
    "DocumentRecognitionTask",
    # Court Document
    "DocumentDownloadStatus",
    "CourtDocument",
    "DocumentQueryHistory",
    "DocumentDeliverySchedule",
    # Court SMS
    "CourtSMSStatus",
    "CourtSMSType",
    "CourtSMS",
]
