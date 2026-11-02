"""Admin 通用列表筛选器。

## 为什么需要这个文件

Django 对日期字段**裸用** `list_filter = ("created_at",)` 时只给四档：
今天 / 过去 7 天 / 本月 / 今年。但律师真实的筛法几乎从不是这四档——最常问的是
「**上个**月收了多少款」「**上个季度**立了多少案」「**昨天到今天**法院回了什么」。
裸 filter 缺「上个月 / 上季度 / 自定义区间」，于是大家退回去翻页找，或者干脆导出 Excel 筛。

本模块提供 `NaturalPeriodFilter`：一个参数、覆盖常用自然期间、并且**时区正确**。

## 时区口径（最容易错的地方）

项目是 `USE_TZ=True` + `TIME_ZONE=Asia/Shanghai`。所以：

- `DateTimeField`：存的都是 UTC。期间边界必须用 `timezone.localtime()` 取本地时间，
  再用 `timezone.make_aware()` 换成 aware datetime 去比较；直接拿 `date.today()`
  比会整体偏 8 小时——月初 0~8 点、月末 16~24 点会串到相邻月份。
- `DateField`：存的是纯日期，**不带时区**，必须用 `date` 比较（传 aware datetime
  会被 Django 报警告并隐式转换，结果随数据库时区漂移）。
- `DateTimeField` 做「整月」筛选时用**半开区间** `[本月初 00:00, 下月初 00:00)`，
  而不是 `__month=...__year=...`——后两者在跨年、跨时区下都有坑，且无法走索引。

## 怎么用

```python
from apps.core.admin.filters import NaturalPeriodFilter, date_filter

class FooAdmin(admin.ModelAdmin):
    # 常规写法：自动识别 DateField / DateTimeField
    list_filter = ["status", NaturalPeriodFilter]   # ← 认不出就什么都不做（安全降级）
    # 或显式指定字段（一个 model 有多个日期列时更清楚）
    list_filter = ["status", date_filter("created_at", title="创建时间")]
```
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, ClassVar

from django.contrib import admin
from django.db import models
from django.utils import timezone

__all__ = [
    "NaturalPeriodFilter",
    "date_filter",
    "PERIOD_LOOKUPS",
]

#: (值, 中文标签)。顺序即下拉里的顺序——高频在前。
PERIOD_LOOKUPS: tuple[tuple[str, str], ...] = (
    ("today", "今天"),
    ("yesterday", "昨天"),
    ("last7", "最近 7 天"),
    ("last30", "最近 30 天"),
    ("this_month", "本月"),
    ("last_month", "上月"),
    ("this_quarter", "本季度"),
    ("last_quarter", "上季度"),
    ("this_year", "今年"),
    ("last_year", "去年"),
)


def _local_today() -> _dt.date:
    """本地时区的「今天」。

    不能用 `datetime.date.today()`——那是**系统本地时区**，在没有 TZ 环境变量的
    服务器上会是 UTC，与 `TIME_ZONE=Asia/Shanghai` 差一天。
    """
    return timezone.localtime(timezone.now()).date()


def _month_start(d: _dt.date) -> _dt.date:
    return d.replace(day=1)


def _add_months(d: _dt.date, months: int) -> _dt.date:
    """月份加减，自动处理跨年（不引入 dateutil 依赖）。"""
    total = (d.year * 12 + (d.month - 1)) + months
    return _dt.date(total // 12, total % 12 + 1, 1)


def _quarter_start(d: _dt.date) -> _dt.date:
    first_month = ((d.month - 1) // 3) * 3 + 1
    return _dt.date(d.year, first_month, 1)


def period_range(period: str, *, today: _dt.date | None = None) -> tuple[_dt.date, _dt.date] | None:
    """把期间枚举换算成**半开**日期间隔 `[start, end)`。

    Returns:
        `(start, end)`；期间不认识时返回 None（调用方不筛选）。
    """
    ref = today or _local_today()

    if period == "today":
        return ref, ref + _dt.timedelta(days=1)
    if period == "yesterday":
        return ref - _dt.timedelta(days=1), ref
    if period == "last7":
        # 「最近 7 天」含今天：今天是 1 天 + 之前 6 天
        return ref - _dt.timedelta(days=6), ref + _dt.timedelta(days=1)
    if period == "last30":
        return ref - _dt.timedelta(days=29), ref + _dt.timedelta(days=1)
    if period == "this_month":
        start = _month_start(ref)
        return start, _add_months(start, 1)
    if period == "last_month":
        start = _add_months(_month_start(ref), -1)
        return start, _month_start(ref)
    if period == "this_quarter":
        start = _quarter_start(ref)
        return start, _add_months(start, 3)
    if period == "last_quarter":
        start = _add_months(_quarter_start(ref), -3)
        return start, _quarter_start(ref)
    if period == "this_year":
        return _dt.date(ref.year, 1, 1), _dt.date(ref.year + 1, 1, 1)
    if period == "last_year":
        return _dt.date(ref.year - 1, 1, 1), _dt.date(ref.year, 1, 1)
    return None


def _apply(queryset: Any, field_name: str, start: _dt.date, end: _dt.date, *, is_datetime: bool) -> Any:
    """把半开日期间隔落到查询上（区分 DateField / DateTimeField 的时区语义）。"""
    if is_datetime:
        # 本地日期 → aware datetime（服务器在 Asia/Shanghai，边界必须 aware）
        start_dt = timezone.make_aware(_dt.datetime.combine(start, _dt.time.min))
        end_dt = timezone.make_aware(_dt.datetime.combine(end, _dt.time.min))
        return queryset.filter(**{f"{field_name}__gte": start_dt, f"{field_name}__lt": end_dt})
    return queryset.filter(**{f"{field_name}__gte": start, f"{field_name}__lt": end})


class NaturalPeriodFilter(admin.SimpleListFilter):
    """按自然期间筛日期列（本月 / 上月 / 本季度 / 上季度 …）。

    通过 `date_filter()` 与 `NaturalPeriodFilter.create()` 传入字段名；
    直接挂在 `list_filter` 里时，`parameter_name` 由字段名派生，避免同页多个
    期间筛选器互相覆盖 URL 参数。
    """

    title = "时间范围"

    #: 被筛的日期列名（`create()` 注入）
    field_name: ClassVar[str] = ""
    #: 该列是否为 DateTimeField（决定时区处理）
    is_datetime: ClassVar[bool] = False

    @classmethod
    def create(cls, field_name: str, *, title: str | None = None) -> type[NaturalPeriodFilter]:
        """生成绑定到具体字段的筛选器类。

        用**闭包派生类**而不是工厂实例：Django 的 `list_filter` 要的是类（它自己
        实例化并把 request/params 传进来）。
        """

        class _Bound(NaturalPeriodFilter):
            pass

        _Bound.field_name = field_name
        _Bound.parameter_name = f"period_{field_name}"
        if title:
            _Bound.title = title
        return _Bound

    def lookups(self, request: Any, model_admin: Any) -> list[tuple[str, str]]:
        return list(PERIOD_LOOKUPS)

    def queryset(self, request: Any, queryset: Any) -> Any:
        period = self.value()
        if not period:
            return queryset

        field_name = self.field_name
        if not field_name:
            # 走到这里说明直接挂了基类而没经过 create()：Django 已在 __init__
            # 检查 parameter_name，这里两层都空只能是配置错。
            # 不静默降级为「不筛选」——那样筛选器会一直显示但永远不生效。
            raise ValueError(
                f"{type(self).__name__} 未绑定字段：请用 date_filter('字段名') 生成，不要直接把它挂进 list_filter。"
            )

        # 未显式声明时从模型推断（`create()` 之外直接挂类的场景）
        try:
            field = queryset.model._meta.get_field(field_name)
        except Exception:
            # 字段名写错：不筛选也不抛——admin 页面不能因为一个过滤器崩掉
            return queryset

        is_datetime = isinstance(field, models.DateTimeField)
        rng = period_range(period)
        if rng is None:
            return queryset
        start, end = rng
        return _apply(queryset, field_name, start, end, is_datetime=is_datetime)


def date_filter(field_name: str, *, title: str | None = None) -> type[NaturalPeriodFilter]:
    """`list_filter` 里按字段生成自然期间筛选器（推荐写法）。

    ```python
    list_filter = ["status", date_filter("created_at", title="创建时间")]
    ```
    """
    return NaturalPeriodFilter.create(field_name, title=title)
