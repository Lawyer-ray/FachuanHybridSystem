"""到账待认领的业务服务：可见性收敛 + 确认/驳回/撤销 + 候选项目下拉。

## 谁能看到 / 确认（设计文档 §6）

- **收件人**：``intake.inbox_message.source.credential.lawyer``
  （实测：IMAP 来源 1「某律师邮箱」→ credential 2 → 该律师）
- **主办律师**：建议项目 / 已确认项目的 ``assignments`` 里 ``is_primary=True``
- **管理员**：``Lawyer.is_admin``

规则：建议项目的主办律师 ≠ 收件人时，**两人都要看到**这条待办——邮件归属人可能
不懂业务、业务主办看不到到账，任何一方漏掉都会导致钱悬着没人认。

## 为什么确认不能直接复用 ContractPaymentService.create_payment

它在 ``amount + total_received > fixed_amount`` 时抛「累计收款超过合同固定金额」。
由于候选下拉已按资格规则过滤掉收满的项目，"选中项必有余额"是硬保证，正常路径
不会触发。但**并发**（两人同时确认两笔到同一合同）仍可能超付，所以确认走独立
事务 + 行锁，超付时只告警不阻断（财务上"多收了钱"不该被系统拒绝记录）。
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.db.models import Q, QuerySet, Sum
from django.utils import timezone

from apps.contracts.models import ContractFinanceLog, ContractPayment, IntakeStatus, LogLevel, PaymentIntake
from apps.contracts.services.payment.intake_eligibility import eligible_contract_qs, with_paid_total

if TYPE_CHECKING:
    from apps.organization.models import Lawyer

logger = logging.getLogger("apps.contracts")


def _is_admin(user: Any) -> bool:
    return bool(getattr(user, "is_admin", False) or getattr(user, "is_superuser", False))


def _intake_party_q(user: Any) -> Q:
    """「与我相关」的过滤条件：我是收件人 / 我是（建议或已确认）项目主办律师。"""
    q = Q(inbox_message__source__credential__lawyer_id=user.pk)
    q |= Q(suggested_contract__assignments__lawyer_id=user.pk, suggested_contract__assignments__is_primary=True)
    q |= Q(
        confirmed_contract__assignments__lawyer_id=user.pk,
        confirmed_contract__assignments__is_primary=True,
    )
    return q


def visible_intakes_qs(user: Any) -> QuerySet[PaymentIntake]:
    """按当前用户收敛的待认领 QuerySet（管理员看全部）。"""
    qs = PaymentIntake.objects.select_related(
        "inbox_message", "inbox_message__source", "suggested_contract", "confirmed_contract", "payment"
    )
    if _is_admin(user):
        return qs
    return qs.filter(_intake_party_q(user)).distinct()


def can_decide(user: Any, intake: PaymentIntake) -> bool:
    """该用户能否对这条待认领做裁定（确认/驳回/忽略）。"""
    if _is_admin(user):
        return True
    source = getattr(intake.inbox_message, "source", None)
    credential = getattr(source, "credential", None) if source else None
    if credential is not None and credential.lawyer_id == user.pk:
        return True
    for contract in (intake.suggested_contract, intake.confirmed_contract):
        if contract is None:
            continue
        if any(a.lawyer_id == user.pk and a.is_primary for a in contract.assignments.all()):
            return True
    return False


def open_count(user: Any) -> int:
    """首页角标：当前用户可见的待确认条数。"""
    return visible_intakes_qs(user).filter(status=IntakeStatus.PENDING).count()


@transaction.atomic
def confirm_intake(*, intake_id: int, contract_id: int | None, user: Any, note: str = "") -> PaymentIntake:
    """确认归属并**创建收款记录**。

    Args:
        contract_id: 省略 = 采纳系统建议；显式传入 = 人工改判到该项目。
    """
    from apps.core.exceptions import NotFoundError, ValidationException

    intake = PaymentIntake.objects.select_for_update().filter(pk=intake_id).first()
    if intake is None:
        raise NotFoundError(f"待认领款项 {intake_id} 不存在")
    if not can_decide(user, intake):
        # 不泄露存在性：无权即视为不存在
        raise NotFoundError(f"待认领款项 {intake_id} 不存在")
    if intake.status != IntakeStatus.PENDING:
        raise ValidationException(f"该笔到账当前状态为「{intake.get_status_display()}」，不能重复确认")

    target_id = contract_id or intake.suggested_contract_id
    if not target_id:
        raise ValidationException("请选择要归属的项目")

    from apps.contracts.models import Contract

    contract = Contract.objects.select_for_update().filter(pk=target_id).first()
    if contract is None:
        raise NotFoundError(f"项目 {target_id} 不存在")

    # 已收合计：用行锁后的实时值判断是否超付
    paid_total = contract.payments.aggregate(total=Sum("amount")).get("total") or Decimal("0")
    over_paid = contract.fixed_amount is not None and paid_total >= contract.fixed_amount

    payment = ContractPayment.objects.create(
        contract=contract,
        amount=intake.amount,
        received_at=intake.received_at,
        note=_build_payment_note(intake, user),
    )

    intake.status = IntakeStatus.CONFIRMED
    intake.confirmed_contract = contract
    intake.confirmed_by = user
    intake.confirmed_at = timezone.now()
    intake.payment = payment
    if note:
        intake.decision_note = note
    intake.save(
        update_fields=[
            "status",
            "confirmed_contract",
            "confirmed_by",
            "confirmed_at",
            "payment",
            "decision_note",
            "updated_at",
        ]
    )

    if over_paid:
        # 并发或人工硬选导致超付：不阻断（钱确实收了），但必须留痕
        logger.warning(
            "到账确认导致累计收款超过合同固定金额: intake=%s contract=%s amount=%s paid_before=%s fixed=%s",
            intake.pk,
            contract.pk,
            intake.amount,
            paid_total,
            contract.fixed_amount,
        )
        ContractFinanceLog.objects.create(
            contract=contract,
            action="payment_intake_over_paid",
            level=LogLevel.WARN,
            actor=user,
            payload={
                "intake_id": intake.pk,
                "payment_id": payment.pk,
                "amount": str(intake.amount),
                "paid_before": str(paid_total),
                "fixed_amount": str(contract.fixed_amount),
                "operator_id": user.pk,
            },
        )
    else:
        ContractFinanceLog.objects.create(
            contract=contract,
            action="payment_intake_confirmed",
            level=LogLevel.INFO,
            actor=user,
            payload={
                "intake_id": intake.pk,
                "payment_id": payment.pk,
                "amount": str(intake.amount),
                "operator_id": user.pk,
            },
        )
    return intake


def _build_payment_note(intake: PaymentIntake, user: Any) -> str:
    """收款备注：保留银行原文要点，便于日后与邮件对账。"""
    parts = [f"付款人：{intake.payer_name or '未知'}"]
    if intake.on_behalf_of:
        parts.append(f"代{intake.on_behalf_of}")
    parts.append(f"到账认领 #{intake.pk}")
    return "；".join(parts)[:255]


@transaction.atomic
def reject_intake(*, intake_id: int, user: Any, reason: str) -> PaymentIntake:
    """标记为「非记账事件」（营销邮件误判、已人工处理过等）。"""
    return _close_intake(intake_id=intake_id, user=user, reason=reason, status=IntakeStatus.REJECTED)


@transaction.atomic
def ignore_intake(*, intake_id: int, user: Any, reason: str) -> PaymentIntake:
    """标记为「不需记账」（往来款、退款等）。"""
    return _close_intake(intake_id=intake_id, user=user, reason=reason, status=IntakeStatus.IGNORED)


def _close_intake(*, intake_id: int, user: Any, reason: str, status: str) -> PaymentIntake:
    from apps.core.exceptions import NotFoundError, ValidationException

    intake = PaymentIntake.objects.select_for_update().filter(pk=intake_id).first()
    if intake is None or not can_decide(user, intake):
        raise NotFoundError(f"待认领款项 {intake_id} 不存在")
    if intake.status != IntakeStatus.PENDING:
        raise ValidationException(f"该笔到账当前状态为「{intake.get_status_display()}」，不能重复处理")
    intake.status = status
    intake.confirmed_by = user
    intake.confirmed_at = timezone.now()
    intake.decision_note = reason
    intake.save(update_fields=["status", "confirmed_by", "confirmed_at", "decision_note", "updated_at"])
    return intake


@transaction.atomic
def reopen_intake(*, intake_id: int, user: Any) -> PaymentIntake:
    """撤销此前的裁定，回到待确认。

    若已确认并生成了收款记录，**必须同时删除该收款**，否则会留下无主的钱。
    """
    from apps.core.exceptions import NotFoundError, ValidationException

    intake = PaymentIntake.objects.select_for_update().filter(pk=intake_id).first()
    if intake is None or not can_decide(user, intake):
        raise NotFoundError(f"待认领款项 {intake_id} 不存在")
    if intake.status == IntakeStatus.PENDING:
        raise ValidationException("该笔到账已是待确认状态")

    # 顺序很关键：数据库约束「status=confirmed 必须同时有 payment」会在
    # 中间态生效。先把 payment 置空再改 status，那一瞬间仍是 confirmed 却没了
    # payment，直接违反约束（真机复现过：chk_paymentintake_confirmed_has_payment）。
    # 所以 status / payment / confirmed_* 必须在同一个 UPDATE 里改掉。
    payment_id = intake.payment_id
    contract_id = intake.payment.contract_id if intake.payment else None

    intake.status = IntakeStatus.PENDING
    intake.confirmed_contract = None
    intake.confirmed_by = None
    intake.confirmed_at = None
    intake.payment = None
    intake.save(update_fields=["status", "confirmed_contract", "confirmed_by", "confirmed_at", "payment", "updated_at"])

    # 收款记录在状态落定之后再删：反过来的话删除失败会留下 confirmed 却无 payment 的脏数据
    if payment_id:
        ContractPayment.objects.filter(pk=payment_id).delete()
        if contract_id:
            ContractFinanceLog.objects.create(
                contract_id=contract_id,
                action="payment_intake_reverted",
                level=LogLevel.WARN,
                actor=user,
                payload={"intake_id": intake.pk, "removed_payment_id": payment_id, "operator_id": user.pk},
            )
    return intake


def selectable_contracts(*, search: str = "", exclude_fully_paid: bool = True) -> QuerySet[Any]:
    """「换个项目」下拉的数据源（未切片的 QuerySet）。

    **必须**走 ``eligible_contract_qs``：与自动匹配共用同一套资格规则，
    否则会出现「下拉里能选、但系统永远不推荐」的自相矛盾（设计文档 §7.1）。

    Args:
        exclude_fully_paid: 发票认领的下拉传 ``False``，与发票匹配器同口径
            （发票在钱收齐后开是正常顺序，收满不应被隐藏）。

    刻意**不在这里切片**：切片后的 QuerySet 不能再 filter/count/get，
    调用方（API 层）才决定取多少条。此前在这里 ``[:limit]`` 导致
    下游任何过滤都抛 "Cannot filter a query once a slice has been taken"。
    """
    qs = eligible_contract_qs(include_expired=True, exclude_fully_paid=exclude_fully_paid).order_by("-specified_date")
    term = (search or "").strip()
    if term:
        qs = qs.filter(Q(name__icontains=term) | Q(filing_number__icontains=term))
    return with_paid_total(qs)
