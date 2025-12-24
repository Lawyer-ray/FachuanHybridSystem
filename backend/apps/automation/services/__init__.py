# -*- coding: utf-8 -*-
"""
Automation 服务模块

本模块提供自动化相关的所有服务，包括：
- Token 管理服务（token/）
- 文书送达服务（document_delivery/）
- 短信处理服务（sms/）
- 文书处理服务（document/）
- AI 服务（ai/）
- 语音服务（speech/）
- 保险服务（insurance/）
- 聊天服务（chat/）
- 验证码服务（captcha/）
- 爬虫服务（scraper/）

向后兼容说明：
- 所有原有的导入路径保持不变
- 新增的拆分服务可通过子模块导入
- 异步任务入口函数保持原有路径兼容
"""

# Token 管理服务
from .token import (
    AccountSelectionStrategy,
    AutoLoginService,
    AutoTokenAcquisitionService,
)

# 文书送达服务（原有 + 拆分后）
from .document_delivery import (
    # 原有服务
    DocumentDeliveryService,
    DocumentDeliveryScheduleService,
    # 数据类
    DocumentDeliveryRecord,
    DocumentQueryResult,
    DocumentProcessResult,
    # API 客户端
    CourtDocumentApiClient,
    # 拆分后的服务
    DocumentDeliveryCoordinator,
    DocumentDeliveryTokenService,
    DocumentDeliveryApiService,
    DocumentDeliveryPlaywrightService,
    DocumentDeliveryProcessor,
)

# 短信处理服务（原有 + 拆分后）
from .sms import (
    # 原有服务
    CaseMatcher,
    SMSParserService,
    FeishuBotService,
    CourtSMSService,
    DocumentRenamer,
    CaseNumberExtractorService,
    DocumentAttachmentService,
    SMSNotificationService,
    TaskRecoveryService,
    # 异步任务入口函数（向后兼容）
    process_sms_async,
    process_sms_from_matching,
    process_sms_from_renaming,
    retry_download_task,
    # 拆分后的服务
    SMSSubmissionService,
    DocumentParserService,
    PartyMatchingService,
    # 阶段处理器
    ISMSStage,
    BaseSMSStage,
    SMSParsingStage,
    SMSDownloadingStage,
    SMSMatchingStage,
    SMSRenamingStage,
    SMSNotifyingStage,
)

__all__ = [
    # ===== Token 管理服务 =====
    "AccountSelectionStrategy",
    "AutoLoginService",
    "AutoTokenAcquisitionService",
    # ===== 文书送达服务（原有）=====
    "DocumentDeliveryService",
    "DocumentDeliveryScheduleService",
    # ===== 文书送达数据类 =====
    "DocumentDeliveryRecord",
    "DocumentQueryResult",
    "DocumentProcessResult",
    # ===== 文书送达 API 客户端 =====
    "CourtDocumentApiClient",
    # ===== 文书送达服务（拆分后）=====
    "DocumentDeliveryCoordinator",
    "DocumentDeliveryTokenService",
    "DocumentDeliveryApiService",
    "DocumentDeliveryPlaywrightService",
    "DocumentDeliveryProcessor",
    # ===== 短信处理服务（原有）=====
    "CaseMatcher",
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
    # ===== 短信处理服务（拆分后）=====
    "SMSSubmissionService",
    "DocumentParserService",
    "PartyMatchingService",
    # ===== 短信阶段处理器 =====
    "ISMSStage",
    "BaseSMSStage",
    "SMSParsingStage",
    "SMSDownloadingStage",
    "SMSMatchingStage",
    "SMSRenamingStage",
    "SMSNotifyingStage",
]
