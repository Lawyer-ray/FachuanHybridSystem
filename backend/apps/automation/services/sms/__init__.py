# -*- coding: utf-8 -*-
"""
SMS 处理服务模块

本模块提供法院短信处理的完整功能，包括：
- 短信解析、匹配、重命名、通知等核心服务
- 拆分后的阶段处理器（stages）
- 案件匹配相关服务（matching）
- SMS 提交服务（submission）

向后兼容说明：
- 所有原有的导入路径保持不变
- 新增的拆分服务可通过子模块或直接从本模块导入
- 异步任务入口函数保持原有路径兼容

异步任务入口（向后兼容）：
- process_sms_async: 异步处理短信
- process_sms_from_matching: 从匹配阶段开始处理
- process_sms_from_renaming: 从重命名阶段开始处理
- retry_download_task: 重试下载任务
"""

# 原有核心服务（保持向后兼容）
from .case_matcher import CaseMatcher, _get_case_matcher
from .sms_parser_service import SMSParserService
from .feishu_bot_service import FeishuBotService
from .court_sms_service import CourtSMSService
from .document_renamer import DocumentRenamer
from .case_number_extractor_service import CaseNumberExtractorService
from .document_attachment_service import DocumentAttachmentService
from .sms_notification_service import SMSNotificationService
from .task_recovery_service import TaskRecoveryService

# 异步任务入口函数（向后兼容 - 保持原有导入路径）
from .court_sms_service import (
    process_sms_async,
    process_sms_from_matching,
    process_sms_from_renaming,
    retry_download_task,
)

# 拆分后的提交服务
from .submission import SMSSubmissionService

# 拆分后的匹配服务
from .matching import (
    DocumentParserService,
    PartyMatchingService,
    _get_document_parser_service,
    _get_party_matching_service,
)

# 拆分后的阶段处理器
from .stages import (
    ISMSStage,
    BaseSMSStage,
    SMSParsingStage,
    create_sms_parsing_stage,
    SMSDownloadingStage,
    create_sms_downloading_stage,
    SMSMatchingStage,
    create_sms_matching_stage,
    SMSRenamingStage,
    create_sms_renaming_stage,
    SMSNotifyingStage,
    create_sms_notifying_stage,
)

__all__ = [
    # ===== 原有核心服务（向后兼容）=====
    "CaseMatcher",
    "_get_case_matcher",
    "SMSParserService",
    "FeishuBotService",
    "CourtSMSService",
    "DocumentRenamer",
    "CaseNumberExtractorService",
    "DocumentAttachmentService",
    "SMSNotificationService",
    "TaskRecoveryService",
    # ===== 异步任务入口函数（向后兼容）=====
    "process_sms_async",
    "process_sms_from_matching",
    "process_sms_from_renaming",
    "retry_download_task",
    # ===== 拆分后的提交服务 =====
    "SMSSubmissionService",
    # ===== 拆分后的匹配服务 =====
    "DocumentParserService",
    "PartyMatchingService",
    "_get_document_parser_service",
    "_get_party_matching_service",
    # ===== 拆分后的阶段处理器 =====
    "ISMSStage",
    "BaseSMSStage",
    "SMSParsingStage",
    "create_sms_parsing_stage",
    "SMSDownloadingStage",
    "create_sms_downloading_stage",
    "SMSMatchingStage",
    "create_sms_matching_stage",
    "SMSRenamingStage",
    "create_sms_renaming_stage",
    "SMSNotifyingStage",
    "create_sms_notifying_stage",
]
