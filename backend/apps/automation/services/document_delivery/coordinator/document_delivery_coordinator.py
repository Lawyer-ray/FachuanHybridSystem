"""
文书送达查询协调器

协调文书送达查询的主入口，负责选择查询策略（API 优先，Playwright 降级）。
整合 Token、API、Playwright、Processor 服务，实现三级降级策略。

Requirements: 1.1, 1.3, 1.4, 5.1, 5.2, 5.5
"""

import logging
import traceback
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from apps.automation.utils.logging import AutomationLogger

from ..data_classes import DocumentQueryResult

if TYPE_CHECKING:
    from ..api.document_delivery_api_service import DocumentDeliveryApiService
    from ..playwright.document_delivery_playwright_service import DocumentDeliveryPlaywrightService
    from ..processor.document_delivery_processor import DocumentDeliveryProcessor
    from ..token.document_delivery_token_service import DocumentDeliveryTokenService

logger = logging.getLogger("apps.automation")


class DocumentDeliveryCoordinator:
    """
    文书送达查询协调器

    职责：
    1. 协调 Token、API、Playwright、Processor 服务
    2. 实现三级降级策略：API 优先 -> Playwright 登录后 API -> Playwright 页面
    3. 统一的查询入口

    Requirements: 1.1, 1.3, 1.4, 5.1, 5.2, 5.5
    """

    def __init__(
        self,
        token_service: Optional["DocumentDeliveryTokenService"] = None,
        api_service: Optional["DocumentDeliveryApiService"] = None,
        playwright_service: Optional["DocumentDeliveryPlaywrightService"] = None,
        processor: Optional["DocumentDeliveryProcessor"] = None,
    ):
        """
        初始化协调器，支持依赖注入

        Args:
            token_service: Token 管理服务（可选）
            api_service: API 查询服务（可选）
            playwright_service: Playwright 查询服务（可选）
            processor: 文书处理服务（可选）
        """
        self._token_service = token_service
        self._api_service = api_service
        self._playwright_service = playwright_service
        self._processor = processor

        logger.debug("DocumentDeliveryCoordinator 初始化完成")

    @property
    def token_service(self) -> "DocumentDeliveryTokenService":
        """延迟加载 Token 管理服务"""
        if self._token_service is None:
            from ..token.document_delivery_token_service import DocumentDeliveryTokenService

            self._token_service = DocumentDeliveryTokenService()
        return self._token_service

    @property
    def api_service(self) -> "DocumentDeliveryApiService":
        """延迟加载 API 查询服务"""
        if self._api_service is None:
            from ..api.document_delivery_api_service import DocumentDeliveryApiService

            self._api_service = DocumentDeliveryApiService()
        return self._api_service

    @property
    def playwright_service(self) -> "DocumentDeliveryPlaywrightService":
        """延迟加载 Playwright 查询服务"""
        if self._playwright_service is None:
            from ..playwright.document_delivery_playwright_service import DocumentDeliveryPlaywrightService

            self._playwright_service = DocumentDeliveryPlaywrightService()
        return self._playwright_service

    @property
    def processor(self) -> "DocumentDeliveryProcessor":
        """延迟加载文书处理服务"""
        if self._processor is None:
            from ..processor.document_delivery_processor import DocumentDeliveryProcessor

            self._processor = DocumentDeliveryProcessor()
        return self._processor

    def query_and_download(
        self, credential_id: int, cutoff_time: datetime, tab: str = "pending", debug_mode: bool = True
    ) -> DocumentQueryResult:
        """
        查询并下载文书（三级降级策略）

        降级策略：
        1. 优先：直接 API 调用（使用缓存的 Token）
        2. 次选：Playwright 登录后使用 API
        3. 回退：Playwright 页面点击方式

        Args:
            credential_id: 账号凭证 ID
            cutoff_time: 截止时间，早于此时间的文书不处理
            tab: 查询标签页，"pending"=待查阅，"reviewed"=已查阅
            debug_mode: 调试模式，为 True 时不关闭浏览器

        Returns:
            DocumentQueryResult: 查询结果

        Requirements: 1.3, 1.4, 5.1, 5.2, 5.5
        """
        logger.info(
            f"开始查询文书: credential_id={credential_id}, "
            f"cutoff_time={cutoff_time}, tab={tab}, debug_mode={debug_mode}"
        )

        # 1. 优先尝试 API 方式（使用缓存的 Token）
        api_result = self._try_api_approach(credential_id, cutoff_time)
        if api_result is not None:
            return api_result

        # 2. API 失败，降级到 Playwright 方式
        logger.info("🔄 API 方式失败，降级到 Playwright 方式")
        return self.playwright_service.query_documents(
            credential_id=credential_id, cutoff_time=cutoff_time, tab=tab, debug_mode=debug_mode
        )

    def _try_api_approach(self, credential_id: int, cutoff_time: datetime) -> DocumentQueryResult | None:
        """
        尝试使用 API 方式查询文书

        流程：
        1. 通过 TokenService 获取 Token
        2. 使用 ApiService 查询文书
        3. 失败时返回 None，触发降级

        Args:
            credential_id: 账号凭证 ID
            cutoff_time: 截止时间

        Returns:
            查询结果，如果 API 方式失败则返回 None

        Requirements: 1.3, 1.4, 5.1, 5.2
        """
        logger.info("🚀 尝试 API 方式查询文书")

        try:
            # 获取 Token
            token = self.token_service.acquire_token(credential_id)
            if not token:
                # 记录降级日志
                AutomationLogger.log_fallback_triggered(
                    from_method="api", to_method="playwright", reason="Token 获取失败", credential_id=credential_id
                )
                return None

            logger.info(f"✅ Token 获取成功: {token[:20]}...")

            # 调用 API 查询
            result = self.api_service.query_documents(token=token, cutoff_time=cutoff_time, credential_id=credential_id)

            # 记录查询统计
            AutomationLogger.log_document_query_statistics(
                total_found=result.total_found,
                processed_count=result.processed_count,
                skipped_count=result.skipped_count,
                failed_count=result.failed_count,
                query_method="api",
                credential_id=credential_id,
            )

            return result

        except Exception as e:
            # 记录详细错误信息
            error_type = type(e).__name__
            error_msg = str(e)

            # 记录降级日志
            AutomationLogger.log_fallback_triggered(
                from_method="api",
                to_method="playwright",
                reason=error_msg,
                error_type=error_type,
                credential_id=credential_id,
            )

            # 记录详细错误信息（包含堆栈跟踪）
            AutomationLogger.log_api_error_detail(
                api_name="document_query_api",
                error_type=error_type,
                error_message=error_msg,
                stack_trace=traceback.format_exc(),
            )

            return None

    def _try_api_after_login(self, token: str, cutoff_time: datetime, credential_id: int) -> DocumentQueryResult | None:
        """
        登录成功后尝试使用 API 方式获取文书列表

        在 Playwright 登录成功获得 token 后，优先尝试 API 方式。
        如果 API 成功则返回结果，失败则返回 None 让调用方继续用 Playwright。

        Args:
            token: 登录成功后获得的 token
            cutoff_time: 截止时间
            credential_id: 凭证 ID

        Returns:
            查询结果，如果 API 失败则返回 None

        Requirements: 1.3, 1.4
        """
        logger.info("🚀 登录成功后尝试 API 方式获取文书列表")

        try:
            # 调用 API 查询
            result = self.api_service.query_documents(token=token, cutoff_time=cutoff_time, credential_id=credential_id)

            # 记录查询统计
            AutomationLogger.log_document_query_statistics(
                total_found=result.total_found,
                processed_count=result.processed_count,
                skipped_count=result.skipped_count,
                failed_count=result.failed_count,
                query_method="api_after_login",
                credential_id=credential_id,
            )

            return result

        except Exception as e:
            # 记录详细错误信息
            error_type = type(e).__name__
            error_msg = str(e)

            # 记录降级日志
            AutomationLogger.log_fallback_triggered(
                from_method="api_after_login",
                to_method="playwright_page",
                reason=error_msg,
                error_type=error_type,
                credential_id=credential_id,
            )

            # 记录详细错误信息（包含堆栈跟踪）
            AutomationLogger.log_api_error_detail(
                api_name="api_after_login",
                error_type=error_type,
                error_message=error_msg,
                stack_trace=traceback.format_exc(),
            )

            return None
