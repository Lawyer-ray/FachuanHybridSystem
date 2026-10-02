"""
SMS 处理服务模块

本模块提供法院短信处理的完整功能，包括：
- 短信解析、匹配、重命名、通知等核心服务
- 案件匹配相关服务（matching）
- 短信解析辅助服务（parsing）

向后兼容说明：
- 所有原有的导入路径保持不变
- 异步任务入口函数保持原有路径兼容

异步任务入口（向后兼容）：
- process_sms_async: 异步处理短信
- process_sms_from_matching: 从匹配阶段开始处理
- process_sms_from_renaming: 从重命名阶段开始处理
- retry_download_task: 重试下载任务
"""

from apps.automation.workers.court_sms_tasks import process_sms as process_sms_async
from apps.automation.workers.court_sms_tasks import (
    process_sms_from_matching,
    process_sms_from_renaming,
    retry_download_task,
)

# 原有核心服务（保持向后兼容）
from .case_matcher import CaseMatcher, _get_case_matcher
from .case_number_extractor_service import CaseNumberExtractorService

# 异步任务入口函数（已迁移到 workers 层，保持向后兼容导入路径）
from .court_sms_service import CourtSMSService
from .document_attachment_service import DocumentAttachmentService
from .document_renamer import DocumentRenamer

# 拆分后的匹配服务
from .matching import (
    DocumentParserService,
    PartyMatchingService,
    _get_document_parser_service,
    _get_party_matching_service,
)
from .sms_notification_service import SMSNotificationService
from .sms_parser_service import SMSParserService

__all__ = [
    # ===== 原有核心服务（向后兼容）=====
    "CaseMatcher",
    "_get_case_matcher",
    "SMSParserService",
    "CourtSMSService",
    "DocumentRenamer",
    "CaseNumberExtractorService",
    "DocumentAttachmentService",
    "SMSNotificationService",
    # ===== 异步任务入口函数（向后兼容）=====
    "process_sms_async",
    "process_sms_from_matching",
    "process_sms_from_renaming",
    "retry_download_task",
    # ===== 拆分后的匹配服务 =====
    "DocumentParserService",
    "PartyMatchingService",
    "_get_document_parser_service",
    "_get_party_matching_service",
]
