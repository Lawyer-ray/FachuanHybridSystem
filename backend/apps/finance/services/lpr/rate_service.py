"""LPR利率查询服务.

提供LPR利率数据的查询和分段计算功能.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, NamedTuple

from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ValidationException

if TYPE_CHECKING:
    from apps.finance.models.lpr_rate import LPRRate

logger = logging.getLogger(__name__)


class RateSegment(NamedTuple):
    """LPR利率分段区间."""

    start: date
    end: date
    rate_1y: Decimal
    rate_5y: Decimal


@dataclass
class PrincipalPeriod:
    """本金时间段.

    用于支持本金变动的计算场景（如租金）。

    Attributes:
        start_date: 开始日期
        end_date: 结束日期
        principal: 本金金额
    """

    start_date: date
    end_date: date
    principal: Decimal


class LPRRateService:
    """LPR利率查询服务."""

    def get_rate_at(self, query_date: date) -> LPRRate:
        """查询指定日期生效的LPR利率.

        返回生效日期 <= query_date 的最近一条记录。

        Args:
            query_date: 查询日期

        Returns:
            LPR利率记录

        Raises:
            ValidationException: 找不到利率数据
        """
        from apps.finance.models.lpr_rate import LPRRate

        rate = LPRRate.objects.filter(effective_date__lte=query_date).order_by("-effective_date").first()
        if rate is None:
            raise ValidationException(
                message=_("缺少 %(date)s 之前的LPR利率数据") % {"date": query_date},
                code="LPR_RATE_NOT_FOUND",
            )
        return rate

    def get_rate_by_date_range(self, start_date: date, end_date: date, rate_type: str = "1y") -> Decimal:
        """查询日期范围内的适用利率.

        如果范围内利率发生变化，返回最新生效的利率。

        Args:
            start_date: 开始日期
            end_date: 结束日期
            rate_type: 利率类型，"1y" 或 "5y"

        Returns:
            适用利率
        """
        rate = self.get_rate_at(end_date)
        if rate_type == "5y":
            return rate.rate_5y
        return rate.rate_1y

    def get_rate_segments(self, start_date: date, end_date: date) -> list[RateSegment]:
        """返回 [start_date, end_date] 区间内的利率分段列表（包含结束日期）.

        逻辑：
        1. 查询 effective_date <= end_date 的所有利率，按 effective_date 升序
        2. 对每条利率确定分段起止日（闭区间）
        3. 仅保留 start <= end 的有效分段

        Args:
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            利率分段列表

        Raises:
            ValidationException: 找不到利率数据
        """
        from datetime import timedelta

        from apps.finance.models.lpr_rate import LPRRate

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
                # 下一条利率生效前一天为本段结束
                seg_end = min(rates[i + 1].effective_date - timedelta(days=1), end_date)
            else:
                seg_end = end_date

            if seg_start <= seg_end:
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

    def get_latest_rate(self) -> LPRRate:
        """获取最新的LPR利率.

        Returns:
            最新的LPR利率记录

        Raises:
            ValidationException: 找不到利率数据
        """
        from apps.finance.models.lpr_rate import LPRRate

        rate = LPRRate.objects.first()
        if rate is None:
            raise ValidationException(
                message=_("系统中没有LPR利率数据"),
                code="LPR_RATE_NOT_FOUND",
            )
        return rate

    def is_data_current(self) -> bool:
        """检查最新 LPR 数据是否为当前期间.

        LPR 通常每月 20 日前后发布：
        - 同年同月 → 当前
        - 今天 < 20 日且最新数据为上月 → 当前
        - 其他情况 → 可能过期

        Returns:
            True 表示数据最新，False 表示可能需要同步
        """
        today = date.today()

        try:
            latest = self.get_latest_rate()
        except ValidationException:
            return False

        ld = latest.effective_date
        if ld.year == today.year and ld.month == today.month:
            return True
        if today.day < 20:
            if ld.year == today.year and ld.month == today.month - 1:
                return True
            if today.month == 1 and ld.month == 12 and ld.year == today.year - 1:
                return True
        return False

    def get_rate_history(
        self, start_date: date | None = None, end_date: date | None = None, limit: int | None = None
    ) -> list[LPRRate]:
        """获取利率历史记录.

        Args:
            start_date: 开始日期筛选
            end_date: 结束日期筛选
            limit: 返回数量限制

        Returns:
            LPR利率记录列表
        """
        from apps.finance.models.lpr_rate import LPRRate

        queryset = LPRRate.objects.all()

        if start_date:
            queryset = queryset.filter(effective_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(effective_date__lte=end_date)

        if limit:
            queryset = queryset[:limit]

        return list(queryset)
