"""到账认领的「项目资格」判定——**唯一真源**。

## 为什么必须只有一份

「哪些项目可以被一笔到账认领」这个问题有两个消费方：

1. 自动匹配器：给一笔到账算出候选项目；
2. 前端「换个项目」下拉：让人手工选项目。

如果两处各写一份过滤条件，必然漂移出「下拉里能选、但自动匹配永远不选」这种
自相矛盾的结果（用户会在下拉里选中一个收满的项目，然后疑惑为什么系统不推荐它）。
所以两个入口都调用本模块，**禁止在别处再写一遍过滤**。

## 资格规则（设计文档 §4.1）

硬排除（项目根本不可能接收这笔到账）：

- 合同已归档 ``status=ARCHIVED``：结案归档后不再挂新收款
- 合同未签约 ``status=UNSIGNED``：还没签，谈不上收费
- **已收满**：``fixed_amount`` 非空且已收合计 >= ``fixed_amount``。
  这是最容易漏的一条——收满后再来一笔钱，业务上要么是合同外多付
  （需另签合同），要么该退，都不应记进这个项目。
- 案件已结案：项目的全部关联案件都是 ``closed``

降权但不排除：合同已过 ``end_date``（顾问合同到期后续费打款是真实场景）。

## 已收合计为什么用聚合而不是 ``contract.payments``

候选要遍历上百份合同，逐份访问 ``payments`` 会打出 N+1。本模块统一用一次
``annotate(Sum)`` 把 ``paid_total`` 挂到 QuerySet 上，调用方直接读注解字段。
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.db.models import DecimalField, F, Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce

if TYPE_CHECKING:
    from apps.contracts.models import Contract

# 排除原因（写进 match_snapshot.excluded_hints，前端据此显示不同提示文案）
EXCLUDED_ARCHIVED = "archived"
EXCLUDED_UNSIGNED = "unsigned"
EXCLUDED_FULLY_PAID = "fully_paid"
EXCLUDED_CASE_CLOSED = "case_closed"

EXCLUDED_LABELS: dict[str, str] = {
    EXCLUDED_ARCHIVED: "项目已归档",
    EXCLUDED_UNSIGNED: "合同未签约",
    EXCLUDED_FULLY_PAID: "费用已收齐",
    EXCLUDED_CASE_CLOSED: "案件已结案",
}


def _paid_total_expression() -> Coalesce:
    """已收合计的聚合表达式（缺省 0，避免 Sum 返回 None）。"""
    return Coalesce(
        Sum("payments__amount"),
        Value(Decimal("0"), output_field=DecimalField(max_digits=14, decimal_places=2)),
    )


def with_paid_total(qs: QuerySet[Contract]) -> QuerySet[Contract]:
    """给合同 QuerySet 挂上 ``paid_total`` 注解（已收合计）。"""
    return qs.annotate(paid_total=_paid_total_expression())


def fully_paid_q() -> Q:
    """「已收满」的判定。

    - ``fixed_amount`` 为空：无法判断上限，不算收满（全风险合同常见）。
    - ``paid_total >= fixed_amount``：收满，含正好相等。
    """
    return Q(fixed_amount__isnull=False) & Q(paid_total__gte=F("fixed_amount"))


def _case_closed_q() -> Q:
    """「案件全部结案」的判定。

    只对**有关联案件**的项目生效：没挂案件的非诉项目不该被这条排除。
    ``~Q(cases__isnull=True)`` 保证否定条件只作用于"有案件"的行。
    """
    return Q(cases__isnull=False) & ~Q(cases__status="active")


def _archived_or_unsigned_q() -> Q:
    return Q(status="archived") | Q(status="unsigned")


def eligible_contract_qs(*, include_expired: bool = True) -> QuerySet[Contract]:
    """返回**可被认领**的在办项目 QuerySet（已挂 ``paid_total`` 注解）。

    自动匹配器与前端下拉共用此函数，保证口径一致。

    Args:
        include_expired: 是否包含已过 ``end_date`` 的项目。默认包含——
            顾问合同到期后续费打款是真实场景，排除会漏。调用方（匹配器）
            用 ``caveat`` 提示到期，而不是在这里砍掉。
    """
    from apps.contracts.models import Contract

    qs = with_paid_total(Contract.objects.all())
    qs = qs.filter(status="active")
    # 已收满：用 NOT 包住"收满"条件
    qs = qs.exclude(fully_paid_q())
    # 案件全部结案：exclude "有案件且没有在办案件"
    qs = qs.exclude(_case_closed_q())
    if not include_expired:
        from django.utils import timezone

        qs = qs.filter(Q(end_date__isnull=True) | Q(end_date__gte=timezone.localdate()))
    return qs


def _sum_payments(contract: Any) -> Decimal:
    """算已收合计，兼容三种取法：注解 > Manager（聚焦查询）> 预加载列表。

    第三种是真实需要：调用方常 ``prefetch_related("payments")`` 以免 N+1，
    此时 ``contract.payments`` 是 RelatedManager 但数据已在缓存里，
    直接遍历即可，不应再打一次数据库。
    """
    payments = getattr(contract, "payments", None)
    if payments is None:
        return Decimal("0")
    aggregate = getattr(payments, "aggregate", None)
    if callable(aggregate):
        try:
            total = aggregate(total=Sum("amount")).get("total")
        except (AttributeError, TypeError, ValueError):
            total = None
        if total is not None:
            return Decimal(str(total))
    try:
        return sum((Decimal(str(getattr(p, "amount", 0) or 0)) for p in payments.all()), Decimal("0"))
    except (AttributeError, TypeError, ValueError):
        return Decimal("0")


def ineligible_reason(contract: Any, *, paid_total: Decimal | None = None) -> str:
    """给出单个合同**不合格的原因**，合格则返回空串。

    用于把被排除的合同写进 ``excluded_hints``——既执行「收满不匹配」，
    又保留线索让人看到"系统想到过这个项目，因为 X 排除了"。

    参数 ``paid_total`` 允许调用方传入已算好的合计，避免重复聚合查询。
    """
    status = str(getattr(contract, "status", "") or "")
    if status == "archived":
        return EXCLUDED_ARCHIVED
    if status == "unsigned":
        return EXCLUDED_UNSIGNED

    if paid_total is None:
        paid_total = getattr(contract, "paid_total", None)
    if paid_total is None:
        paid_total = _sum_payments(contract)

    fixed = getattr(contract, "fixed_amount", None)
    if fixed is not None and paid_total >= fixed:
        return EXCLUDED_FULLY_PAID

    cases = list(contract.cases.all()) if hasattr(contract, "cases") else []
    if cases and all(str(getattr(c, "status", "") or "") != "active" for c in cases):
        return EXCLUDED_CASE_CLOSED

    return ""


def excluded_note(reason: str, contract: Any, *, paid_total: Decimal | None = None) -> str:
    """给 ``excluded_hints`` 的一句人话说明。

    这里刻意不复用前端文案——它要带上具体数字，人才判得了
    "这个项目是不是真的已经收过钱了"。
    """
    label = EXCLUDED_LABELS.get(reason, "不可认领")
    if reason == EXCLUDED_FULLY_PAID:
        fixed = getattr(contract, "fixed_amount", None)
        paid = paid_total if paid_total is not None else getattr(contract, "paid_total", None)
        if fixed is not None and paid is not None:
            return f"{label}（{paid}/{fixed}）"
    # 刻意**不**在这里写「请先新建合同」之类的指引：系统只如实陈述这个项目
    # 为何不适合承接这笔钱，要不要另立项目由人自己判断（用户明确要求不引导）。
    return label
