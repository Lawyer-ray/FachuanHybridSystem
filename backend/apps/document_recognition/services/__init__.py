"""
法院文书智能识别服务

提供法院文书（传票、执行裁定书等）的智能识别功能，
包括文书类型识别、关键信息提取、案件匹配和日志绑定。
"""

from .adapter import CourtDocumentRecognitionServiceAdapter
from .case_binding_service import CaseBindingService
from .case_matching_service import DocumentCaseMatchingService
from .data_classes import BindingResult, DocumentType, NotificationResult, RecognitionResponse, RecognitionResult
from .date_candidate_service import DateCandidateDraft, build_date_candidates, confirm_candidates, revoke_confirmation
from .document_classifier import DocumentClassifier
from .info_extractor import InfoExtractor
from .notification_service import DocumentRecognitionNotificationService
from .recognition_service import CourtDocumentRecognitionService
from .text_extraction_service import (
    SUPPORTED_EXTENSIONS,
    SUPPORTED_IMAGE_EXTENSIONS,
    SUPPORTED_PDF_EXTENSIONS,
    TextExtractionResult,
    TextExtractionService,
)

__all__ = [
    # 数据类
    "DocumentType",
    "RecognitionResult",
    "BindingResult",
    "RecognitionResponse",
    "NotificationResult",
    # 文本提取服务
    "TextExtractionService",
    "TextExtractionResult",
    "SUPPORTED_EXTENSIONS",
    "SUPPORTED_PDF_EXTENSIONS",
    "SUPPORTED_IMAGE_EXTENSIONS",
    # 文书分类器
    "DocumentClassifier",
    # 信息提取器
    "InfoExtractor",
    # 案件绑定服务
    "CaseBindingService",
    # 案件严格匹配服务
    "DocumentCaseMatchingService",
    # 日期候选服务
    "DateCandidateDraft",
    "build_date_candidates",
    "confirm_candidates",
    "revoke_confirmation",
    # 主服务（协调器）
    "CourtDocumentRecognitionService",
    # ServiceLocator 适配器
    "CourtDocumentRecognitionServiceAdapter",
    # 通知服务
    "DocumentRecognitionNotificationService",
]
