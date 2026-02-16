"""
文书送达查询服务

负责 API 和 Playwright 方式的文书查询逻辑.
"""

import logging
import math
import traceback
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from apps.automation.utils.logging import AutomationLogger

from .data_classes import DocumentQueryResult, DocumentRecord
from .repo.document_history_repo import DocumentHistoryRepo
from .utils.time_parser import make_aware_if_needed

if TYPE_CHECKING:
    from apps.core.interfaces import ICaseNumberService

    from .court_document_api_client import CourtDocumentApiClient
    from .token.document_delivery_token_service import DocumentDeliveryTokenService

logger = logging.getLogger("apps.automation")


class DocumentQueryService:
    """文书查询服务 - 负责查询逻辑"""

    def __init__(
        self,
        api_client: Optional["CourtDocumentApiClient"] = None,
        token_service: Optional["DocumentDeliveryTokenService"] = None,
        case_number_service: Optional["ICaseNumberService"] = None,
        history_repo: DocumentHistoryRepo | None = None,
    ) -> None:
        """
        初始化文书查询服务

        Args:
            api_client: API 客户端实例(可选,用于依赖注入)
            token_service: Token 管理服务实例(可选,用于依赖注入)
            case_number_service: 案号服务实例(可选,用于依赖注入)
        """
        self._api_client = api_client
        self._token_service = token_service
        self._case_number_service = case_number_service
        self._history_repo = history_repo

        logger.debug("DocumentQueryService 初始化完成")

    @property
    def api_client(self) -> "CourtDocumentApiClient":
        if self._api_client is None:
            raise RuntimeError("DocumentQueryService.api_client 未注入")
        return self._api_client

    @property
    def token_service(self) -> "DocumentDeliveryTokenService":
        if self._token_service is None:
            raise RuntimeError("DocumentQueryService.token_service 未注入")
        return self._token_service

    @property
    def case_number_service(self) -> "ICaseNumberService":
        if self._case_number_service is None:
            raise RuntimeError("DocumentQueryService.case_number_service 未注入")
        return self._case_number_service

    @property
    def history_repo(self) -> DocumentHistoryRepo:
        if self._history_repo is None:
            raise RuntimeError("DocumentQueryService.history_repo 未注入")
        return self._history_repo

    # ==================== Token 获取方法 ====================

    def acquire_token(self, credential_id: int) -> str | None:
        """
        获取 Token(带缓存和自动刷新)

        委托给 DocumentDeliveryTokenService 执行,统一 Token 获取逻辑

        Args:
            credential_id: 账号凭证 ID

        Returns:
            Token 字符串,获取失败返回 None
        """
        return self.token_service.acquire_token(credential_id)

    def refresh_token_if_expired(self, credential_id: int, current_token: str) -> str | None:
        """
        检查 Token 是否过期,如果过期则刷新

        Args:
            credential_id: 凭证 ID
            current_token: 当前 Token

        Returns:
            有效的 Token(可能是原 Token 或新获取的 Token),
            刷新失败返回 None
        """
        return self.token_service.refresh_token_if_expired(credential_id, current_token)

    # ==================== API 查询方法 ====================

    def try_api_approach(self, credential_id: int, cutoff_time: datetime) -> DocumentQueryResult | None | None:
        """
        尝试使用 API 方式查询文书

        Args:
            credential_id: 账号凭证 ID
            cutoff_time: 截止时间

        Returns:
            查询结果,如果 API 方式失败则返回 None
        """
        logger.info("🚀 尝试 API 方式查询文书")

        try:
            # 获取 Token
            token = self.acquire_token(credential_id)
            if not token:
                AutomationLogger.log_fallback_triggered(
                    from_method="api", to_method="playwright", reason="Token 获取失败", credential_id=credential_id
                )
                return None

            logger.info("✅ Token 获取成功")

            # 调用 API 查询
            result = self.query_via_api(token=token, cutoff_time=cutoff_time, credential_id=credential_id)

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
            logger.exception("操作失败")
            error_type = type(e).__name__
            error_msg = str(e)

            AutomationLogger.log_fallback_triggered(
                from_method="api",
                to_method="playwright",
                reason=error_msg,
                error_type=error_type,
                credential_id=credential_id,
            )

            AutomationLogger.log_api_error_detail(
                api_name="document_query_api",
                error_type=error_type,
                error_message=error_msg,
                stack_trace=traceback.format_exc(),
            )

            return None

    def query_via_api(self, token: str, cutoff_time: datetime, credential_id: int) -> DocumentQueryResult:
        """
        通过 API 查询文书

        Args:
            token: 认证令牌
            cutoff_time: 截止时间
            credential_id: 账号凭证 ID

        Returns:
            DocumentQueryResult: 查询结果
        """
        logger.info(f"开始 API 查询文书: cutoff_time={cutoff_time}")

        result = DocumentQueryResult(
            total_found=0, processed_count=0, skipped_count=0, failed_count=0, case_log_ids=[], errors=[]
        )

        page_size = 20
        page_num = 1

        try:
            # 获取第一页,确定总数
            first_response = self.api_client.fetch_document_list(token=token, page_num=page_num, page_size=page_size)

            total = first_response.total
            result.total_found = total

            logger.info(f"API 查询: 总文书数={total}")

            if total == 0:
                logger.info("没有文书需要处理")
                return result

            # 计算总页数
            total_pages = math.ceil(total / page_size)
            logger.info(f"分页计算: total={total}, page_size={page_size}, total_pages={total_pages}")

            # 返回结果,让调用方处理文书
            # 这里只负责查询,不负责处理
            return result

        except Exception as e:
            error_msg = f"API 查询失败: {e!s}"
            logger.error(error_msg)
            result.errors.append(error_msg)
            raise

    def try_api_after_login(
        self, token: str, cutoff_time: datetime, credential_id: int
    ) -> DocumentQueryResult | None | None:
        """
        登录成功后尝试使用 API 方式获取文书列表

        Args:
            token: 登录成功后获得的 token
            cutoff_time: 截止时间
            credential_id: 凭证 ID

        Returns:
            查询结果,如果 API 失败则返回 None
        """
        logger.info("🚀 登录成功后尝试 API 方式获取文书列表")

        try:
            result = self.query_via_api(token=token, cutoff_time=cutoff_time, credential_id=credential_id)

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
            logger.exception("操作失败")
            error_type = type(e).__name__
            error_msg = str(e)

            AutomationLogger.log_fallback_triggered(
                from_method="api_after_login",
                to_method="playwright_page",
                reason=error_msg,
                error_type=error_type,
                credential_id=credential_id,
            )

            AutomationLogger.log_api_error_detail(
                api_name="api_after_login",
                error_type=error_type,
                error_message=error_msg,
                stack_trace=traceback.format_exc(),
            )

            return None

    # ==================== 文书检查方法 ====================

    def should_process_api_document(self, record: DocumentRecord, cutoff_time: datetime, credential_id: int) -> bool:
        """
        判断是否需要处理该 API 文书记录

        Args:
            record: API 文书记录
            cutoff_time: 截止时间
            credential_id: 账号凭证 ID

        Returns:
            是否需要处理
        """
        # 1. 解析 fssj 字符串为 datetime
        send_time = record.parse_fssj()

        if send_time is None:
            logger.warning(f"无法解析发送时间: {record.fssj}, 默认处理")
            return True

        # 2. 比较 fssj 与 cutoff_time
        send_time = make_aware_if_needed(send_time)

        if send_time <= cutoff_time:
            logger.info(f"⏰ 文书时间 {send_time} 早于截止时间 {cutoff_time},跳过")
            return False

        return self.history_repo.should_process(credential_id, record.ah, send_time)

    def check_api_document_not_processed(self, credential_id: int, record: DocumentRecord) -> bool:
        send_time = record.parse_fssj()
        if send_time is None:
            return True
        return self.history_repo.should_process(credential_id, record.ah, make_aware_if_needed(send_time))
