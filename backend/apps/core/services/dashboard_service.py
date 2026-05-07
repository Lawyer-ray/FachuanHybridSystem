"""仪表盘聚合统计 Service"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.cases.models import Case
from apps.contracts.models import Contract, ContractPayment
from apps.core.models.enums import CaseStage, CaseStatus, SimpleCaseType
from apps.reminders.models import Reminder


class DashboardService:
    """提供仪表盘所需的聚合统计数据。"""

    def get_stats(self) -> dict[str, Any]:
        """返回完整的仪表盘统计数据。"""
        today = timezone.localdate()
        now = timezone.now()
        month_start = today.replace(day=1)

        return {
            # 总量
            "client_count": self._client_count(),
            "contract_count": self._contract_count(),
            "case_count": self._active_case_count(),
            "monthly_fee": self._monthly_fee(month_start, today),
            # 趋势
            "case_trend": self._case_trend(),
            "contract_trend": self._contract_trend(),
            "fee_trend": self._fee_trend(),
            # 分布
            "case_type_distribution": self._case_type_distribution(),
            "case_status_distribution": self._case_status_distribution(),
            # 提醒
            "upcoming_reminders": self._upcoming_reminders(now),
            "overdue_count": self._overdue_count(now),
            "today_count": self._today_count(now),
        }

    # ── 总量 ───────────────────────────────────────────────────────────────────

    @staticmethod
    def _client_count() -> int:
        from apps.client.models import Client

        return Client.objects.count()

    @staticmethod
    def _contract_count() -> int:
        return Contract.objects.count()

    @staticmethod
    def _active_case_count() -> int:
        return Case.objects.filter(status=CaseStatus.ACTIVE).count()

    @staticmethod
    def _monthly_fee(month_start: date, today: date) -> Decimal:
        result = ContractPayment.objects.filter(
            received_at__gte=month_start,
            received_at__lte=today,
        ).aggregate(total=Sum("amount"))
        return result["total"] or Decimal("0")

    # ── 趋势（近 12 个月）─────────────────────────────────────────────────────

    @staticmethod
    def _case_trend() -> list[dict[str, Any]]:
        start = timezone.localdate() - timedelta(days=365)
        qs = (
            Case.objects.filter(start_date__gte=start)
            .annotate(month=TruncMonth("start_date"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )
        return [{"month": r["month"].strftime("%Y-%m"), "count": r["count"]} for r in qs]

    @staticmethod
    def _contract_trend() -> list[dict[str, Any]]:
        start = timezone.localdate() - timedelta(days=365)
        qs = (
            Contract.objects.filter(specified_date__gte=start)
            .annotate(month=TruncMonth("specified_date"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )
        return [{"month": r["month"].strftime("%Y-%m"), "count": r["count"]} for r in qs]

    @staticmethod
    def _fee_trend() -> list[dict[str, Any]]:
        start = timezone.localdate() - timedelta(days=365)
        qs = (
            ContractPayment.objects.filter(received_at__gte=start)
            .annotate(month=TruncMonth("received_at"))
            .values("month")
            .annotate(amount=Sum("amount"))
            .order_by("month")
        )
        return [{"month": r["month"].strftime("%Y-%m"), "amount": str(r["amount"] or 0)} for r in qs]

    # ── 分布 ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _case_type_distribution() -> list[dict[str, Any]]:
        label_map = {k: str(v) for k, v in SimpleCaseType.choices}
        qs = (
            Case.objects.filter(status=CaseStatus.ACTIVE)
            .values("case_type")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        return [
            {
                "type": r["case_type"] or "unknown",
                "label": label_map.get(r["case_type"], "未分类"),
                "count": r["count"],
            }
            for r in qs
        ]

    @staticmethod
    def _case_status_distribution() -> dict[str, int]:
        qs = Case.objects.values("status").annotate(count=Count("id"))
        return {r["status"]: r["count"] for r in qs}

    # ── 提醒 ──────────────────────────────────────────────────────────────────

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

    @staticmethod
    def _overdue_count(now: datetime) -> int:
        return Reminder.objects.filter(due_at__lt=now).count()

    @staticmethod
    def _today_count(now: datetime) -> int:
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        return Reminder.objects.filter(due_at__gte=today_start, due_at__lt=today_end).count()
