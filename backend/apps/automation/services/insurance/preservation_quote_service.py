"""
财产保全询价服务

提供财产保全担保费询价的业务逻辑：
- 创建询价任务
- 执行询价流程
- 获取询价结果
- 列表查询
"""

import logging
from decimal import Decimal
from typing import Any, Optional, cast

from django.core.paginator import Paginator
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.automation.models import PreservationQuote, QuoteStatus
from apps.automation.services.insurance._quote_execution_mixin import QuoteExecutionMixin
from apps.automation.services.insurance.court_insurance_client import CourtInsuranceClient
from apps.automation.services.insurance.exceptions import ValidationError
from apps.core.config import get_config
from apps.core.exceptions import NotFoundError
from apps.core.interfaces import IAutoTokenAcquisitionService, ITokenService

logger = logging.getLogger("apps.automation")


class PreservationQuoteService(QuoteExecutionMixin):
    """
    财产保全询价服务

    职责：
    - 管理询价任务的生命周期
    - 集成 TokenService 进行 Token 管理
    - 调用 CourtInsuranceClient 执行询价
    - 持久化询价结果

    使用依赖注入，所有依赖通过构造函数传递
    """

    def __init__(
        self,
        token_service: ITokenService | None = None,
        auto_token_service: Optional["IAutoTokenAcquisitionService"] = None,
        insurance_client: CourtInsuranceClient | None = None,
    ):
        """
        初始化服务（依赖注入）

        Args:
            token_service: Token 管理服务，None 时使用 ServiceLocator 获取
            auto_token_service: 自动Token获取服务，None 时使用 ServiceLocator 获取
            insurance_client: 保险询价客户端，None 时创建默认实例
        """
        self._token_service = token_service
        self._auto_token_service = auto_token_service
        self._insurance_client = insurance_client or CourtInsuranceClient()

    @property
    def insurance_client(self) -> CourtInsuranceClient:
        """获取保险询价客户端"""
        return self._insurance_client

    @property
    def token_service(self) -> ITokenService:
        """获取 Token 服务（延迟加载）"""
        if self._token_service is None:
            from apps.core.interfaces import ServiceLocator

            self._token_service = ServiceLocator.get_token_service()
        return self._token_service

    @property
    def auto_token_service(self) -> "IAutoTokenAcquisitionService":
        """获取自动Token获取服务（延迟加载）"""
        if self._auto_token_service is None:
            from apps.core.interfaces import ServiceLocator

            self._auto_token_service = ServiceLocator.get_auto_token_acquisition_service()
        return self._auto_token_service

    @transaction.atomic
    def create_quote(
        self, preserve_amount: Decimal, corp_id: str, category_id: str, credential_id: int | None = None
    ) -> PreservationQuote:
        """
        创建询价任务

        Args:
            preserve_amount: 保全金额
            corp_id: 企业/法院 ID
            category_id: 分类 ID (cPid)
            credential_id: 凭证 ID

        Returns:
            创建的询价任务

        Raises:
            ValidationException: 数据验证失败
        """
        # 数据验证
        try:
            self._validate_create_params(
                preserve_amount=preserve_amount,
                corp_id=corp_id,
                category_id=category_id,
                credential_id=credential_id,  # type: ignore
            )
        except ValidationError as e:
            # 记录验证失败日志
            logger.warning(
                "创建询价任务验证失败",
                extra={
                    "action": "create_quote_validation_failed",
                    "preserve_amount": str(preserve_amount),
                    "corp_id": corp_id,
                    "category_id": category_id,
                    "credential_id": credential_id,
                    "errors": e.errors if hasattr(e, "errors") else str(e),
                },
            )
            raise

        # 记录任务创建开始
        logger.info(
            "创建询价任务",
            extra={
                "action": "create_quote_start",
                "preserve_amount": str(preserve_amount),
                "corp_id": corp_id,
                "category_id": category_id,
                "credential_id": credential_id,
            },
        )

        # 创建任务
        quote = PreservationQuote.objects.create(
            preserve_amount=preserve_amount,
            corp_id=corp_id,
            category_id=category_id,
            credential_id=credential_id,
            status=QuoteStatus.PENDING,
        )

        # 记录任务创建成功
        logger.info(
            "✅ 询价任务创建成功",
            extra={
                "action": "create_quote_success",
                "quote_id": quote.id,
                "status": quote.status,
                "preserve_amount": str(quote.preserve_amount),
            },
        )

        return quote

    async def execute_quote(self, quote_id: int) -> dict[str, Any]:
        """
        执行询价流程

        Args:
            quote_id: 询价任务 ID

        Returns:
            执行结果统计

        Raises:
            NotFoundError: 任务不存在
            TokenError: Token 相关错误
            BusinessError: 其他业务错误
        """
        import time

        from asgiref.sync import sync_to_async

        # 记录任务开始时间
        task_start_time = time.time()

        # 获取任务
        try:
            quote = await sync_to_async(PreservationQuote.objects.get)(id=quote_id)
        except PreservationQuote.DoesNotExist as e:
            logger.error(
                "询价任务不存在",
                extra={
                    "quote_id": quote_id,
                    "action": "execute_quote",
                },
            )
            raise NotFoundError(
                message=_("询价任务不存在"),
                code="QUOTE_NOT_FOUND",
                errors={"quote_id": quote_id},
            ) from e

        # 记录任务开始日志（包含任务 ID 和参数）
        logger.info(
            "开始执行询价任务",
            extra={
                "action": "execute_quote_start",
                "quote_id": quote.id,
                "preserve_amount": str(quote.preserve_amount),
                "corp_id": quote.corp_id,
                "category_id": quote.category_id,
                "credential_id": quote.credential_id,
                "status": quote.status,
            },
        )

        # 更新任务状态为执行中
        quote.status = QuoteStatus.RUNNING
        quote.started_at = timezone.now()
        await sync_to_async(quote.save)(update_fields=["status", "started_at"])

        try:
            # 1. 获取 Token
            token = await self._get_valid_token(quote.credential_id)

            # 2. 获取保险公司列表
            companies = await self._fetch_insurance_companies(
                token=token,
                category_id=quote.category_id,
                corp_id=quote.corp_id,
            )

            # 更新保险公司总数
            quote.total_companies = len(companies)
            await sync_to_async(quote.save)(update_fields=["total_companies"])

            # 3. 并发查询所有保险公司报价
            premium_results = await self._fetch_all_premiums(
                token=token,
                preserve_amount=quote.preserve_amount,
                corp_id=quote.corp_id,
                companies=companies,
            )

            # 4. 保存报价结果
            success_count, failed_count = await self._save_premium_results(
                quote=quote,
                results=premium_results,
            )

            # 5. 更新任务状态
            quote.success_count = success_count
            quote.failed_count = failed_count
            quote.finished_at = timezone.now()

            # 根据成功/失败情况设置状态
            if success_count == 0:
                quote.status = QuoteStatus.FAILED
                quote.error_message = _("所有保险公司查询均失败")
            elif failed_count == 0:
                quote.status = QuoteStatus.SUCCESS
            else:
                quote.status = QuoteStatus.PARTIAL_SUCCESS

            await sync_to_async(quote.save)(
                update_fields=[
                    "success_count",
                    "failed_count",
                    "status",
                    "finished_at",
                    "error_message",
                ]
            )

            # 计算执行时长
            execution_time = (quote.finished_at - quote.started_at).total_seconds()
            total_elapsed_time = time.time() - task_start_time

            # 记录任务完成日志（包含执行时长和统计信息）
            logger.info(
                "✅ 询价任务执行完成",
                extra={
                    "action": "execute_quote_complete",
                    "quote_id": quote.id,
                    "status": quote.status,
                    "total_companies": quote.total_companies,
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "execution_time_seconds": round(execution_time, 2),
                    "total_elapsed_time_seconds": round(total_elapsed_time, 2),
                    "success_rate": (
                        round(success_count / quote.total_companies * 100, 2) if quote.total_companies > 0 else 0
                    ),
                },
            )

            return {
                "quote_id": quote.id,
                "status": quote.status,
                "total_companies": quote.total_companies,
                "success_count": success_count,
                "failed_count": failed_count,
                "execution_time": execution_time,
            }

        except Exception as e:
            # 任务执行失败
            quote.status = QuoteStatus.FAILED
            quote.error_message = str(e)
            quote.finished_at = timezone.now()
            await sync_to_async(quote.save)(update_fields=["status", "error_message", "finished_at"])

            # 计算失败时的执行时长
            failed_elapsed_time = time.time() - task_start_time

            # 记录错误日志（包含完整堆栈信息）
            logger.error(
                f"❌ 询价任务执行失败: {e}",
                extra={
                    "action": "execute_quote_failed",
                    "quote_id": quote.id,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "elapsed_time_seconds": round(failed_elapsed_time, 2),
                },
                exc_info=True,  # 记录完整堆栈信息
            )

            raise

    def get_quote(self, quote_id: int) -> PreservationQuote:
        """
        获取询价结果

        Args:
            quote_id: 询价任务 ID

        Returns:
            询价任务（包含所有报价记录）

        Raises:
            NotFoundError: 任务不存在
        """
        logger.info(
            "获取询价任务",
            extra={
                "action": "get_quote",
                "quote_id": quote_id,
            },
        )

        try:
            quote = PreservationQuote.objects.prefetch_related("quotes").get(id=quote_id)

            logger.info(
                "✅ 获取询价任务成功",
                extra={
                    "action": "get_quote_success",
                    "quote_id": quote.id,
                    "status": quote.status,
                    "quotes_count": quote.quotes.count(),
                },
            )

            return quote
        except PreservationQuote.DoesNotExist as e:
            logger.error(
                "询价任务不存在",
                extra={
                    "action": "get_quote_not_found",
                    "quote_id": quote_id,
                },
            )
            raise NotFoundError(
                message=_("询价任务不存在"),
                code="QUOTE_NOT_FOUND",
                errors={"quote_id": quote_id},
            ) from e

    async def retry_quote(self, quote_id: int) -> dict[str, Any]:
        """
        重试失败的询价任务

        此方法允许重新执行失败或部分成功的询价任务。

        Args:
            quote_id: 询价任务 ID

        Returns:
            执行结果统计

        Raises:
            NotFoundError: 任务不存在
            ValidationError: 任务状态不允许重试
        """
        from asgiref.sync import sync_to_async

        # 获取任务
        try:
            quote = await sync_to_async(PreservationQuote.objects.get)(id=quote_id)
        except PreservationQuote.DoesNotExist as e:
            logger.error(
                "询价任务不存在",
                extra={
                    "quote_id": quote_id,
                    "action": "retry_quote",
                },
            )
            raise NotFoundError(
                message=_("询价任务不存在"),
                code="QUOTE_NOT_FOUND",
                errors={"quote_id": quote_id},
            ) from e

        # 检查任务状态是否允许重试
        if quote.status not in [QuoteStatus.FAILED, QuoteStatus.PARTIAL_SUCCESS]:
            logger.warning(
                "任务状态不允许重试",
                extra={
                    "action": "retry_quote_invalid_status",
                    "quote_id": quote.id,
                    "current_status": quote.status,
                },
            )
            raise ValidationError(
                message=f"任务状态为 {quote.get_status_display()}，不允许重试。只有失败或部分成功的任务可以重试。",
                errors={"status": quote.status},
            )

        logger.info(
            "开始重试询价任务",
            extra={
                "action": "retry_quote_start",
                "quote_id": quote.id,
                "previous_status": quote.status,
                "previous_success_count": quote.success_count,
                "previous_failed_count": quote.failed_count,
            },
        )

        # 重置任务状态
        quote.status = QuoteStatus.PENDING
        quote.error_message = None
        quote.started_at = None
        quote.finished_at = None
        await sync_to_async(quote.save)(
            update_fields=[
                "status",
                "error_message",
                "started_at",
                "finished_at",
            ]
        )

        # 删除之前的报价记录（可选，根据业务需求决定）
        # await sync_to_async(quote.quotes.all().delete)()

        # 执行询价
        result = await self.execute_quote(quote_id)

        logger.info(
            "✅ 重试询价任务完成",
            extra={
                "action": "retry_quote_complete",
                "quote_id": quote.id,
                "new_status": result["status"],
                "new_success_count": result["success_count"],
                "new_failed_count": result["failed_count"],
            },
        )

        return result

    def list_quotes(
        self, page: int = 1, page_size: int | None = None, status: str | None = None
    ) -> tuple[list[PreservationQuote], int]:
        """
        列表查询（优化版）

        性能优化：
        - 使用 prefetch_related 预加载 quotes 关系，避免 N+1 查询
        - 使用 only() 只查询需要的字段，减少数据传输
        - 使用索引优化排序和筛选

        Args:
            page: 页码（从 1 开始）
            page_size: 每页数量
            status: 状态筛选（可选）

        Returns:
            (任务列表, 总数)

        Raises:
            ValidationError: 参数验证失败
        """
        # 获取分页配置
        if page_size is None:
            page_size = get_config("pagination.default_page_size", 20)

        # 参数验证
        errors = {}
        max_page_size = get_config("pagination.max_page_size", 100)

        if page < 1:
            errors["page"] = "页码必须大于 0"
        if page_size < 1 or page_size > max_page_size:
            errors["page_size"] = f"每页数量必须在 1-{max_page_size} 之间"

        if errors:
            raise ValidationError(message=_("参数验证失败"), errors=errors)

        logger.info(
            "查询询价任务列表",
            extra={
                "action": "list_quotes",
                "page": page,
                "page_size": page_size,
                "status": status,
            },
        )

        # 构建查询
        queryset = PreservationQuote.objects.all()

        # 状态筛选（使用索引）
        if status:
            queryset = queryset.filter(status=status)

        # 排序（使用索引：status + created_at）
        queryset = queryset.order_by("-created_at")

        # 预加载关联的报价记录，避免 N+1 查询
        # 如果列表页面需要显示报价数量或报价详情，这会显著提升性能
        queryset = queryset.prefetch_related("quotes")

        # 只查询列表展示需要的字段，减少数据传输
        # 注意：如果需要访问其他字段，需要在这里添加
        queryset = queryset.only(
            "id",
            "preserve_amount",
            "corp_id",
            "category_id",
            "credential_id",
            "status",
            "total_companies",
            "success_count",
            "failed_count",
            "created_at",
            "started_at",
            "finished_at",
        )

        # 分页
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        logger.info(
            "✅ 查询询价任务列表成功",
            extra={
                "action": "list_quotes_success",
                "page": page,
                "page_size": page_size,
                "total_count": paginator.count,
                "returned_count": len(page_obj.object_list),
            },
        )

        return list(page_obj.object_list), paginator.count

    # ==================== 私有方法 ====================

    def _validate_create_params(
        self, preserve_amount: Decimal, corp_id: str, category_id: str, credential_id: int
    ) -> None:
        errors = {}
        if preserve_amount <= 0:
            errors["preserve_amount"] = "保全金额必须为正数"
        if not corp_id or not corp_id.strip():
            errors["corp_id"] = "法院 ID 不能为空"
        if not category_id or not category_id.strip():
            errors["category_id"] = "分类 ID 不能为空"
        if credential_id is not None and credential_id <= 0:
            errors["credential_id"] = "凭证 ID 必须为正整数"
        if errors:
            raise ValidationError(message=_("数据验证失败"), errors=errors)
