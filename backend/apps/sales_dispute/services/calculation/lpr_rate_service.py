"""
LPR利率查询服务

封装LPR利率数据的读取和分段逻辑
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, NamedTuple

from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ValidationException

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from apps.sales_dispute.models import LPRRate

logger = logging.getLogger(__name__)


class RateSegment(NamedTuple):
    """LPR利率分段区间"""

    start: date
    end: date
    rate_1y: Decimal
    rate_5y: Decimal


class LprRateService:
    """LPR利率查询服务"""

    def get_rate_at(self, query_date: date) -> LPRRate:
        """查询指定日期生效的LPR利率（生效日期 <= query_date 的最近一条）"""
        from apps.sales_dispute.models import LPRRate

        rate = LPRRate.objects.filter(effective_date__lte=query_date).order_by("-effective_date").first()
        if rate is None:
            raise ValidationException(
                message=_("缺少 %(date)s 之前的LPR利率数据") % {"date": query_date},
                code="LPR_RATE_NOT_FOUND",
            )
        return rate

    def get_all_rates(self) -> QuerySet[LPRRate]:
        """返回所有LPR利率记录（按生效日期降序）"""
        from apps.sales_dispute.models import LPRRate

        return LPRRate.objects.all()

    def get_rate_segments(self, start_date: date, end_date: date) -> list[RateSegment]:
        """
        返回 [start_date, end_date) 区间内的利率分段列表

        逻辑：
        1. 查询 effective_date <= end_date 的所有利率，按 effective_date 升序
        2. 对每条利率确定分段起止日
        3. 仅保留 start < end 的有效分段
        """
        from apps.sales_dispute.models import LPRRate

        rates = list(LPRRate.objects.filter(effective_date__lte=end_date).order_by("effective_date"))

        if not rates:
            raise ValidationException(
                message=_("缺少 %(start)s 至 %(end)s 期间的LPR利率数据") % {"start": start_date, "end": end_date},
                code="LPR_RATE_NOT_FOUND",
            )

        segments: list[RateSegment] = []

        for i, rate in enumerate(rates):
            seg_start = max(rate.effective_date, start_date)

            if i + 1 < len(rates):
                seg_end = min(rates[i + 1].effective_date, end_date)
            else:
                seg_end = end_date

            if seg_start < seg_end:
                segments.append(
                    RateSegment(
                        start=seg_start,
                        end=seg_end,
                        rate_1y=rate.rate_1y,
                        rate_5y=rate.rate_5y,
                    )
                )

        if not segments:
            raise ValidationException(
                message=_("缺少 %(start)s 至 %(end)s 期间的LPR利率数据") % {"start": start_date, "end": end_date},
                code="LPR_RATE_NOT_FOUND",
            )

        return segments
