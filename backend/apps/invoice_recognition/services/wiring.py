"""Dependency wiring for invoice recognition domain."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.invoice_recognition.services.invoice_download_service import InvoiceDownloadService
    from apps.invoice_recognition.services.invoice_recognition_service import InvoiceRecognitionService
    from apps.invoice_recognition.services.quick_recognition_service import QuickRecognitionService


def get_invoice_recognition_service() -> InvoiceRecognitionService:
    from apps.automation.services.ocr.ocr_service import OCRService
    from apps.automation.services.ocr.pdf_text_extractor import PDFTextExtractor
    from apps.invoice_recognition.services.invoice_parser import InvoiceParser
    from apps.invoice_recognition.services.invoice_recognition_service import InvoiceRecognitionService

    return InvoiceRecognitionService(
        ocr_service=OCRService(),
        pdf_extractor=PDFTextExtractor(),
        parser=InvoiceParser(),
    )


def get_invoice_download_service() -> InvoiceDownloadService:
    from apps.invoice_recognition.services.invoice_download_service import InvoiceDownloadService

    return InvoiceDownloadService()


def get_quick_recognition_service() -> QuickRecognitionService:
    from apps.automation.services.ocr.ocr_service import OCRService
    from apps.automation.services.ocr.pdf_text_extractor import PDFTextExtractor
    from apps.invoice_recognition.services.invoice_parser import InvoiceParser
    from apps.invoice_recognition.services.quick_recognition_service import QuickRecognitionService

    return QuickRecognitionService(
        ocr_service=OCRService(),
        pdf_extractor=PDFTextExtractor(),
        parser=InvoiceParser(),
    )

