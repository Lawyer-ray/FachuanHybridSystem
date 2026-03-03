"""Data repository layer."""

import logging
from decimal import Decimal
from typing import Any

from asgiref.sync import sync_to_async
from django.core.paginator import Paginator
from django.db import connections
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.automation.models import InsuranceQuote, PreservationQuote, QuoteItemStatus, QuoteStatus
from apps.automation.services.insurance.court_insurance_client import PremiumResult
from apps.automation.services.insurance.exceptions import ValidationError
from apps.core.config import get_config
from apps.core.exceptions import NotFoundError

logger = logging.getLogger("apps.automation")


def _configure_db_settings() -> None:
    raw_settings = getattr(connections, "_settings", None)
    configured_settings = connections.configure_settings(raw_settings)
    connections._settings = configured_settings  # type: ignore


async def _db_sync(func: Any, *args: Any, **kwargs: Any) -> Any:
    def _wrapped() -> Any:
        _configure_db_settings()
        return func(*args, **kwargs)

    return await sync_to_async(_wrapped, thread_sensitive=True)()


class PreservationQuoteRepository:
    def validate_create_params(
        self, *, preserve_amount: Decimal, corp_id: str, category_id: str, credential_id: int | None
    ) -> None:
        errors: dict[str, str] = {}
        if preserve_amount <= 0:
            errors["preserve_amount"] = "保全金额必须为正数"
        if not corp_id or not corp_id.strip():
            errors["corp_id"] = "法院 ID 不能为空"
        if not category_id or not category_id.strip():
            errors["category_id"] = "分类 ID 不能为空"
        if credential_id is not None and credential_id <= 0:
            errors["credential_id"] = "凭证 ID 必须为正整数"
        if errors:
            raise ValidationError(message=_("数据验证失败"), errors=errors)  # type: ignore

    def create_quote(
        self, *, preserve_amount: Decimal, corp_id: str, category_id: str, credential_id: int | None
    ) -> PreservationQuote:
        _configure_db_settings()
        return PreservationQuote.objects.create(
            preserve_amount=preserve_amount,
            corp_id=corp_id,
            category_id=category_id,
            credential_id=credential_id,
            status=QuoteStatus.PENDING,
        )

    def get_quote_with_items(self, *, quote_id: int) -> Any:
        try:
            return PreservationQuote.objects.prefetch_related("quotes").get(id=quote_id)
        except PreservationQuote.DoesNotExist:
            raise NotFoundError(message=_("询价任务不存在"), errors={"quote_id": quote_id}) from None

    def list_quotes(
        self, *, page: int = 1, page_size: int | None = None, status: str | None = None
    ) -> tuple[list[PreservationQuote], int]:
        if page_size is None:
            page_size = get_config("pagination.default_page_size", 20)

        errors = ({},)  # type: ignore
        max_page_size = get_config("pagination.max_page_size", 100)
        if page < 1:
            errors["page"] = "页码必须大于 0"  # type: ignore
        if page_size < 1 or page_size > max_page_size:
            errors["page_size"] = f"每页数量必须在 1-{max_page_size} 之间"  # type: ignore
        if errors:
            raise ValidationError(message=_("参数验证失败"), errors=errors)  # type: ignore

        queryset = PreservationQuote.objects.all()
        if status:
            queryset = queryset.filter(status=status)
        queryset = queryset.order_by("-created_at")
        queryset = queryset.prefetch_related("quotes")
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
            "error_message",
        )

        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        return list(page_obj.object_list), paginator.count

    async def get_quote_model(self, *, quote_id: int) -> Any:
        try:
            return await _db_sync(PreservationQuote.objects.get, id=quote_id)
        except PreservationQuote.DoesNotExist as e:
            raise NotFoundError(message=_("询价任务不存在"), errors={"quote_id": quote_id}) from e

    async def mark_running(self, *, quote: PreservationQuote) -> None:
        quote.status = QuoteStatus.RUNNING
        quote.started_at = timezone.now()
        await _db_sync(quote.save, update_fields=["status", "started_at"])

    async def set_total_companies(self, *, quote: PreservationQuote, total: int) -> None:
        quote.total_companies = total
        await _db_sync(quote.save, update_fields=["total_companies"])

    async def finalize_quote(
        self,
        *,
        quote: PreservationQuote,
        success_count: int,
        failed_count: int,
        error_message: str | None,
    ) -> None:
        quote.success_count = success_count
        quote.failed_count = failed_count
        quote.finished_at = timezone.now()
        quote.error_message = error_message

        if success_count == 0:
            quote.status = QuoteStatus.FAILED
            quote.error_message = error_message or "所有保险公司查询均失败"
        elif failed_count == 0:
            quote.status = QuoteStatus.SUCCESS
        else:
            quote.status = QuoteStatus.PARTIAL_SUCCESS

        await _db_sync(
            quote.save,
            update_fields=[
                "success_count",
                "failed_count",
                "status",
                "finished_at",
                "error_message",
            ],
        )

    async def mark_failed(self, *, quote: PreservationQuote, error_message: str) -> None:
        quote.status = QuoteStatus.FAILED
        quote.error_message = error_message
        quote.finished_at = timezone.now()
        await _db_sync(quote.save, update_fields=["status", "error_message", "finished_at"])

    async def reset_for_retry(self, *, quote: PreservationQuote) -> None:
        quote.status = QuoteStatus.PENDING
        quote.error_message = None
        quote.started_at = None
        quote.finished_at = None
        await _db_sync(quote.save, update_fields=["status", "error_message", "started_at", "finished_at"])

    async def save_premium_results(self, *, quote: PreservationQuote, results: list[PremiumResult]) -> tuple[int, int]:
        logger.info(
            "开始保存报价结果",
            extra={
                "action": "save_premium_results_start",
                "quote_id": quote.id,
                "results_count": len(results),
            },
        )

        success_count = 0
        failed_count = 0
        insurance_quotes: list[Any] = []

        def clean_decimal(value: Any) -> Decimal | None:
            if value is None or value == "" or value == "null":
                return None
            try:
                return Decimal(str(value))
            except Exception:
                logger.exception("操作失败")

                return None

        for result in results:
            status = QuoteItemStatus.SUCCESS if result.status == "success" else QuoteItemStatus.FAILED
            rate_data = {}  # type: ignore
            if result.response_data and isinstance(result.response_data, dict):
                rate_data = result.response_data.get("data") or {}
            if not isinstance(rate_data, dict):
                rate_data = {}

            insurance_quotes.append(
                InsuranceQuote(
                    preservation_quote=quote,
                    company_id=result.company.c_id,
                    company_code=result.company.c_code,
                    company_name=result.company.c_name,
                    premium=result.premium,
                    min_premium=clean_decimal(rate_data.get("minPremium")),
                    min_amount=clean_decimal(rate_data.get("minAmount")),
                    max_amount=clean_decimal(rate_data.get("maxAmount")),
                    min_rate=clean_decimal(rate_data.get("minRate")),
                    max_rate=clean_decimal(rate_data.get("maxRate")),
                    max_apply_amount=clean_decimal(rate_data.get("maxApplyAmount")),
                    status=status,
                    error_message=result.error_message,
                    response_data=result.response_data,
                )
            )

            if result.status == "success":
                success_count += 1
            else:
                failed_count += 1

        await _db_sync(InsuranceQuote.objects.bulk_create, insurance_quotes)

        logger.info(
            "✅ 保存报价结果成功",
            extra={
                "action": "save_premium_results_success",
                "quote_id": quote.id,
                "total_records": len(insurance_quotes),
                "success_count": success_count,
                "failed_count": failed_count,
            },
        )
        return success_count, failed_count
