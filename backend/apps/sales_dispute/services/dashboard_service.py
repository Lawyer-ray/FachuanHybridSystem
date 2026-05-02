"""回款统计看板服务"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Case as DBCase
from django.db.models import CharField, Count, Max, OuterRef, Q, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce, TruncMonth, TruncQuarter, TruncYear
from django.utils.translation import gettext as _

from apps.sales_dispute.models.case_assessment import ContractBasisType
from apps.sales_dispute.models.collection_record import STAGE_ORDER, CollectionStage

from .dashboard_models import (
    AMOUNT_RANGES,
    DEBT_AGE_RANGES,
    _ZERO,
    BreakdownItem,
    CaseStatsOutput,
    FactorItem,
    LawyerPerformanceItem,
    SummaryOutput,
    TrendItem,
    _amount_range_q,
    _get_case_assignment_model,
    _get_case_model,
    _lawyer_display_name,
    _safe_rate,
)

logger = logging.getLogger(__name__)


class DashboardService:
    """回款统计看板服务"""

    def get_summary(
        self,
        start_date: date,
        end_date: date,
    ) -> SummaryOutput:
        """核心指标统计（Req 1）"""
        from apps.sales_dispute.models.payment_record import PaymentRecord

        logger.info("get_summary: %s ~ %s", start_date, end_date)

        case_model = _get_case_model()
        cases = case_model.objects.filter(start_date__range=(start_date, end_date))

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

        case_model = _get_case_model()
        total_target: Decimal = (
            case_model.objects.filter(
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
        from apps.sales_dispute.models.payment_record import PaymentRecord

        logger.info("get_breakdown: %s ~ %s, group=%s", start_date, end_date, group_by)

        case_model = _get_case_model()
        cases = case_model.objects.filter(start_date__range=(start_date, end_date))

        payment_sub = (
            PaymentRecord.objects.filter(
                case_id=OuterRef("pk"),
                payment_date__range=(start_date, end_date),
            )
            .values("case_id")
            .annotate(total=Sum("payment_amount"))
            .values("total")[:1]
        )

        if group_by == "case_type":
            grouped = (
                cases.annotate(case_recovery=Coalesce(Subquery(payment_sub), _ZERO))
                .values("case_type")
                .annotate(
                    case_count=Count("id"),
                    total_recovery=Sum("case_recovery"),
                    total_target=Sum("target_amount", filter=Q(target_amount__isnull=False)),
                )
            )
            return [
                BreakdownItem(
                    group_label=g["case_type"] or _("未分类"),
                    total_recovery=g["total_recovery"] or _ZERO,
                    case_count=g["case_count"],
                    recovery_rate=_safe_rate(g["total_recovery"] or _ZERO, g["total_target"] or _ZERO),
                )
                for g in grouped
            ]

        elif group_by == "amount_range":
            bucket = DBCase(
                *[
                    When(**{"target_amount__lt": high, "then": Value(label)})
                    for label, _, high in AMOUNT_RANGES
                    if high is not None
                ],
                default=Value(AMOUNT_RANGES[-1][0]),
                output_field=CharField(),
            )
            grouped = (
                cases.annotate(
                    amount_bucket=bucket,
                    case_recovery=Coalesce(Subquery(payment_sub), _ZERO),
                )
                .values("amount_bucket")
                .annotate(
                    case_count=Count("id"),
                    total_recovery=Sum("case_recovery"),
                    total_target=Sum("target_amount", filter=Q(target_amount__isnull=False)),
                )
            )
            return [
                BreakdownItem(
                    group_label=g["amount_bucket"],
                    total_recovery=g["total_recovery"] or _ZERO,
                    case_count=g["case_count"],
                    recovery_rate=_safe_rate(g["total_recovery"] or _ZERO, g["total_target"] or _ZERO),
                )
                for g in grouped
            ]

        else:  # lawyer
            case_assignment_model = _get_case_assignment_model()
            grouped = (
                case_assignment_model.objects.filter(case__in=cases)
                .values("lawyer_id")
                .annotate(
                    case_count=Count("case_id", distinct=True),
                    total_recovery=Coalesce(
                        Sum(
                            "case__dispute_payments__payment_amount",
                            filter=Q(case__dispute_payments__payment_date__range=(start_date, end_date)),
                        ),
                        _ZERO,
                    ),
                    total_target=Sum(
                        "case__target_amount",
                        filter=Q(case__target_amount__isnull=False),
                    ),
                )
            )
            lawyer_ids = [g["lawyer_id"] for g in grouped]
            from apps.organization.models import Lawyer

            lawyers = {l.id: l for l in Lawyer.objects.filter(id__in=lawyer_ids)}
            return [
                BreakdownItem(
                    group_label=_lawyer_display_name(lawyers.get(g["lawyer_id"])),
                    total_recovery=g["total_recovery"] or _ZERO,
                    case_count=g["case_count"],
                    recovery_rate=_safe_rate(g["total_recovery"] or _ZERO, g["total_target"] or _ZERO),
                )
                for g in grouped
            ]

    def get_factors(
        self,
        start_date: date,
        end_date: date,
    ) -> dict[str, list[FactorItem]]:
        """回款影响因素分析（Req 4）"""
        from apps.sales_dispute.models.case_assessment import CaseAssessment
        from apps.sales_dispute.models.payment_record import PaymentRecord

        logger.info("get_factors: %s ~ %s", start_date, end_date)

        case_model = _get_case_model()
        cases = case_model.objects.filter(start_date__range=(start_date, end_date))
        today = date.today()

        payment_sub = (
            PaymentRecord.objects.filter(
                case_id=OuterRef("pk"),
                payment_date__range=(start_date, end_date),
            )
            .values("case_id")
            .annotate(total=Sum("payment_amount"))
            .values("total")[:1]
        )

        # ── 欠款时间区间 ──
        debt_age_bucket = DBCase(
            *[
                When(start_date__lte=today - timedelta(days=low), then=Value(label))
                for label, low, _ in DEBT_AGE_RANGES
                if low is not None
            ],
            default=Value(DEBT_AGE_RANGES[0][0]),
            output_field=CharField(),
        )
        debt_age_grouped = (
            cases.annotate(
                age_bucket=debt_age_bucket,
                case_recovery=Coalesce(Subquery(payment_sub), _ZERO),
            )
            .values("age_bucket")
            .annotate(
                case_count=Count("id"),
                total_recovery=Sum("case_recovery"),
                total_target=Sum("target_amount", filter=Q(target_amount__isnull=False)),
            )
        )
        debt_age_items = [
            FactorItem(
                group_label=g["age_bucket"],
                case_count=g["case_count"],
                total_recovery=g["total_recovery"] or _ZERO,
                recovery_rate=_safe_rate(g["total_recovery"] or _ZERO, g["total_target"] or _ZERO),
            )
            for g in debt_age_grouped
        ]

        # ── 合同基础类型 ──
        contract_grouped = (
            CaseAssessment.objects.filter(case__in=cases)
            .values("contract_basis")
            .annotate(
                case_count=Count("id"),
                total_recovery=Coalesce(
                    Sum(
                        "case__dispute_payments__payment_amount",
                        filter=Q(case__dispute_payments__payment_date__range=(start_date, end_date)),
                    ),
                    _ZERO,
                ),
                total_target=Sum(
                    "case__target_amount",
                    filter=Q(case__target_amount__isnull=False),
                ),
            )
        )
        cb_label_map = {cb.value: str(cb.label) for cb in ContractBasisType}
        contract_items = [
            FactorItem(
                group_label=cb_label_map.get(g["contract_basis"], g["contract_basis"]),
                case_count=g["case_count"],
                total_recovery=g["total_recovery"] or _ZERO,
                recovery_rate=_safe_rate(g["total_recovery"] or _ZERO, g["total_target"] or _ZERO),
            )
            for g in contract_grouped
        ]

        # ── 财产保全 ──
        preservation_bucket = DBCase(
            When(
                Q(preservation_amount__isnull=True) | Q(preservation_amount=0),
                then=Value(_("无财产保全")),
            ),
            default=Value(_("有财产保全")),
            output_field=CharField(),
        )
        preservation_grouped = (
            cases.annotate(
                pres_bucket=preservation_bucket,
                case_recovery=Coalesce(Subquery(payment_sub), _ZERO),
            )
            .values("pres_bucket")
            .annotate(
                case_count=Count("id"),
                total_recovery=Sum("case_recovery"),
                total_target=Sum("target_amount", filter=Q(target_amount__isnull=False)),
            )
        )
        preservation_items = [
            FactorItem(
                group_label=g["pres_bucket"],
                case_count=g["case_count"],
                total_recovery=g["total_recovery"] or _ZERO,
                recovery_rate=_safe_rate(g["total_recovery"] or _ZERO, g["total_target"] or _ZERO),
            )
            for g in preservation_grouped
        ]

        # ── 标的额区间 ──
        amount_bucket = DBCase(
            *[
                When(**{"target_amount__lt": high, "then": Value(label)})
                for label, _, high in AMOUNT_RANGES
                if high is not None
            ],
            default=Value(AMOUNT_RANGES[-1][0]),
            output_field=CharField(),
        )
        amount_grouped = (
            cases.annotate(
                amt_bucket=amount_bucket,
                case_recovery=Coalesce(Subquery(payment_sub), _ZERO),
            )
            .values("amt_bucket")
            .annotate(
                case_count=Count("id"),
                total_recovery=Sum("case_recovery"),
                total_target=Sum("target_amount", filter=Q(target_amount__isnull=False)),
            )
        )
        amount_items = [
            FactorItem(
                group_label=g["amt_bucket"],
                case_count=g["case_count"],
                total_recovery=g["total_recovery"] or _ZERO,
                recovery_rate=_safe_rate(g["total_recovery"] or _ZERO, g["total_target"] or _ZERO),
            )
            for g in amount_grouped
        ]

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
        from apps.organization.models import Lawyer
        from apps.sales_dispute.models.payment_record import PaymentRecord

        logger.info("get_lawyer_performance: %s ~ %s, sort=%s", start_date, end_date, sort_by)

        case_model = _get_case_model()
        case_assignment_model = _get_case_assignment_model()
        cases = case_model.objects.filter(start_date__range=(start_date, end_date))

        last_payment_sub = (
            PaymentRecord.objects.filter(case_id=OuterRef("pk")).order_by("-payment_date").values("payment_date")[:1]
        )

        grouped = (
            case_assignment_model.objects.filter(case__in=cases)
            .values("lawyer_id")
            .annotate(
                case_count=Count("case_id", distinct=True),
                total_recovery=Coalesce(
                    Sum(
                        "case__dispute_payments__payment_amount",
                        filter=Q(case__dispute_payments__payment_date__range=(start_date, end_date)),
                    ),
                    _ZERO,
                ),
                total_target=Sum(
                    "case__target_amount",
                    filter=Q(case__target_amount__isnull=False),
                ),
                closed_count=Count(
                    "case_id",
                    filter=Q(case__status="closed"),
                    distinct=True,
                ),
            )
        )

        lawyer_ids = [g["lawyer_id"] for g in grouped]
        lawyers = {l.id: l for l in Lawyer.objects.filter(id__in=lawyer_ids)}

        lawyer_case_map: dict[int, list[int]] = {}
        for a in case_assignment_model.objects.filter(case__in=cases).values_list("lawyer_id", "case_id"):
            lawyer_case_map.setdefault(a[0], []).append(a[1])

        items: list[LawyerPerformanceItem] = []
        for g in grouped:
            lid = g["lawyer_id"]
            case_count = g["case_count"]
            recovery = g["total_recovery"] or _ZERO
            target = g["total_target"] or _ZERO
            closed_count = g["closed_count"]

            case_ids = lawyer_case_map.get(lid, [])
            avg_cycle = 0
            if case_ids:
                last_pay_map = dict(
                    PaymentRecord.objects.filter(case_id__in=case_ids)
                    .values("case_id")
                    .annotate(last_pay=Max("payment_date"))
                    .values_list("case_id", "last_pay")
                )
                case_start_map = dict(case_model.objects.filter(id__in=case_ids).values_list("id", "start_date"))
                cycles = [
                    (last_pay_map[cid] - case_start_map[cid]).days
                    for cid in case_ids
                    if cid in last_pay_map and cid in case_start_map and last_pay_map[cid] is not None
                ]
                avg_cycle = sum(cycles) // len(cycles) if cycles else 0

            items.append(
                LawyerPerformanceItem(
                    lawyer_id=lid,
                    lawyer_name=_lawyer_display_name(lawyers.get(lid)),
                    case_count=case_count,
                    total_recovery=recovery,
                    recovery_rate=_safe_rate(recovery, target),
                    avg_recovery_cycle=avg_cycle,
                    closed_rate=_safe_rate(Decimal(closed_count), Decimal(case_count)),
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
        from apps.sales_dispute.models.collection_record import CollectionRecord

        logger.info("get_case_stats: %s ~ %s", start_date, end_date)

        case_model = _get_case_model()
        cases = case_model.objects.filter(start_date__range=(start_date, end_date))
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
