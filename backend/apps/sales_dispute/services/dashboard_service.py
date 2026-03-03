"""回款统计看板服务"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Max, Q, Sum
from django.db.models.functions import TruncMonth, TruncQuarter, TruncYear
from django.utils.translation import gettext as _

from apps.sales_dispute.models.case_assessment import ContractBasisType
from apps.sales_dispute.models.collection_record import STAGE_ORDER, CollectionStage

logger = logging.getLogger(__name__)

_ZERO = Decimal("0.00")


# ── 输出 dataclass ──


@dataclass(frozen=True)
class SummaryOutput:
    """核心指标输出"""

    total_recovery: Decimal
    recovery_rate: Decimal
    avg_recovery_cycle: int
    recovered_case_count: int
    unrecovered_case_count: int
    query_start: date
    query_end: date


@dataclass(frozen=True)
class TrendItem:
    """趋势分组项"""

    label: str
    amount: Decimal
    count: int
    recovery_rate: Decimal


@dataclass(frozen=True)
class BreakdownItem:
    """分组统计项"""

    group_label: str
    total_recovery: Decimal
    case_count: int
    recovery_rate: Decimal


@dataclass(frozen=True)
class FactorItem:
    """影响因素分析项"""

    group_label: str
    case_count: int
    total_recovery: Decimal
    recovery_rate: Decimal


@dataclass(frozen=True)
class LawyerPerformanceItem:
    """律师绩效项"""

    lawyer_id: int
    lawyer_name: str
    case_count: int
    total_recovery: Decimal
    recovery_rate: Decimal
    avg_recovery_cycle: int
    closed_rate: Decimal


@dataclass(frozen=True)
class CaseStatsOutput:
    """案件统计输出"""

    total_cases: int
    active_cases: int
    closed_cases: int
    stage_distribution: list[BreakdownItem]
    amount_distribution: list[BreakdownItem]
    stage_conversion_rates: list[FactorItem]
    query_start: date
    query_end: date


# ── 常量 ──

AMOUNT_RANGES: list[tuple[str, Decimal | None, Decimal | None]] = [
    (_("10万以下"), None, Decimal("100000")),
    (_("10万-50万"), Decimal("100000"), Decimal("500000")),
    (_("50万-100万"), Decimal("500000"), Decimal("1000000")),
    (_("100万以上"), Decimal("1000000"), None),
]

DEBT_AGE_RANGES: list[tuple[str, int | None, int | None]] = [
    (_("1年内"), None, 365),
    (_("1-2年"), 365, 730),
    (_("2年以上"), 730, None),
]


def _safe_rate(numerator: Decimal, denominator: Decimal) -> Decimal:
    """除零保护的百分比计算"""
    if denominator == 0:
        return _ZERO
    return (numerator / denominator * 100).quantize(Decimal("0.01"))


def _amount_range_q(
    field: str,
    low: Decimal | None,
    high: Decimal | None,
) -> Q:
    """构建金额区间 Q 对象"""
    q = Q()
    if low is not None:
        q &= Q(**{f"{field}__gte": low})
    if high is not None:
        q &= Q(**{f"{field}__lt": high})
    return q


class DashboardService:
    """回款统计看板服务"""

    def get_summary(
        self,
        start_date: date,
        end_date: date,
    ) -> SummaryOutput:
        """核心指标统计（Req 1）"""
        from apps.cases.models.case import Case
        from apps.sales_dispute.models.payment_record import PaymentRecord

        logger.info("get_summary: %s ~ %s", start_date, end_date)

        cases = Case.objects.filter(start_date__range=(start_date, end_date))

        total_target: Decimal = (
            cases.filter(target_amount__isnull=False).aggregate(s=Sum("target_amount"))["s"] or _ZERO
        )

        payments = PaymentRecord.objects.filter(
            payment_date__range=(start_date, end_date),
        )
        total_recovery: Decimal = payments.aggregate(s=Sum("payment_amount"))["s"] or _ZERO

        recovery_rate = _safe_rate(total_recovery, total_target)

        # 回款周期：有回款记录的案件

        case_with_payment = (
            cases.filter(dispute_payments__isnull=False)
            .annotate(last_payment=Max("dispute_payments__payment_date"))
            .values_list("start_date", "last_payment")
        )
        cycles: list[int] = []
        for c_start, last_pay in case_with_payment:
            if last_pay is not None:
                cycles.append((last_pay - c_start).days)

        avg_cycle = sum(cycles) // len(cycles) if cycles else 0

        recovered_ids = set(payments.values_list("case_id", flat=True).distinct())
        total_case_ids = set(cases.values_list("id", flat=True))
        recovered_count = len(total_case_ids & recovered_ids)
        unrecovered_count = len(total_case_ids) - recovered_count

        return SummaryOutput(
            total_recovery=total_recovery,
            recovery_rate=recovery_rate,
            avg_recovery_cycle=avg_cycle,
            recovered_case_count=recovered_count,
            unrecovered_case_count=unrecovered_count,
            query_start=start_date,
            query_end=end_date,
        )

    def get_trend(
        self,
        start_date: date,
        end_date: date,
        dimension: str,
    ) -> list[TrendItem]:
        """回款趋势统计（Req 2）"""
        from apps.cases.models.case import Case
        from apps.sales_dispute.models.payment_record import PaymentRecord

        logger.info("get_trend: %s ~ %s, dim=%s", start_date, end_date, dimension)

        trunc_map = {
            "month": TruncMonth,
            "quarter": TruncQuarter,
            "year": TruncYear,
        }
        trunc_fn = trunc_map[dimension]

        payments = PaymentRecord.objects.filter(
            payment_date__range=(start_date, end_date),
        )
        grouped = (
            payments.annotate(period=trunc_fn("payment_date"))
            .values("period")
            .annotate(
                amount=Sum("payment_amount"),
                count=Count("id"),
            )
            .order_by("period")
        )

        total_target: Decimal = (
            Case.objects.filter(
                start_date__range=(start_date, end_date),
                target_amount__isnull=False,
            ).aggregate(s=Sum("target_amount"))["s"]
            or _ZERO
        )

        items: list[TrendItem] = []
        for row in grouped:
            period_date: date = row["period"]
            amt: Decimal = row["amount"] or _ZERO
            cnt: int = row["count"]
            if dimension == "month":
                label = period_date.strftime("%Y-%m")
            elif dimension == "quarter":
                q = (period_date.month - 1) // 3 + 1
                label = f"{period_date.year}-Q{q}"
            else:
                label = str(period_date.year)
            items.append(
                TrendItem(
                    label=label,
                    amount=amt,
                    count=cnt,
                    recovery_rate=_safe_rate(amt, total_target),
                )
            )
        return items

    def get_breakdown(
        self,
        start_date: date,
        end_date: date,
        group_by: str,
    ) -> list[BreakdownItem]:
        """多维度分组统计（Req 3）"""
        from apps.cases.models.case import Case
        from apps.sales_dispute.models.payment_record import PaymentRecord

        logger.info("get_breakdown: %s ~ %s, group=%s", start_date, end_date, group_by)

        cases = Case.objects.filter(start_date__range=(start_date, end_date))

        if group_by == "case_type":
            groups = cases.values("case_type").annotate(case_count=Count("id")).order_by("case_type")
            items: list[BreakdownItem] = []
            for g in groups:
                ct: str | None = g["case_type"]
                label = ct or _("未分类")
                case_ids = list(cases.filter(case_type=ct).values_list("id", flat=True))
                recovery: Decimal = (
                    PaymentRecord.objects.filter(
                        case_id__in=case_ids,
                        payment_date__range=(start_date, end_date),
                    ).aggregate(s=Sum("payment_amount"))["s"]
                    or _ZERO
                )
                target: Decimal = (
                    cases.filter(case_type=ct, target_amount__isnull=False).aggregate(s=Sum("target_amount"))["s"]
                    or _ZERO
                )
                items.append(
                    BreakdownItem(
                        group_label=label,
                        total_recovery=recovery,
                        case_count=g["case_count"],
                        recovery_rate=_safe_rate(recovery, target),
                    )
                )
            return items

        elif group_by == "amount_range":
            items = []
            for label, low, high in AMOUNT_RANGES:
                q = _amount_range_q("target_amount", low, high)
                filtered = cases.filter(q)
                cnt = filtered.count()
                case_ids = list(filtered.values_list("id", flat=True))
                recovery = (
                    PaymentRecord.objects.filter(
                        case_id__in=case_ids,
                        payment_date__range=(start_date, end_date),
                    ).aggregate(s=Sum("payment_amount"))["s"]
                    or _ZERO
                )
                target = filtered.filter(target_amount__isnull=False).aggregate(s=Sum("target_amount"))["s"] or _ZERO
                items.append(
                    BreakdownItem(
                        group_label=label,
                        total_recovery=recovery,
                        case_count=cnt,
                        recovery_rate=_safe_rate(recovery, target),
                    )
                )
            return items

        else:  # lawyer
            from apps.cases.models.party import CaseAssignment

            assignments = CaseAssignment.objects.filter(
                case__in=cases,
            ).select_related("lawyer")
            lawyer_map: dict[int, tuple[str, list[int]]] = {}
            for a in assignments:
                lid: int = a.lawyer_id
                if lid not in lawyer_map:
                    lawyer_map[lid] = (
                        a.lawyer.real_name or a.lawyer.username,
                        [],
                    )
                lawyer_map[lid][1].append(a.case_id)

            items = []
            for lid, (name, case_ids) in lawyer_map.items():
                recovery = (
                    PaymentRecord.objects.filter(
                        case_id__in=case_ids,
                        payment_date__range=(start_date, end_date),
                    ).aggregate(s=Sum("payment_amount"))["s"]
                    or _ZERO
                )
                target = (
                    cases.filter(id__in=case_ids, target_amount__isnull=False).aggregate(s=Sum("target_amount"))["s"]
                    or _ZERO
                )
                items.append(
                    BreakdownItem(
                        group_label=name,
                        total_recovery=recovery,
                        case_count=len(case_ids),
                        recovery_rate=_safe_rate(recovery, target),
                    )
                )
            return items

    def get_factors(
        self,
        start_date: date,
        end_date: date,
    ) -> dict[str, list[FactorItem]]:
        """回款影响因素分析（Req 4）"""
        from apps.cases.models.case import Case
        from apps.sales_dispute.models.case_assessment import CaseAssessment
        from apps.sales_dispute.models.payment_record import PaymentRecord

        logger.info("get_factors: %s ~ %s", start_date, end_date)

        cases = Case.objects.filter(start_date__range=(start_date, end_date))
        today = date.today()

        # ── 欠款时间区间 ──
        debt_age_items: list[FactorItem] = []
        for label, low, high in DEBT_AGE_RANGES:
            q = Q()
            if low is not None:
                cutoff_high = today - timedelta(days=low)
                q &= Q(start_date__lte=cutoff_high)
            if high is not None:
                cutoff_low = today - timedelta(days=high)
                q &= Q(start_date__gt=cutoff_low)
            filtered = cases.filter(q)
            cnt = filtered.count()
            case_ids = list(filtered.values_list("id", flat=True))
            recovery: Decimal = (
                PaymentRecord.objects.filter(
                    case_id__in=case_ids,
                    payment_date__range=(start_date, end_date),
                ).aggregate(s=Sum("payment_amount"))["s"]
                or _ZERO
            )
            target: Decimal = (
                filtered.filter(target_amount__isnull=False).aggregate(s=Sum("target_amount"))["s"] or _ZERO
            )
            debt_age_items.append(
                FactorItem(
                    group_label=label,
                    case_count=cnt,
                    total_recovery=recovery,
                    recovery_rate=_safe_rate(recovery, target),
                )
            )

        # ── 合同基础类型 ──
        contract_items: list[FactorItem] = []
        for cb in ContractBasisType:
            assessed_case_ids = list(
                CaseAssessment.objects.filter(
                    contract_basis=cb.value,
                    case__in=cases,
                ).values_list("case_id", flat=True)
            )
            cnt = len(assessed_case_ids)
            recovery = (
                PaymentRecord.objects.filter(
                    case_id__in=assessed_case_ids,
                    payment_date__range=(start_date, end_date),
                ).aggregate(s=Sum("payment_amount"))["s"]
                or _ZERO
            )
            target = (
                cases.filter(id__in=assessed_case_ids, target_amount__isnull=False).aggregate(s=Sum("target_amount"))[
                    "s"
                ]
                or _ZERO
            )
            contract_items.append(
                FactorItem(
                    group_label=str(cb.label),
                    case_count=cnt,
                    total_recovery=recovery,
                    recovery_rate=_safe_rate(recovery, target),
                )
            )

        # ── 财产保全 ──
        preservation_items: list[FactorItem] = []
        for label, q_filter in [
            (_("有财产保全"), Q(preservation_amount__isnull=False) & ~Q(preservation_amount=0)),
            (_("无财产保全"), Q(preservation_amount__isnull=True) | Q(preservation_amount=0)),
        ]:
            filtered = cases.filter(q_filter)
            cnt = filtered.count()
            case_ids = list(filtered.values_list("id", flat=True))
            recovery = (
                PaymentRecord.objects.filter(
                    case_id__in=case_ids,
                    payment_date__range=(start_date, end_date),
                ).aggregate(s=Sum("payment_amount"))["s"]
                or _ZERO
            )
            target = filtered.filter(target_amount__isnull=False).aggregate(s=Sum("target_amount"))["s"] or _ZERO
            preservation_items.append(
                FactorItem(
                    group_label=label,
                    case_count=cnt,
                    total_recovery=recovery,
                    recovery_rate=_safe_rate(recovery, target),
                )
            )

        # ── 标的额区间 ──
        amount_items: list[FactorItem] = []
        for label, low, high in AMOUNT_RANGES:
            q = _amount_range_q("target_amount", low, high)
            filtered = cases.filter(q)
            cnt = filtered.count()
            case_ids = list(filtered.values_list("id", flat=True))
            recovery = (
                PaymentRecord.objects.filter(
                    case_id__in=case_ids,
                    payment_date__range=(start_date, end_date),
                ).aggregate(s=Sum("payment_amount"))["s"]
                or _ZERO
            )
            target = filtered.filter(target_amount__isnull=False).aggregate(s=Sum("target_amount"))["s"] or _ZERO
            amount_items.append(
                FactorItem(
                    group_label=label,
                    case_count=cnt,
                    total_recovery=recovery,
                    recovery_rate=_safe_rate(recovery, target),
                )
            )

        return {
            "debt_age": debt_age_items,
            "contract_basis": contract_items,
            "preservation": preservation_items,
            "amount_range": amount_items,
        }

    def get_lawyer_performance(
        self,
        start_date: date,
        end_date: date,
        sort_by: str,
    ) -> list[LawyerPerformanceItem]:
        """律师绩效分析（Req 5）"""
        from apps.cases.models.case import Case
        from apps.cases.models.party import CaseAssignment
        from apps.sales_dispute.models.payment_record import PaymentRecord

        logger.info("get_lawyer_performance: %s ~ %s, sort=%s", start_date, end_date, sort_by)

        cases = Case.objects.filter(start_date__range=(start_date, end_date))
        assignments = CaseAssignment.objects.filter(
            case__in=cases,
        ).select_related("lawyer")

        lawyer_cases: dict[int, tuple[str, list[int]]] = {}
        for a in assignments:
            lid: int = a.lawyer_id
            if lid not in lawyer_cases:
                lawyer_cases[lid] = (
                    a.lawyer.real_name or a.lawyer.username,
                    [],
                )
            lawyer_cases[lid][1].append(a.case_id)

        items: list[LawyerPerformanceItem] = []
        for lid, (name, case_ids) in lawyer_cases.items():
            case_count = len(case_ids)
            recovery: Decimal = (
                PaymentRecord.objects.filter(
                    case_id__in=case_ids,
                    payment_date__range=(start_date, end_date),
                ).aggregate(s=Sum("payment_amount"))["s"]
                or _ZERO
            )
            target: Decimal = (
                cases.filter(id__in=case_ids, target_amount__isnull=False).aggregate(s=Sum("target_amount"))["s"]
                or _ZERO
            )
            closed = cases.filter(id__in=case_ids, status="closed").count()
            closed_rate = _safe_rate(Decimal(closed), Decimal(case_count))

            # 回款周期
            case_with_pay = (
                cases.filter(id__in=case_ids, dispute_payments__isnull=False)
                .annotate(last_payment=Max("dispute_payments__payment_date"))
                .values_list("start_date", "last_payment")
            )
            cycles: list[int] = []
            for c_start, last_pay in case_with_pay:
                if last_pay is not None:
                    cycles.append((last_pay - c_start).days)
            avg_cycle = sum(cycles) // len(cycles) if cycles else 0

            items.append(
                LawyerPerformanceItem(
                    lawyer_id=lid,
                    lawyer_name=name,
                    case_count=case_count,
                    total_recovery=recovery,
                    recovery_rate=_safe_rate(recovery, target),
                    avg_recovery_cycle=avg_cycle,
                    closed_rate=closed_rate,
                )
            )

        sort_key_map: dict[str, str] = {
            "total_recovery": "total_recovery",
            "recovery_rate": "recovery_rate",
            "case_count": "case_count",
        }
        key = sort_key_map[sort_by]
        items.sort(key=lambda x: getattr(x, key), reverse=True)
        return items

    def get_case_stats(
        self,
        start_date: date,
        end_date: date,
    ) -> CaseStatsOutput:
        """案件数据统计（Req 6）"""
        from apps.cases.models.case import Case
        from apps.sales_dispute.models.collection_record import CollectionRecord

        logger.info("get_case_stats: %s ~ %s", start_date, end_date)

        cases = Case.objects.filter(start_date__range=(start_date, end_date))
        total = cases.count()
        active = cases.filter(status="active").count()
        closed = cases.filter(status="closed").count()

        # ── 催收阶段分布 ──
        stage_items: list[BreakdownItem] = []
        for stage in CollectionStage:
            cnt = CollectionRecord.objects.filter(
                case__in=cases,
                current_stage=stage.value,
            ).count()
            stage_items.append(
                BreakdownItem(
                    group_label=str(stage.label),
                    total_recovery=_ZERO,
                    case_count=cnt,
                    recovery_rate=_ZERO,
                )
            )

        # ── 标的额分布 ──
        amount_items: list[BreakdownItem] = []
        for label, low, high in AMOUNT_RANGES:
            q = _amount_range_q("target_amount", low, high)
            cnt = cases.filter(q).count()
            amount_items.append(
                BreakdownItem(
                    group_label=label,
                    total_recovery=_ZERO,
                    case_count=cnt,
                    recovery_rate=_ZERO,
                )
            )

        # ── 催收阶段转化率 ──
        conversion_items: list[FactorItem] = []
        stage_counts: list[int] = []
        for stage in CollectionStage:
            cnt = CollectionRecord.objects.filter(
                case__in=cases,
                current_stage=stage.value,
            ).count()
            stage_counts.append(cnt)

        # 转化率：累计到达该阶段及之后的案件数 / 累计到达上一阶段及之后的案件数
        # 用反向累加：到达某阶段 = 该阶段 + 后续所有阶段
        cumulative: list[int] = [0] * len(stage_counts)
        running = 0
        for i in range(len(stage_counts) - 1, -1, -1):
            running += stage_counts[i]
            cumulative[i] = running

        for i in range(len(STAGE_ORDER) - 1):
            current_cum = cumulative[i]
            next_cum = cumulative[i + 1]
            rate = _safe_rate(Decimal(next_cum), Decimal(current_cum))
            stage_label = str(CollectionStage(STAGE_ORDER[i]).label)
            conversion_items.append(
                FactorItem(
                    group_label=stage_label,
                    case_count=current_cum,
                    total_recovery=_ZERO,
                    recovery_rate=rate,
                )
            )

        return CaseStatsOutput(
            total_cases=total,
            active_cases=active,
            closed_cases=closed,
            stage_distribution=stage_items,
            amount_distribution=amount_items,
            stage_conversion_rates=conversion_items,
            query_start=start_date,
            query_end=end_date,
        )
