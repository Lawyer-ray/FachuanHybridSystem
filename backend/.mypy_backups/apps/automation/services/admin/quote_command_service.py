"""Business logic services."""

from __future__ import annotations

"""
财产保全询价命令服务

负责询价任务的执行、重试、批量创建等写操作.
从 PreservationQuoteAdminService 中拆分出来.
"""


import logging
from decimal import Decimal
from typing import Any, Dict, cast

from django.db import transaction
from django.db.models import Q

from apps.automation.models import PreservationQuote, QuoteStatus
from apps.core.exceptions import BusinessException, NotFoundError, ValidationException
from apps.core.interfaces import ServiceLocator

logger = logging.getLogger(__name__)


class QuoteCommandService:
    """
    询价命令服务

    负责写操作:
    - 执行询价任务
    - 重试失败的询价
    - 批量创建询价
    - 运行单个询价
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    @property
    def preservation_quote_service(self) -> Any:
        """延迟加载财产保全询价服务"""
        if not hasattr(self, "_preservation_quote_service"):
            self._preservation_quote_service = ServiceLocator.get_preservation_quote_service()
        return self._preservation_quote_service

    async def execute_quotes(self, quote_ids: list[int]) -> dict[str, Any]:
        """
        批量执行询价任务

        Args:
            quote_ids: 询价任务ID列表

        Returns:
            Dict[str, Any]: 执行结果统计

        Raises:
            ValidationException: 参数验证失败
            BusinessException: 执行失败
        """
        if not quote_ids:
            from apps.core.exceptions import AutomationExceptions

            raise AutomationExceptions.no_quotes_selected()

        try:
            executable_quotes = PreservationQuote.objects.filter(
                id__in=quote_ids, status__in=[QuoteStatus.PENDING, QuoteStatus.FAILED]
            )

            if not executable_quotes.exists():
                from apps.core.exceptions import AutomationExceptions

                raise AutomationExceptions.no_executable_quotes()

            success_count = 0
            error_count = 0
            errors: list[Any] = []

            self.logger.info("开始批量执行询价任务", extra={})

            for quote in executable_quotes:
                try:
                    result = await self.preservation_quote_service.execute_quote(cast(int, quote.pk))
                    success_count += 1

                    self.logger.info(
                        "询价任务执行成功",
                        extra={"action": "execute_quotes", "quote_id": cast(int, quote.id), "result": result},
                    )

                except Exception as e:
                    logger.exception("操作失败")
                    error_count += 1
                    error_msg = str(e)
                    errors.append({"quote_id": cast(int, quote.id), "error": error_msg})

                    self.logger.error(
                        "询价任务执行失败",
                        extra={},
                        exc_info=True,
                    )

            result = {
                "total_requested": len(quote_ids),
                "executable_count": executable_quotes.count(),
                "success_count": success_count,
                "error_count": error_count,
                "errors": errors,
            }

            self.logger.info("批量执行询价任务完成", extra={"action": "execute_quotes", "result": result})

            return result

        except Exception as e:
            self.logger.error(
                "批量执行询价任务失败",
                extra={},
                exc_info=True,
            )
            from apps.core.exceptions import AutomationExceptions

            raise AutomationExceptions.execute_quotes_failed() from e

    @transaction.atomic
    def retry_failed_quotes(self, quote_ids: list[int] | None = None) -> dict[str, Any]:
        """
        重试失败的询价任务

        Args:
            quote_ids: 可选的询价任务ID列表,如果不提供则重试所有失败的任务

        Returns:
            Dict[str, Any]: 重试结果

        Raises:
            BusinessException: 重试失败
        """
        try:
            query = Q(status__in=[QuoteStatus.FAILED, QuoteStatus.PARTIAL_SUCCESS])
            if quote_ids:
                query &= Q(id__in=quote_ids)

            failed_quotes = PreservationQuote.objects.filter(query)

            if not failed_quotes.exists():
                return {"retried_count": 0, "message": "没有找到需要重试的询价任务"}

            retried_count = 0
            for quote in failed_quotes:
                quote.quotes.all().delete()

                quote.status = QuoteStatus.PENDING
                quote.error_message = None
                quote.started_at = None
                quote.finished_at = None
                quote.total_companies = 0
                quote.success_count = 0
                quote.failed_count = 0
                quote.save()

                retried_count += 1

            result = {}

            self.logger.info("重试失败询价任务完成", extra={})

            return result

        except Exception as e:
            self.logger.error(
                "重试失败询价任务失败",
                extra={},
                exc_info=True,
            )
            from apps.core.exceptions import AutomationExceptions

            raise AutomationExceptions.retry_failed_quotes_failed() from e

    @transaction.atomic
    def batch_create_quotes(self, quote_configs: list[dict[str, Any]]) -> dict[str, Any]:
        """
        批量创建询价任务

        Args:
            quote_configs: 询价配置列表

        Returns:
            Dict[str, Any]: 创建结果

        Raises:
            ValidationException: 参数验证失败
            BusinessException: 创建失败
        """
        if not quote_configs:
            from apps.core.exceptions import AutomationExceptions

            raise AutomationExceptions.no_quote_configs()

        try:
            created_quotes: list[Any] = []
            errors: list[Any] = []

            for i, config in enumerate(quote_configs):
                try:
                    if "preserve_amount" not in config:
                        from apps.core.exceptions import AutomationExceptions

                        raise AutomationExceptions.missing_preserve_amount()

                    preserve_amount = Decimal(str(config["preserve_amount"]))
                    if preserve_amount <= 0:
                        raise ValidationException(
                            message="保全金额必须大于0", code="INVALID_PRESERVE_AMOUNT", errors={}
                        )

                    quote = PreservationQuote.objects.create(
                        preserve_amount=preserve_amount,
                        corp_id=config.get("corp_id", "2550"),
                        category_id=config.get("category_id", "127000"),
                        credential_id=config.get("credential_id"),
                    )

                    created_quotes.append(quote)

                except Exception as e:
                    logger.exception("操作失败")
                    errors.append({"config_index": i, "config": config, "error": str(e)})

            result = {
                "created_count": len(created_quotes),
                "error_count": len(errors),
                "created_quote_ids": [cast(int, q.id) for q in created_quotes],
                "errors": errors,
            }

            self.logger.info("批量创建询价任务完成", extra={"action": "batch_create_quotes", "result": result})

            return result

        except Exception as e:
            self.logger.error(
                "批量创建询价任务失败", extra={"action": "batch_create_quotes", "error": str(e)}, exc_info=True
            )
            raise BusinessException(
                message="批量创建询价任务失败", code="BATCH_CREATE_QUOTES_FAILED", errors={"error": str(e)}
            ) from e

    def run_single_quote(self, quote_id: int) -> dict[str, Any]:
        """
        运行单个询价任务

        Args:
            quote_id: 询价任务ID

        Returns:
            Dict[str, Any]: 运行结果

        Raises:
            NotFoundError: 询价任务不存在
            ValidationException: 任务状态不允许执行
        """
        try:
            from django_q.tasks import async_task

            quote = PreservationQuote.objects.get(id=quote_id)

            if quote.status not in [QuoteStatus.PENDING, QuoteStatus.FAILED]:
                raise ValidationException(
                    message=f"任务当前状态为 {quote.get_status_display()},无法执行",
                    code="INVALID_QUOTE_STATUS",
                    errors={},
                )

            task_id = async_task(
                "apps.automation.tasks.execute_preservation_quote_task",
                quote_id,
                task_name=f"询价任务 #{quote_id}",
                timeout=600,
            )

            return {
                "success": True,
                "message": f"✅ 任务 #{quote_id} 已提交到队列,Task ID: {task_id}.请确保 Django Q 正在运行.",
            }

        except PreservationQuote.DoesNotExist:
            raise NotFoundError(message="询价任务不存在", code="QUOTE_NOT_FOUND", errors={}) from None
