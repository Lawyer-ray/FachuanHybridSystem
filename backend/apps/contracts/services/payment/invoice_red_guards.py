"""红票（红字发票）域的守卫与落账目标判定——纯判定，不碰文件、不开事务。

守卫（G1–G6）全部是**硬错误**，不是提示：红票确认会直接改账、改合同文件夹结构，
任何一条被放过都会写出一份说不清的账。唯一允许偏离的是 G4（重开金额不等），
且必须由调用方显式 ``amount_override=True`` 并在财务日志里留痕。

裁定层 ``invoice_intake_service`` 从这里 import 后按原路径再导出，
测试与调用方仍按 ``invoice_intake_service`` 引用这些名字。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from apps.contracts.models import InvoiceIntake, InvoiceIntakeStatus

#: 重开金额与被冲金额允许的绝对容差（与 invoice_match.AMOUNT_TOLERANCE 同口径）
RED_AMOUNT_TOLERANCE = Decimal("0.005")


def _invoice_is_red(invoice: Any) -> bool:
    """这张 ``Invoice`` 是不是红票（金额为负，或生成它的 intake 判为红票）。"""
    if getattr(invoice, "total_amount", None) is not None and invoice.total_amount < 0:
        return True
    from apps.contracts.models import InvoiceIntake

    intake = InvoiceIntake.objects.filter(invoice_id=invoice.pk).first()
    return bool(intake.is_red) if intake is not None else False


def _ensure_not_red(intake: InvoiceIntake) -> None:
    """老确认入口的红票硬拦（G-red）。

    红票的语义是「抵掉一张已存在的票」，不是「新增一笔开票」：走 ``confirm`` 会
    生成一张金额为负、没有原票关联的 ``Invoice``——账上多一张孤立红票，而没有任何
    东西能说清它冲的是谁。

    为什么同时拦在 Service 层而不只拦在 API：Service 是财务写入的唯一门，绕过 API 的
    脚本/管理后台/未来的批量接口都得吃同一道守卫。
    """
    from apps.core.exceptions import ValidationException

    if intake.is_red:
        raise ValidationException(
            "红字发票请使用「冲红重开」或「仅冲红」入口处理，不能直接确认",
            code="INVOICE_RED_USE_DEDICATED_ENDPOINT",
        )


def _contract_of_invoice(invoice: Any) -> int | None:
    """``Invoice`` 归属的合同（挂收款时跟收款走）。"""
    contract_id = getattr(invoice, "contract_id", None)
    if contract_id:
        return int(contract_id)
    payment = getattr(invoice, "payment", None)
    payment_contract_id = getattr(payment, "contract_id", None)
    return int(payment_contract_id) if payment_contract_id else None


def _red_guards(red: InvoiceIntake, *, contract_id: int | None) -> Any:
    """G1 / G2 / G6：红票能否被一键冲销，返回它要冲掉的那张原 ``Invoice``。

    - G1 ``offset_invoice`` 为空：原票不在本库。只允许人工驳回 + 手工补录原票——
      若允许落成“独立红票”，因为没有原票可冲，这张红票自己就是“未作废的有效票”，
      **会被打进交付包**。一张负数发票交给客户，是能上投诉的。
    - G2 原票合同 ≠ 红票要确认的合同：冲错项目比不冲更糟。
    - G6 原票已有其他已确认红票冲过：双重冲红会让 ``Sum`` 多算一笔负数。
    """
    from apps.core.exceptions import ValidationException

    offset = red.offset_invoice if red.offset_invoice_id else None
    if offset is None:
        raise ValidationException(
            "被红冲的原票不在系统里，不能一键冲红：请驳回此红票，并在对应项目手动补录原票后再处理",
            code="INVOICE_RED_OFFSET_NOT_FOUND",
            errors={"red_against_number": str(red.red_against_number or "")},
        )

    offset_contract_id = _contract_of_invoice(offset)
    if contract_id is not None and offset_contract_id != contract_id:
        raise ValidationException(
            "红票冲销的原票不属于本项目，不能在此项目冲红",
            code="INVOICE_RED_CONTRACT_MISMATCH",
            errors={"offset_invoice_id": offset.pk, "offset_contract_id": offset_contract_id},
        )

    applied_by = InvoiceIntake.objects.filter(
        status=InvoiceIntakeStatus.CONFIRMED, offset_invoice_id=offset.pk
    ).exclude(pk=red.pk)
    if applied_by.exists():
        raise ValidationException(
            "这张原票已被另一张红票冲销过，不能重复冲红",
            code="INVOICE_RED_ALREADY_APPLIED",
            errors={"offset_invoice_id": offset.pk},
        )
    return offset


def _red_guard_amount(red: InvoiceIntake) -> None:
    """红票金额必须是个确定的负数。

    金额未知时冲红，``Sum(total_amount)`` 根本不会变——少一笔负数是直接错账，
    而且从账面上完全看不出漏了什么。这类红票必须先重解析拿到金额。
    """
    from apps.core.exceptions import ValidationException

    if red.total_amount is None:
        raise ValidationException(
            "红字发票金额未识别，不能冲红。请先「重新解析」，确认金额后再冲红",
            code="INVOICE_RED_AMOUNT_UNKNOWN",
        )


def _reissue_guards(
    new: InvoiceIntake,
    *,
    offset: Any,
    contract_id: int | None,
    amount_override: bool,
) -> None:
    """G3 / G4 / G5：重开蓝票的三条硬约束（G4 可由 ``amount_override`` 显式放行）。"""
    from apps.contracts.models import Invoice
    from apps.core.exceptions import ValidationException

    if new.total_amount is None or new.total_amount <= 0:
        raise ValidationException(
            "重开的蓝票金额必须为正数",
            code="INVOICE_REENACT_NOT_POSITIVE",
            errors={"total_amount": str(getattr(new, "total_amount", ""))},
        )

    offset_amount = abs(Decimal(str(getattr(offset, "total_amount", 0) or 0)))
    gap = abs(Decimal(str(new.total_amount)) - offset_amount)
    if gap > RED_AMOUNT_TOLERANCE and not amount_override:
        raise ValidationException(
            f"重开金额 {new.total_amount} 与被冲销金额 {offset_amount} 不一致；改动金额需显式确认并留痕",
            code="INVOICE_REENACT_AMOUNT_MISMATCH",
            errors={"new_total": str(new.total_amount), "offset_total": str(offset_amount)},
        )

    if new.invoice_number and Invoice.objects.filter(invoice_number=new.invoice_number).exists():
        raise ValidationException(
            f"发票号码 {new.invoice_number} 已在库，重开票不能重复入账",
            code="INVOICE_NUMBER_DUPLICATED",
            errors={"invoice_number": new.invoice_number},
        )


def _resolve_payment_for_red(red: InvoiceIntake, *, contract_id: int, user: Any) -> Any | None:
    """红票落到哪笔收款：原票挂的那笔（冲销必须落在同一个付款上）。

    重回退：原票挂在合同名下时，若合同恰好只有一笔收款就用它——单笔收款的项目
    “先开票后付款”其实是“钱已到、票挂合同”，不回填的话冲红后净额永远算不到账上。
    多笔时不猜（猜错的账比没算更难查），留给人工挂。
    """
    from apps.contracts.models import ContractPayment

    offset = red.offset_invoice if red.offset_invoice_id else None
    if offset is not None and offset.payment_id is not None:
        return ContractPayment.objects.filter(pk=offset.payment_id).select_related("contract").first()
    if red.suggested_payment_id is not None and red.suggested_contract_id == contract_id:
        return ContractPayment.objects.filter(pk=red.suggested_payment_id).select_related("contract").first()
    payments = list(ContractPayment.objects.filter(contract_id=contract_id).select_related("contract")[:2])
    return payments[0] if len(payments) == 1 else None
