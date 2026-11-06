"""证件到期状态判定（纯读，不写库）。

设计原则：到期提醒必须**读时计算**，不做定时扫库——
证件到期日是证件的固有属性，一年最多变一次；每天扫库既浪费算力，
又可能在识别抽风时写入错误日期，制造假告警（提醒类功能最典型的死法）。

状态口径：
- ``expired``  已过期
- ``expiring`` 临期（默认 30 天内到期）
- ``missing``  无证件文件/无到期日（**重点**：不标出来就是假绿灯）
- ``ok``       正常
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# 默认临期阈值（天）
DEFAULT_EXPIRING_DAYS = 30

STATUS_EXPIRED = "expired"
STATUS_EXPIRING = "expiring"
STATUS_MISSING = "missing"
STATUS_OK = "ok"

# 「长期有效」在识别链路里被归一成 2099-12-31，视为无到期压力
_LONG_TERM_CUTOFF = date(2090, 1, 1)


@dataclass(frozen=True)
class ExpiryStatus:
    """单个证件的到期状态。"""

    status: str
    expiry_date: date | None = None
    days_left: int | None = None

    @property
    def needs_attention(self) -> bool:
        return self.status in (STATUS_EXPIRED, STATUS_EXPIRING, STATUS_MISSING)


def evaluate_expiry(
    expiry_date: date | None,
    today: date,
    *,
    expiring_days: int = DEFAULT_EXPIRING_DAYS,
    has_file: bool = True,
) -> ExpiryStatus:
    """判定单个证件的到期状态。

    Args:
        expiry_date: 证件到期日；None 表示尚未识别或无此项。
        today: 参照日期（调用方传，便于测试）。
        expiring_days: 临期阈值天数。
        has_file: 是否有证件文件；没有文件时即使有日期也视为缺失（文件都没了无法核验）。
    """
    if not has_file:
        return ExpiryStatus(STATUS_MISSING, expiry_date, None)
    if expiry_date is None:
        return ExpiryStatus(STATUS_MISSING, None, None)
    if expiry_date >= _LONG_TERM_CUTOFF:
        return ExpiryStatus(STATUS_OK, expiry_date, None)

    days_left = (expiry_date - today).days
    if days_left < 0:
        return ExpiryStatus(STATUS_EXPIRED, expiry_date, days_left)
    if days_left <= expiring_days:
        return ExpiryStatus(STATUS_EXPIRING, expiry_date, days_left)
    return ExpiryStatus(STATUS_OK, expiry_date, days_left)


def aggregate_client_status(
    docs: list[tuple[date | None, bool]],
    today: date,
    *,
    expiring_days: int = DEFAULT_EXPIRING_DAYS,
) -> ExpiryStatus:
    """聚合一个当事人名下所有证件的状态，取最紧急的那个。

    Args:
        docs: [(expiry_date, has_file), ...]
    """
    if not docs:
        return ExpiryStatus(STATUS_MISSING, None, None)

    statuses = [evaluate_expiry(exp, today, expiring_days=expiring_days, has_file=has_file) for exp, has_file in docs]
    # 紧急度：已过期 > 临期 > 缺失 > 正常
    priority = {STATUS_EXPIRED: 0, STATUS_EXPIRING: 1, STATUS_MISSING: 2, STATUS_OK: 3}
    worst = min(statuses, key=lambda s: priority[s.status])
    # 临期时取剩余天数最小的那个，便于列表页显示紧迫度
    if worst.status == STATUS_EXPIRING:
        urgent = [s for s in statuses if s.status == STATUS_EXPIRING and s.days_left is not None]
        if urgent:
            worst = min(urgent, key=lambda s: s.days_left or 0)
    return worst


def witness_today() -> date:
    """当前本地日期（集中一处便于测试替换）。"""
    from django.utils import timezone

    return timezone.localdate()


def summarize_counts(statuses: list[ExpiryStatus]) -> dict[str, int]:
    """汇总各状态数量，供列表页页头提示。"""
    counts = {STATUS_EXPIRED: 0, STATUS_EXPIRING: 0, STATUS_MISSING: 0, STATUS_OK: 0}
    for s in statuses:
        counts[s.status] = counts.get(s.status, 0) + 1
    return counts


__all__ = [
    "DEFAULT_EXPIRING_DAYS",
    "STATUS_EXPIRED",
    "STATUS_EXPIRING",
    "STATUS_MISSING",
    "STATUS_OK",
    "ExpiryStatus",
    "aggregate_client_status",
    "evaluate_expiry",
    "summarize_counts",
    "witness_today",
]
