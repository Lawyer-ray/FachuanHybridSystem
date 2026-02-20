"""Business logic services."""

from django.utils.translation import gettext_lazy as _
from __future__ import annotations

"""
财产保全询价查询服务

负责询价统计分析和结果对比等只读操作.
从 PreservationQuoteAdminService 中拆分出来.
"""


import logging
from datetime import timedelta
from typing import Any, Dict, cast

from django.db.models import Avg, Count, Max, Min, Q
from django.utils import timezone

from apps.automation.models import InsuranceQuote, PreservationQuote, QuoteItemStatus, QuoteStatus
from apps.core.exceptions import BusinessException, NotFoundError


class QuoteQueryService:
    """
    询价查询服务

    负责只读操作:
    - 询价统计分析
    - 询价结果对比
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def get_quote_statistics(self, queryset: Any | None = None) -> dict[str, Any]:
        """
        获取询价统计数据

        Args:
            queryset: 可选的查询集,如果不提供则统计所有询价任务

        Returns:
            Dict[str, Any]: 统计数据

        Raises:
            BusinessException: 统计失败
        """
        try:
            if queryset is None:
                queryset = PreservationQuote.objects.all()

            total_quotes = queryset.count()

            status_stats = self._build_status_stats(queryset, total_quotes)
            success_rate = self._calc_success_rate(queryset, total_quotes)
            amount_stats = self._build_amount_stats(queryset)
            amount_range_stats = self._build_amount_range_stats(queryset, total_quotes)
            insurance_stats = self._build_insurance_stats(queryset)
            date_stats = self._build_date_stats(queryset)
            avg_duration = self._calc_avg_duration(queryset)

            result = {
                "total_quotes": total_quotes,
                "status_stats": status_stats,
                "success_rate": success_rate,
                "amount_stats": amount_stats,
                "amount_range_stats": amount_range_stats,
                "insurance_stats": insurance_stats,
                "date_stats": date_stats,
                "avg_duration": avg_duration,
            }

            self.logger.info("获取询价统计数据完成", extra={})

            return result

        except Exception as e:
            self.logger.error(
                "获取询价统计数据失败", extra={"action": "get_quote_statistics", "error": str(e)}, exc_info=True
            )
            from apps.core.exceptions import BusinessException

            raise BusinessException(
                message=_("获取询价统计数据失败"),
                code="GET_QUOTE_STATS_FAILED",
                errors={},
            ) from e

    def get_quote_comparison(self, quote_id: int) -> dict[str, Any]:
        """
        获取询价结果对比分析

        Args:
            quote_id: 询价任务ID

        Returns:
            Dict[str, Any]: 对比分析结果

        Raises:
            NotFoundError: 询价任务不存在
            BusinessException: 分析失败
        """
        try:
            try:
                quote = PreservationQuote.objects.get(id=quote_id)
            except PreservationQuote.DoesNotExist:
                raise NotFoundError(message=_("询价任务不存在"), code="QUOTE_NOT_FOUND", errors={}) from None

            successful_quotes = quote.quotes.filter(status=QuoteItemStatus.SUCCESS, min_amount__isnull=False).order_by(
                "min_amount"
            )

            if not successful_quotes.exists():
                return {
                    "quote_id": quote_id,
                    "preserve_amount": float(quote.preserve_amount),
                    "comparison_data": [],
                    "statistics": {},
                    "message": "暂无成功的报价数据",
                }

            comparison_data, premiums = self._build_comparison_data(quote, successful_quotes)
            statistics = self._build_comparison_statistics(comparison_data, premiums)

            result = {
                "quote_id": quote_id,
                "preserve_amount": float(quote.preserve_amount),
                "comparison_data": comparison_data,
                "statistics": statistics,
            }

            self.logger.info(
                "获取询价对比分析完成",
                extra={
                    "action": "get_quote_comparison",
                    "quote_id": quote_id,
                    "successful_quotes": len(comparison_data),
                },
            )

            return result

        except NotFoundError:
            raise
        except Exception as e:
            self.logger.error(
                "获取询价对比分析失败",
                extra={},
                exc_info=True,
            )
            raise BusinessException(
                message=_("获取询价对比分析失败"), code="GET_QUOTE_COMPARISON_FAILED", errors={"error": str(e)}
            ) from e

    # ---- 内部辅助方法 ----

    def _build_status_stats(self, queryset: Any, total_quotes: int) -> dict[str, Any]:
        status_stats = {}
        for status_choice in QuoteStatus.choices:
            status_code = status_choice[0]
            status_name = status_choice[1]
            count = queryset.filter(status=status_code).count()
            status_stats[status_code] = {
                "name": status_name,
                "count": count,
                "percentage": (count / total_quotes * 100) if total_quotes > 0 else 0,
            }
        return status_stats

    def _calc_success_rate(self, queryset: Any, total_quotes: int) -> Any:
        success_quotes = queryset.filter(status=QuoteStatus.SUCCESS)
        return (success_quotes.count() / total_quotes * 100) if total_quotes > 0 else 0

    def _build_amount_stats(self, queryset: Any) -> dict[str, Any]:
        return queryset.aggregate(
            total_amount=Count("preserve_amount"),
            min_amount=Min("preserve_amount"),
            max_amount=Max("preserve_amount"),
            avg_amount=Avg("preserve_amount"),
        )

    def _build_amount_range_stats(self, queryset: Any, total_quotes: int) -> list[Any]:
        amount_ranges: list[Any] = [
            (0, 10000, "1万以下"),
            (10000, 100000, "1-10万"),
            (100000, 1000000, "10-100万"),
            (1000000, 10000000, "100-1000万"),
            (10000000, float("inf"), "1000万以上"),
        ]

        stats: list[Any] = []
        for min_val, max_val, label in amount_ranges:
            if max_val == float("inf"):
                count = queryset.filter(preserve_amount__gte=min_val).count()
            else:
                count = queryset.filter(preserve_amount__gte=min_val, preserve_amount__lt=max_val).count()

            stats.append(
                {
                    "range": label,
                    "count": count,
                    "percentage": (count / total_quotes * 100) if total_quotes > 0 else 0,
                }
            )
        return stats

    def _build_insurance_stats(self, queryset: Any) -> list[Any]:
        return list(
            InsuranceQuote.objects.filter(preservation_quote__in=queryset)
            .values("company_name")
            .annotate(
                total_quotes=Count("id"),
                success_quotes=Count("id", filter=Q(status=QuoteItemStatus.SUCCESS)),
                avg_premium=Avg("min_amount", filter=Q(status=QuoteItemStatus.SUCCESS)),
            )
            .order_by("-total_quotes")[:20]
        )

    def _build_date_stats(self, queryset: Any) -> list[Any]:
        now = timezone.now()
        date_stats: list[Any] = []
        for i in range(30):
            date = (now - timedelta(days=i)).date()
            day_count = queryset.filter(created_at__date=date).count()
            day_success = queryset.filter(created_at__date=date, status=QuoteStatus.SUCCESS).count()

            date_stats.append({"date": date.strftime("%m-%d"), "total": day_count, "success": day_success})

        date_stats.reverse()
        return date_stats

    def _calc_avg_duration(self, queryset: Any) -> Any:
        duration_stats: list[Any] = []
        completed_quotes = queryset.filter(started_at__isnull=False, finished_at__isnull=False)

        for quote in completed_quotes:
            duration = (quote.finished_at - quote.started_at).total_seconds()
            duration_stats.append(duration)

        return sum(duration_stats) / len(duration_stats) if duration_stats else 0

    def _build_comparison_data(self, quote: Any, successful_quotes: Any) -> tuple[Any, ...]:
        comparison_data: list[Any] = []
        premiums: list[Any] = []

        for i, insurance_quote in enumerate(successful_quotes):
            premium = float(insurance_quote.min_amount)
            premiums.append(premium)

            rate = premium / float(quote.preserve_amount) * 100

            comparison_data.append(
                {
                    "rank": i + 1,
                    "company_name": insurance_quote.company_name,
                    "premium": premium,
                    "rate": rate,
                    "max_apply_amount": (
                        float(insurance_quote.max_apply_amount) if insurance_quote.max_apply_amount else None
                    ),
                    "is_best": i == 0,
                }
            )

        return comparison_data, premiums

    def _build_comparison_statistics(self, comparison_data: list[Any], premiums: list[Any]) -> dict[str, Any]:
        return {
            "total_companies": len(comparison_data),
            "min_premium": min(premiums),
            "max_premium": max(premiums),
            "avg_premium": sum(premiums) / len(premiums),
            "price_range": max(premiums) - min(premiums),
            "savings_amount": max(premiums) - min(premiums),
            "savings_percentage": ((max(premiums) - min(premiums)) / max(premiums) * 100) if max(premiums) > 0 else 0,
        }
