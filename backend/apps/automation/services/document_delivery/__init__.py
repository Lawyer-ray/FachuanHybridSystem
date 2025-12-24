# -*- coding: utf-8 -*-
"""
文书送达服务模块

本模块提供文书送达查询的完整功能，包括：
- 文书送达查询服务（API 和 Playwright 两种方式）
- 文书送达调度服务
- Token 管理服务
- 文书处理服务

向后兼容说明：
- DocumentDeliveryService 保持原有接口不变
- 新增的拆分服务可通过子模块或直接从本模块导入
- 推荐使用 DocumentDeliveryCoordinator 作为新的入口点

架构说明：
- coordinator/ - 协调器，负责选择查询策略
- token/ - Token 管理服务
- api/ - API 查询服务
- playwright/ - Playwright 浏览器自动化服务
- processor/ - 文书处理服务
"""

# 原有核心服务（保持向后兼容）
from .document_delivery_service import DocumentDeliveryService
from .document_delivery_schedule_service import DocumentDeliveryScheduleService

# 数据类
from .data_classes import (
    DocumentDeliveryRecord,
    DocumentQueryResult,
    DocumentProcessResult,
)

# API 客户端和相关类
from .court_document_api_client import (
    CourtDocumentApiClient,
    DocumentRecord,
    DocumentDetail,
    DocumentListResponse,
    CourtApiError,
    TokenExpiredError,
    ApiResponseError,
)

# 拆分后的服务 - 协调器
from .coordinator import DocumentDeliveryCoordinator

# 拆分后的服务 - Token 管理
from .token import DocumentDeliveryTokenService

# 拆分后的服务 - API 查询
from .api import DocumentDeliveryApiService

# 拆分后的服务 - Playwright 查询
from .playwright import DocumentDeliveryPlaywrightService

# 拆分后的服务 - 文书处理
from .processor import DocumentDeliveryProcessor

__all__ = [
    # ===== 原有核心服务（向后兼容）=====
    "DocumentDeliveryService",
    "DocumentDeliveryScheduleService",
    # ===== 数据类 =====
    "DocumentDeliveryRecord",
    "DocumentQueryResult",
    "DocumentProcessResult",
    # ===== API 客户端 =====
    "CourtDocumentApiClient",
    "DocumentRecord",
    "DocumentDetail",
    "DocumentListResponse",
    # ===== 异常类 =====
    "CourtApiError",
    "TokenExpiredError",
    "ApiResponseError",
    # ===== 拆分后的服务 - 协调器（推荐入口）=====
    "DocumentDeliveryCoordinator",
    # ===== 拆分后的服务 - Token 管理 =====
    "DocumentDeliveryTokenService",
    # ===== 拆分后的服务 - API 查询 =====
    "DocumentDeliveryApiService",
    # ===== 拆分后的服务 - Playwright 查询 =====
    "DocumentDeliveryPlaywrightService",
    # ===== 拆分后的服务 - 文书处理 =====
    "DocumentDeliveryProcessor",
]