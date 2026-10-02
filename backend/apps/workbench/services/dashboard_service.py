"""仪表盘聚合统计 Service"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.cases.models import Case
from apps.contracts.models import Contract, ContractPayment
from apps.core.models.enums import CaseStatus, SimpleCaseType
from apps.reminders.models import Reminder


class DashboardService:
    """提供仪表盘所需的聚合统计数据。"""

    def get_stats(self) -> dict[str, Any]:
        """返回完整的仪表盘统计数据。"""
        today = timezone.localdate()
        now = timezone.now()
        month_start = today.replace(day=1)
        trend_start = today - timedelta(days=365)

        # 1 query: Case 活跃数 + 案件类型分布（同表、同 filter）
        case_type_dist, active_case_count = self._case_type_stats()

        # 1 query: Case 趋势（按月）
        case_trend = self._case_trend(trend_start)

        # 1 query: Case 状态分布（全部状态）
        case_status_dist = self._case_status_distribution()

        # 1 query: ContractPayment 费用（本月 + 近 12 月趋势）
        monthly_fee, fee_trend = self._fee_stats(month_start, today, trend_start)

        # 1 query: Reminder 计数（overdue + today）
        reminder_counts = self._reminder_counts(now)

        # 1 query: Reminder 到期列表（需要实际对象数据，无法合并）
        upcoming_reminders = self._upcoming_reminders(now)

        return {
            # 总量
            "client_count": self._client_count(),
            "contract_count": self._contract_count(),
            "case_count": active_case_count,
            "monthly_fee": monthly_fee,
            # 趋势
            "case_trend": case_trend,
            "contract_trend": self._contract_trend(trend_start),
            "fee_trend": fee_trend,
            # 分布
            "case_type_distribution": case_type_dist,
            "case_status_distribution": case_status_dist,
            # 提醒
            "upcoming_reminders": upcoming_reminders,
            "overdue_count": reminder_counts["overdue_count"],
            "today_count": reminder_counts["today_count"],
        }

    # ── 总量（独立小查询，无法合并）────────────────────────────────────────────

    @staticmethod
    def _client_count() -> int:
        from apps.client.models import Client

        return Client.objects.count()

    @staticmethod
    def _contract_count() -> int:
        return Contract.objects.count()

    # ── Case: 活跃数 + 类型分布（合并为 1 条查询）─────────────────────────────

    @staticmethod
    def _case_type_stats() -> tuple[list[dict[str, Any]], int]:
        """一次查询同时返回活跃案件类型分布和活跃案件总数。"""
        label_map = {k: str(v) for k, v in SimpleCaseType.choices}
        qs = (
            Case.objects.filter(status=CaseStatus.ACTIVE)
            .values("case_type")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        distribution = []
        total = 0
        for r in qs:
            count = r["count"]
            total += count
            distribution.append(
                {
                    "type": r["case_type"] or "unknown",
                    "label": label_map.get(r["case_type"] or "", "未分类"),
                    "count": count,
                }
            )
        return distribution, total

    # ── Case 趋势（近 12 个月）────────────────────────────────────────────────

    @staticmethod
    def _case_trend(start: date) -> list[dict[str, Any]]:
        qs = (
            Case.objects.filter(start_date__gte=start)
            .annotate(month=TruncMonth("start_date"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )
        return [{"month": r["month"].strftime("%Y-%m"), "count": r["count"]} for r in qs]

    # ── Case 状态分布 ─────────────────────────────────────────────────────────

    @staticmethod
    def _case_status_distribution() -> dict[str, int]:
        qs = Case.objects.values("status").annotate(count=Count("id"))
        return {r["status"]: r["count"] for r in qs}

    # ── Contract 趋势（近 12 个月）────────────────────────────────────────────

    @staticmethod
    def _contract_trend(start: date) -> list[dict[str, Any]]:
        qs = (
            Contract.objects.filter(specified_date__gte=start)
            .annotate(month=TruncMonth("specified_date"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )
        return [{"month": r["month"].strftime("%Y-%m"), "count": r["count"]} for r in qs]

    # ── ContractPayment: 本月费用 + 费用趋势（合并为 1 条查询）────────────────

    @staticmethod
    def _fee_stats(month_start: date, today: date, trend_start: date) -> tuple[Decimal, list[dict[str, Any]]]:
        """一次查询从 trend_start 到 today 的所有支付记录，
        同时计算本月费用和近 12 月趋势。"""
        qs = ContractPayment.objects.filter(received_at__gte=trend_start, received_at__lte=today)
        # 本月费用
        monthly_result = qs.filter(
            received_at__gte=month_start,
        ).aggregate(total=Sum("amount"))
        monthly_fee: Decimal = monthly_result["total"] or Decimal("0")

        # 近 12 月趋势
        trend_qs = (
            qs.annotate(month=TruncMonth("received_at"))
            .values("month")
            .annotate(amount=Sum("amount"))
            .order_by("month")
        )
        fee_trend = [{"month": r["month"].strftime("%Y-%m"), "amount": str(r["amount"] or 0)} for r in trend_qs]
        return monthly_fee, fee_trend

    # ── Reminder: overdue + today 计数（合并为 1 条查询）──────────────────────

    @staticmethod
    def _reminder_counts(now: datetime) -> dict[str, int]:
        """一次条件聚合查询同时获取 overdue 和 today 的提醒数量。"""
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        return Reminder.objects.filter(Q(due_at__lt=now) | Q(due_at__gte=today_start, due_at__lt=today_end)).aggregate(
            overdue_count=Count("id", filter=Q(due_at__lt=now)),
            today_count=Count("id", filter=Q(due_at__gte=today_start, due_at__lt=today_end)),
        )

    # ── Reminder 到期列表（需要实际对象数据）─────────────────────────────────

    @staticmethod
    def _upcoming_reminders(now: datetime) -> list[dict[str, Any]]:
        from apps.reminders.models import ReminderType

        type_label_map = {k: str(v) for k, v in ReminderType.choices}
        week_later = now + timedelta(days=7)
        qs = Reminder.objects.filter(due_at__lte=week_later).order_by("due_at")[:20]
        result = []
        for r in qs:
            result.append(
                {
                    "id": r.id,
                    "title": r.content,
                    "due_at": r.due_at.isoformat(),
                    "type_label": type_label_map.get(r.reminder_type, ""),
                    "is_overdue": r.due_at < now,
                }
            )
        return result
