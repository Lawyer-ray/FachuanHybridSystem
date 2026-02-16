"""Automation Schemas - 统一导出

向后兼容:所有 Schema 都可以通过 `from apps.automation.schemas import X` 导入
"""

# Captcha Recognition
from .captcha import CaptchaRecognizeIn, CaptchaRecognizeOut

# Court Document
from .court_document import APIInterceptResponseSchema, CourtDocumentSchema

# Court SMS
from .court_sms import (
    CourtSMSAssignCaseIn,
    CourtSMSAssignCaseOut,
    CourtSMSDetailOut,
    CourtSMSListOut,
    CourtSMSSubmitIn,
    CourtSMSSubmitOut,
    SMSParseResult,
)

# Document Processing
from .document import (
    AsyncTaskStatusOut,
    AsyncTaskSubmitOut,
    AutoToolProcessIn,
    AutoToolProcessOut,
    DocumentProcessIn,
    DocumentProcessOut,
    MoonshotChatIn,
    MoonshotChatOut,
    OllamaChatIn,
    OllamaChatOut,
)

# Document Delivery
from .document_delivery import DocumentDeliveryRecord, DocumentProcessResult, DocumentQueryResult

# Image Rotation
from .image_rotation import (  # Auto Rename
    DetectOrientationItem,
    DetectOrientationRequestSchema,
    DetectOrientationResponseSchema,
    DetectPageOrientationRequestSchema,
    DetectPageOrientationResponseSchema,
    ExportPageItem,
    ExportPDFRequestSchema,
    ExportPDFResponseSchema,
    ExportRequestSchema,
    ExportResponseSchema,
    ImageRotationItem,
    OrientationResult,
    PDFExtractFastResponseSchema,
    PDFExtractRequestSchema,
    PDFExtractResponseSchema,
    PDFPageItem,
    PDFPageItemSimple,
    RenameRequestItem,
    RenameSuggestionItem,
    SuggestRenameRequestSchema,
    SuggestRenameResponseSchema,
)

# Performance Monitoring
from .performance import AlertSchema, HealthCheckOut, PerformanceMetricsOut, ResourceUsageOut, StatisticsReportOut

# Preservation Quote
from .preservation import (
    InsuranceQuoteSchema,
    PreservationQuoteCreateSchema,
    PreservationQuoteSchema,
    QuoteExecuteResponseSchema,
    QuoteListItemSchema,
    QuoteListSchema,
)

__all__ = [
    # Document Processing
    "DocumentProcessIn",
    "DocumentProcessOut",
    "OllamaChatIn",
    "OllamaChatOut",
    "MoonshotChatIn",
    "MoonshotChatOut",
    "AutoToolProcessIn",
    "AutoToolProcessOut",
    "AsyncTaskSubmitOut",
    "AsyncTaskStatusOut",
    # Captcha
    "CaptchaRecognizeIn",
    "CaptchaRecognizeOut",
    # Preservation
    "PreservationQuoteCreateSchema",
    "InsuranceQuoteSchema",
    "PreservationQuoteSchema",
    "QuoteListItemSchema",
    "QuoteListSchema",
    "QuoteExecuteResponseSchema",
    # Court Document
    "APIInterceptResponseSchema",
    "CourtDocumentSchema",
    # Performance
    "PerformanceMetricsOut",
    "StatisticsReportOut",
    "AlertSchema",
    "HealthCheckOut",
    "ResourceUsageOut",
    # Court SMS
    "SMSParseResult",
    "CourtSMSSubmitIn",
    "CourtSMSSubmitOut",
    "CourtSMSDetailOut",
    "CourtSMSListOut",
    "CourtSMSAssignCaseIn",
    "CourtSMSAssignCaseOut",
    # Document Delivery
    "DocumentDeliveryRecord",
    "DocumentQueryResult",
    "DocumentProcessResult",
    # Image Rotation
    "ImageRotationItem",
    "ExportRequestSchema",
    "ExportResponseSchema",
    "DetectOrientationItem",
    "DetectOrientationRequestSchema",
    "OrientationResult",
    "DetectOrientationResponseSchema",
    "PDFExtractRequestSchema",
    "PDFPageItem",
    "PDFExtractResponseSchema",
    "ExportPageItem",
    "ExportPDFRequestSchema",
    "ExportPDFResponseSchema",
    "PDFPageItemSimple",
    "PDFExtractFastResponseSchema",
    "DetectPageOrientationRequestSchema",
    "DetectPageOrientationResponseSchema",
    # Auto Rename
    "RenameRequestItem",
    "SuggestRenameRequestSchema",
    "RenameSuggestionItem",
    "SuggestRenameResponseSchema",
]
