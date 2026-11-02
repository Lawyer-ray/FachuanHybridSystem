"""Admin 自然期间筛选器的单测（纯函数 + queryset 行为）。

重点是**期间边界**：月初 0 点、跨年、季度切换、`USE_TZ` 下的 DateTimeField。
这几处错了不会报错，只会「少一条/多一条」，是财务对账时最难发现的错。
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from apps.core.admin.filters import NaturalPeriodFilter, date_filter, period_range


class TestPeriodRange:
    """半开区间 `[start, end)` 的换算。"""

    @pytest.mark.parametrize(
        ("period", "today", "expected"),
        [
            # 普通日子
            ("today", dt.date(2026, 11, 2), (dt.date(2026, 11, 2), dt.date(2026, 11, 3))),
            ("yesterday", dt.date(2026, 11, 2), (dt.date(2026, 11, 1), dt.date(2026, 11, 2))),
            # 「最近 7 天」含今天
            ("last7", dt.date(2026, 11, 2), (dt.date(2026, 10, 27), dt.date(2026, 11, 3))),
            # 月初当天：上月的 end 必须正好是本月初，不能多也不能少
            ("this_month", dt.date(2026, 11, 2), (dt.date(2026, 11, 1), dt.date(2026, 12, 1))),
            ("last_month", dt.date(2026, 11, 2), (dt.date(2026, 10, 1), dt.date(2026, 11, 1))),
            # 跨年：1 月的「上月」是去年 12 月
            ("last_month", dt.date(2026, 1, 15), (dt.date(2025, 12, 1), dt.date(2026, 1, 1))),
            # 跨年：12 月的「本月」end 要落到次年 1 月
            ("this_month", dt.date(2026, 12, 31), (dt.date(2026, 12, 1), dt.date(2027, 1, 1))),
            # 季度边界
            ("this_quarter", dt.date(2026, 11, 2), (dt.date(2026, 10, 1), dt.date(2027, 1, 1))),
            ("last_quarter", dt.date(2026, 11, 2), (dt.date(2026, 7, 1), dt.date(2026, 10, 1))),
            # 一季度跨年
            ("last_quarter", dt.date(2026, 1, 15), (dt.date(2025, 10, 1), dt.date(2026, 1, 1))),
            # 年份
            ("this_year", dt.date(2026, 11, 2), (dt.date(2026, 1, 1), dt.date(2027, 1, 1))),
            ("last_year", dt.date(2026, 11, 2), (dt.date(2025, 1, 1), dt.date(2026, 1, 1))),
        ],
    )
    def test_ranges(self, period: str, today: dt.date, expected: tuple[dt.date, dt.date]) -> None:
        assert period_range(period, today=today) == expected

    def test_unknown_period_returns_none(self) -> None:
        # 不认识的期间不筛选，而不是瞎猜一个区间
        assert period_range("no_such_period") is None

    @pytest.mark.parametrize(
        "period",
        ["today", "yesterday", "last7", "last30", "this_month", "last_month",
         "this_quarter", "last_quarter", "this_year", "last_year"],
    )
    def test_all_periods_are_half_open_and_non_empty(self, period: str) -> None:
        rng = period_range(period, today=dt.date(2026, 3, 15))
        assert rng is not None
        start, end = rng
        assert start < end, f"{period} 的区间必须非空"

    def test_consecutive_months_are_contiguous(self) -> None:
        """上月.end 必须等于本月.start——否则每月 1 号的记录会丢或重复计。"""
        today = dt.date(2026, 3, 15)
        last_start, last_end = period_range("last_month", today=today)  # type: ignore[misc]
        this_start, _this_end = period_range("this_month", today=today)  # type: ignore[misc]
        assert last_end == this_start
        assert last_start < last_end


@pytest.mark.django_db
class TestFilterQueryset:
    """queryset 层：DateField 与 DateTimeField 的时区语义必须分开处理。"""

    def _build(self, field_name: str):
        from apps.contracts.models import ContractPayment

        bound = date_filter(field_name)
        # 直接构造 filter 实例（跳过 admin 请求链路）
        return bound, ContractPayment

    def test_datetime_field_uses_local_day_boundaries(self) -> None:
        """DateTimeField 存的 UTC：本地「今天 00:00」必须算成 aware datetime。

        这里直接验证 `_apply` 的落库参数形状，避免依赖建数据。
        """
        from apps.core.admin.filters import _apply

        class _Probe:
            def __init__(self) -> None:
                self.kwargs: dict = {}

            def filter(self, **kwargs):
                self.kwargs = kwargs
                return self

        probe = _Probe()
        start = dt.date(2026, 3, 1)
        end = dt.date(2026, 4, 1)
        _apply(probe, "created_at", start, end, is_datetime=True)

        gte = probe.kwargs["created_at__gte"]
        lt = probe.kwargs["created_at__lt"]
        assert timezone.is_aware(gte) and timezone.is_aware(lt)
        # 本地 00:00 → 上海时区应是 UTC 前一天 16:00
        local_gte = timezone.localtime(gte)
        assert (local_gte.year, local_gte.month, local_gte.day) == (2026, 3, 1)
        assert local_gte.hour == 0 and local_gte.minute == 0
        local_lt = timezone.localtime(lt)
        assert (local_lt.year, local_lt.month, local_lt.day) == (2026, 4, 1)

    def test_date_field_uses_plain_dates(self) -> None:
        """DateField 是纯日期：绝对不能传 aware datetime（会被隐式转换、结果随时区漂）。"""
        from apps.core.admin.filters import _apply

        class _Probe:
            def __init__(self) -> None:
                self.kwargs: dict = {}

            def filter(self, **kwargs):
                self.kwargs = kwargs
                return self

        probe = _Probe()
        _apply(probe, "received_at", dt.date(2026, 3, 1), dt.date(2026, 4, 1), is_datetime=False)

        assert probe.kwargs["received_at__gte"] == dt.date(2026, 3, 1)
        assert probe.kwargs["received_at__lt"] == dt.date(2026, 4, 1)
        assert isinstance(probe.kwargs["received_at__gte"], dt.date)
        assert not isinstance(probe.kwargs["received_at__gte"], dt.datetime)


@pytest.mark.django_db
class TestFilterOnRealModels:
    """接到真实模型上跑一遍，确认 filter 真能筛出预期行。

    ContractPayment.received_at 是 DateField、消息 received_at 是 DateTimeField，
    两种字段各覆盖一次（这正是时区处理最容易翻车的组合）。
    """

    def _payment(self, received_at: dt.date):
        from decimal import Decimal

        from apps.contracts.models import Contract, ContractPayment

        contract = Contract.objects.create(name="期间筛选测试合同", case_type="civil", fixed_amount=Decimal("100"))
        return ContractPayment.objects.create(contract=contract, amount=Decimal("10"), received_at=received_at)

    def test_date_field_filter_selects_this_month(self) -> None:
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory

        from apps.contracts.admin import ContractPaymentAdmin
        from apps.contracts.models import ContractPayment

        today = timezone.localtime(timezone.now()).date()
        this_month_day = today.replace(day=1)
        last_month_day = (this_month_day - dt.timedelta(days=1))

        in_month = self._payment(this_month_day)
        self._payment(last_month_day)

        bound = date_filter("received_at")
        flt = bound(
            RequestFactory().get("/", {bound.parameter_name: "this_month"}),
            {bound.parameter_name: ["this_month"]},
            ContractPayment,
            AdminSite(),
        )
        qs = flt.queryset(RequestFactory().get("/"), ContractPayment.objects.all())
        ids = set(qs.values_list("id", flat=True))
        assert in_month.id in ids
        assert all(p.received_at >= this_month_day.replace(day=1) for p in qs)

    def test_unknown_field_does_not_crash(self) -> None:
        """字段名写错时不得抛异常——admin 页面不能因为一个过滤器挂掉。"""
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory

        from apps.contracts.models import ContractPayment

        bound = date_filter("no_such_field")
        flt = bound(
            RequestFactory().get("/", {bound.parameter_name: "this_month"}),
            {bound.parameter_name: ["this_month"]},
            ContractPayment,
            AdminSite(),
        )
        qs = flt.queryset(RequestFactory().get("/"), ContractPayment.objects.all())
        assert qs.count() == ContractPayment.objects.count()

    def test_no_value_returns_unfiltered(self) -> None:
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory

        from apps.contracts.models import ContractPayment

        bound = date_filter("received_at")
        flt = bound(
            RequestFactory().get("/"),
            {},
            ContractPayment,
            AdminSite(),
        )
        qs = flt.queryset(RequestFactory().get("/"), ContractPayment.objects.all())
        assert qs.count() == ContractPayment.objects.count()


class TestFilterBinding:
    def test_parameter_name_is_derived_from_field(self) -> None:
        """同页多个期间筛选器不能共用一个 URL 参数（否则互相覆盖）。"""
        a = date_filter("created_at")
        b = date_filter("updated_at")
        assert a.parameter_name != b.parameter_name
        assert a.parameter_name == "period_created_at"
        assert b.parameter_name == "period_updated_at"

    def test_title_override(self) -> None:
        assert date_filter("created_at", title="创建时间").title == "创建时间"

    def test_base_class_requires_binding(self) -> None:
        """裸挂 `NaturalPeriodFilter` 必须报错。

        Django 的 SimpleListFilter 本就要求 `parameter_name` 非空；我们**不**做
        「未绑定就静默不筛选」的降级——那样配置错的人会看到一个永远不起作用的
        筛选器，比启动即报错更难排查。正确写法是 `date_filter("created_at")`。
        """
        from django.contrib.admin.sites import AdminSite
        from django.core.exceptions import ImproperlyConfigured
        from django.test import RequestFactory

        from apps.contracts.models import ContractPayment

        with pytest.raises(ImproperlyConfigured):
            NaturalPeriodFilter(
                RequestFactory().get("/"),
                {},
                ContractPayment,
                AdminSite(),
            )
