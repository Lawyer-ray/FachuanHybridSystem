"""Automation Models - 统一导出

向后兼容:所有 Model 都可以通过 `from apps.automation.models import X` 导入
"""

from __future__ import annotations

# Base (Virtual Models)
from .base import AutomationTool, ImageRotation, NamerTool, PreservationDateTest, TestCourt, TestToolsHub

# Court Document
from .court_document import CourtDocument, DocumentDeliverySchedule, DocumentDownloadStatus, DocumentQueryHistory

# Court SMS
from .court_sms import CourtSMS, CourtSMSStatus, CourtSMSType

# Invoice Recognition
from .invoice_recognition import (
    InvoiceCategory,
    InvoiceRecognitionTask,
    InvoiceRecognitionTaskStatus,
    InvoiceRecord,
    InvoiceRecordStatus,
)

# Preservation Quote
from .preservation import InsuranceQuote, PreservationQuote, QuoteItemStatus, QuoteStatus

# Document Recognition
from .recognition import DocumentRecognitionStatus, DocumentRecognitionTask

# Scraper Tasks
from .scraper import ScraperTask, ScraperTaskStatus, ScraperTaskType

# GSXT Report
from .gsxt_report import GsxtReportStatus, GsxtReportTask

# Token Management
from .token import CourtToken, TokenAcquisitionHistory, TokenAcquisitionStatus

__all__ = [
    # Base
    "AutomationTool",
    "NamerTool",
    "TestCourt",
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
    # Invoice Recognition
    "InvoiceCategory",
    "InvoiceRecognitionTaskStatus",
    "InvoiceRecordStatus",
    "InvoiceRecognitionTask",
    "InvoiceRecord",
    # GSXT
    "GsxtReportStatus",
    "GsxtReportTask",
]
