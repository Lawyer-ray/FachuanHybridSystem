"""待认领发票的裁定动作：确认绑定 / 驳回 / 撤销。

## 确认绑定为什么必须复用 ``InvoiceFileService.save_invoice``

律师原来是把发票**手动拖进项目页面**的，那条链路已经做对了全部落地动作：
识别 → 命名（``发票（合同名）_YYYYMMDD开具.pdf``）→ 落 media → 镜像到合同文件夹
→ 回填收款的已开票金额。邮件认领只是换了个**入口**（从"人手拖文件"变成
"解析后点确认"），落地动作必须走同一份代码——两套命名/落盘规则并存的那天，
同一个案子下就会出现两种文件名的票。

所以本模块**不做任何文件操作**，只负责：取来源附件 → 交给 ``save_invoice`` →
写回 intake 状态。文件怎么命名、要不要镜像文件夹，全部由那条既有链路决定。

## 撤销为什么删得干净

``InvoiceFileService`` 把发票镜像到合同文件夹后，落点相对路径写在
``Invoice.folder_subpath``（本功能新增字段）。撤销时据此调
``ContractFolderBrowseService.delete_entry`` —— 它**不是物理删除**，而是把文件
移进绑定根下的 ``_已删除/``（带时间戳，随时可找回）。所以"撤销即清理"既干净
又留了后悔药，不需要用户手工去 Finder 里删残留。

## 冲红重开为什么是一个原子动作

"冲红"与"重开"在账上是**同一件事的两面**：红票让 ``Sum(total_amount)`` 变负，
重开蓝票把它补回正。中间态（只有红票、没有重开票）是合法的，而且正是
``VOIDED_PENDING_REISSUE`` 要表达的东西；但如果分两次点、第二次失败了，
系统就会停在"账已冲、人以为已重开"的状态。所以 ``confirm_red_reenact`` 把
落红票 / 落重开票 / 移入已冲红 / 重算收款 / 写审计日志包在**一个事务**里。

守卫（G1–G6）全部是**硬错误**，不是提示：红票确认会直接改账、改合同文件夹结构，
任何一条守卫放过都会写出一份说不清的账。唯一允许偏离的是 G4（重开金额不等），
且必须由调用方显式 ``amount_override=True``，并在财务日志里留痕。
"""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.contracts.models import InvoiceIntake, InvoiceIntakeStatus

logger = logging.getLogger("apps.contracts")

__all__ = [
    "confirm_invoice_intake",
    "confirm_red_only",
    "confirm_red_reenact",
    "reject_invoice_intake",
    "reopen_invoice_intake",
    "open_count",
    "red_group_facts",
    "reparse_invoice_intake",
]

#: 重开金额与被冲金额允许的绝对容差（与 invoice_match.AMOUNT_TOLERANCE 同口径）
RED_AMOUNT_TOLERANCE = Decimal("0.005")


def _is_admin(user: Any) -> bool:
    return bool(getattr(user, "is_admin", False) or getattr(user, "is_superuser", False))


def open_count(user: Any) -> int:
    """首页角标：与我相关的待认领发票数。"""
    # visible_intakes_qs 返回 Any（跨模型 QuerySet），count() 需显式收敛成 int
    return int(visible_intakes_qs(user).filter(status=InvoiceIntakeStatus.PENDING).count())


def visible_intakes_qs(user: Any) -> Any:
    """「与我相关」的待认领发票。

    收敛口径与到账款项一致：邮件收件人 / 建议项目主办律师 / 管理员。
    这里不复刻复杂权限推导——发票天然属于律所内部财务流，可见范围给足，
    真正危险的动作（确认绑定）另有 :func:`can_decide` 把关。
    """
    from django.db.models import Q

    from apps.contracts.models import ContractAssignment

    if _is_admin(user):
        return InvoiceIntake.objects.all()

    primary_contract_ids = ContractAssignment.objects.filter(lawyer=user, is_primary=True).values("contract_id")
    return InvoiceIntake.objects.filter(
        Q(inbox_message__source__credential__lawyer=user)
        | Q(suggested_contract_id__in=primary_contract_ids)
        | Q(suggested_contract__assignments__lawyer=user)
    ).distinct()


def get_intake_for_user(*, intake_id: int, user: Any) -> InvoiceIntake:
    """取一条待认领发票（带常用关联），无权即视为不存在。

    ORM 留在 Service 层：API 层出现 ``Model.objects`` 会撞四层架构门禁。
    无权时抛 NotFound 而不是 PermissionDenied——不泄露记录存在性。
    """
    from apps.core.exceptions import NotFoundError

    # visible_intakes_qs 声明为 Any（跨模型 Q 查询），这里显式收敛回模型类型
    intake: InvoiceIntake | None = (
        visible_intakes_qs(user)
        .select_related("suggested_contract", "confirmed_contract", "inbox_message", "inbox_message__source")
        .filter(pk=intake_id)
        .first()
    )
    if intake is None or not can_decide(user, intake):
        raise NotFoundError(f"待认领发票 {intake_id} 不存在")
    return intake


def generated_invoice_facts(intake: InvoiceIntake) -> dict[str, str]:
    """确认后那张发票的**展示名 + 文件夹落点**（未确认则两者均空串）。

    展示名走 ``InvoiceFileService.display_filename`` 的同一份命名规则——绝不另拼。
    合同名取**确认到的**合同（人工改判过时可能与建议合同不同）。

    一次查库同时给两个字段：列表只关心文件名，详情还要落点，分两次查是白花。
    """
    blank = {"display_filename": "", "folder_subpath": ""}
    if intake.invoice_id is None:
        return blank
    from pathlib import Path

    from apps.contracts.models import Invoice
    from apps.contracts.services.payment.invoice_file_service import InvoiceFileService

    invoice = Invoice.objects.filter(pk=intake.invoice_id).select_related("payment__contract", "contract").first()
    if invoice is None:
        return blank
    payment = invoice.payment if invoice.payment_id else None
    contract = invoice.contract or (payment.contract if payment is not None else None)
    return {
        "display_filename": InvoiceFileService().display_filename(
            contract_name=str(getattr(contract, "name", "") or ""),
            seller=str(invoice.seller_name or ""),
            inv_date=invoice.invoice_date,
            ext=Path(str(invoice.file_path or "")).suffix.lower(),
            # 红票尾部是「红字开具」：列表里与它冲掉/重开的那张票必须看得出区别
            is_red=_invoice_is_red(invoice),
        ),
        "folder_subpath": str(getattr(invoice, "folder_subpath", "") or ""),
    }


def _invoice_is_red(invoice: Any) -> bool:
    """这张 ``Invoice`` 是不是红票（金额为负，或生成它的 intake 判为红票）。"""
    if getattr(invoice, "total_amount", None) is not None and invoice.total_amount < 0:
        return True
    from apps.contracts.models import InvoiceIntake

    intake = InvoiceIntake.objects.filter(invoice_id=invoice.pk).first()
    return bool(intake.is_red) if intake is not None else False


def can_decide(user: Any, intake: InvoiceIntake) -> bool:
    """能不能对这张票做裁定。

    规则：管理员一律可以；其余人须是邮件收件人 或 建议项目的主办律师。
    无权时对外表现为"不存在"，不泄露记录存在性。
    """
    if _is_admin(user):
        return True
    credential_lawyer_id = getattr(getattr(intake.inbox_message, "source", None), "credential", None)
    if credential_lawyer_id is not None and getattr(credential_lawyer_id, "lawyer_id", None) == user.pk:
        return True
    contract = intake.suggested_contract
    if contract is not None:
        return contract.assignments.filter(lawyer=user, is_primary=True).exists()
    return False


def _attachment_file(intake: InvoiceIntake) -> Any:
    """把邮件附件包成 ``save_invoice`` 能吃的上传对象（它只要求 read/name）。"""
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.message_hub.services.base import resolve_media_attachment_path

    path = resolve_media_attachment_path(intake.attachment_path)
    if path is None:
        from apps.core.exceptions import ValidationException

        raise ValidationException(
            message="发票附件已不在磁盘上，请从邮件原文重新下载后手动上传", code="INVOICE_FILE_MISSING"
        )

    data = Path(path).read_bytes()
    filename = intake.original_filename or Path(path).name
    return SimpleUploadedFile(filename, data, content_type="application/pdf")


@transaction.atomic
def confirm_invoice_intake(
    *,
    intake_id: int,
    contract_id: int | None,
    payment_id: int | None,
    user: Any,
    note: str = "",
) -> InvoiceIntake:
    """确认绑定：把发票落进项目（可选同时挂到某笔收款）。

    Args:
        contract_id: 省略 = 采纳系统建议项目。
        payment_id: 省略 = 挂合同名下（先开票后付款）；显式给出 = 挂到该笔收款，
            由 ``save_invoice`` 回填已开票金额。
    """
    from apps.core.exceptions import NotFoundError, ValidationException

    intake = InvoiceIntake.objects.select_for_update().filter(pk=intake_id).first()
    if intake is None or not can_decide(user, intake):
        raise NotFoundError(f"待认领发票 {intake_id} 不存在")
    if intake.status != InvoiceIntakeStatus.PENDING:
        raise ValidationException(
            f"该发票当前状态为「{intake.get_status_display()}」，不能重复确认", code="INVOICE_INTAKE_NOT_PENDING"
        )
    _ensure_not_red(intake)

    target_contract_id = contract_id or intake.suggested_contract_id
    if not target_contract_id:
        raise ValidationException("请选择要绑定的项目", code="INVOICE_INTAKE_NO_CONTRACT")

    # 未显式指定收款时，采纳系统预选（已按"唯一且金额吻合"规则算过，见 invoice_match）
    target_payment_id = payment_id
    if target_payment_id is None and contract_id is None:
        target_payment_id = intake.suggested_payment_id

    if target_payment_id is not None:
        from apps.contracts.models import ContractPayment

        payment = ContractPayment.objects.filter(pk=target_payment_id).select_related("contract").first()
        if payment is None:
            raise NotFoundError(f"收款记录 {target_payment_id} 不存在")
        if payment.contract_id != target_contract_id:
            raise ValidationException("发票与收款不属于同一项目", code="INVOICE_PAYMENT_CONTRACT_MISMATCH")

    from apps.contracts.models import Invoice
    from apps.contracts.services.payment.invoice_file_service import InvoiceFileService

    saved = InvoiceFileService().save_invoice(
        payment_id=target_payment_id,
        contract_id=target_contract_id if target_payment_id is None else None,
        uploaded_file=_attachment_file(intake),
        # 必须把扫描时已识别到的字段传进去：save_invoice 的"识别字段回填"与
        # "按 parole 金额重算已开票金额"都从这个对象取，不传就会出现
        # 「票建好了但金额是空的、收款还显示未开票」。
        parsed=_parsed_from_intake(intake),
        user=user,
        # 待认领确认路径上同号票几乎必然是“同一张票被确认了两次”，必须硬拦
        # （人手拖文件上传那条路径仍只提示，见 save_invoice 的 docstring）
        reject_duplicated_number=True,
    )

    # 文件夹副本落点必须入库：撤销时靠它确定性地把副本移进「_已删除」
    if saved.folder_subpath:
        Invoice.objects.filter(pk=saved.id).update(folder_subpath=saved.folder_subpath)

    intake.status = InvoiceIntakeStatus.CONFIRMED
    intake.confirmed_contract_id = target_contract_id
    intake.confirmed_payment_id = target_payment_id
    intake.confirmed_by = user
    intake.confirmed_at = timezone.now()
    intake.invoice_id = saved.id
    if note:
        intake.decision_note = note
    intake.save(
        update_fields=[
            "status",
            "confirmed_contract",
            "confirmed_payment",
            "confirmed_by",
            "confirmed_at",
            "invoice",
            "decision_note",
            "updated_at",
        ]
    )

    _log_finance(intake, target_contract_id, "invoice_intake_confirmed", user, {"invoice_id": saved.id})
    logger.info(
        "invoice_intake_confirmed",
        extra={
            "intake_id": intake.pk,
            "contract_id": target_contract_id,
            "payment_id": target_payment_id,
            "invoice_id": saved.id,
            "folder_subpath": saved.folder_subpath,
        },
    )
    return intake


# ── 冲红重开（裁定层）──────────────────────────────────────────


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


def _lock_pending_intake(intake_id: int, user: Any) -> InvoiceIntake:
    """取一条待裁定的 intake 并锁行（并发下两个浏览器不能同时冲同一张票）。"""
    from apps.core.exceptions import NotFoundError, ValidationException

    intake = InvoiceIntake.objects.select_for_update().filter(pk=intake_id).first()
    if intake is None or not can_decide(user, intake):
        raise NotFoundError(f"待认领发票 {intake_id} 不存在")
    if intake.status != InvoiceIntakeStatus.PENDING:
        raise ValidationException(
            f"该发票当前状态为「{intake.get_status_display()}」，不能重复确认", code="INVOICE_INTAKE_NOT_PENDING"
        )
    return intake


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


def _land_red_and_reissue(
    *,
    red: InvoiceIntake,
    new: InvoiceIntake | None,
    contract_id: int,
    payment: Any | None,
    user: Any,
) -> tuple[Any, Any | None]:
    """落两张票（红票 + 可选的蓝票），并把原票移进 ``已冲红/``。

    顺序有意义：先落红票→移原票→落重开票。原票移动失败只记日志不抛——
    账务事实已经确定，文件位置是“锦上添花”；反过来说，若因为文件夹解绑/云存储
    就让整笔冲红失败，律师会反复重试并最终手工改库。
    """
    from apps.contracts.models import Invoice
    from apps.contracts.services.payment.invoice_file_service import InvoiceFileService

    service = InvoiceFileService()
    offset = red.offset_invoice if red.offset_invoice_id else None
    offset_subpath = str(getattr(offset, "folder_subpath", "") or "") if offset is not None else ""

    saved_red = service.save_invoice(
        payment_id=payment.pk if payment is not None else None,
        contract_id=contract_id if payment is None else None,
        uploaded_file=_attachment_file(red),
        parsed=_parsed_from_intake(red),
        user=user,
        reject_duplicated_number=True,
    )
    if saved_red.folder_subpath:
        Invoice.objects.filter(pk=saved_red.id).update(folder_subpath=saved_red.folder_subpath)

    if offset is not None and offset_subpath and offset_subpath.split("/")[-2:-1] != ["已冲红"]:
        try:
            service.move_invoice_to_voided(invoice_id=offset.pk, user=user)
        except Exception:
            logger.warning(
                "invoice_voided_move_failed", extra={"invoice_id": offset.pk, "subpath": offset_subpath}, exc_info=True
            )

    saved_new = None
    if new is not None:
        saved_new = service.save_invoice(
            payment_id=payment.pk if payment is not None else None,
            contract_id=contract_id if payment is None else None,
            uploaded_file=_attachment_file(new),
            parsed=_parsed_from_intake(new),
            user=user,
            reject_duplicated_number=True,
        )
        if saved_new.folder_subpath:
            Invoice.objects.filter(pk=saved_new.id).update(folder_subpath=saved_new.folder_subpath)
    return saved_red, saved_new


def _mark_confirmed(
    intake: InvoiceIntake, *, contract_id: int, payment_id: int | None, invoice_id: int, user: Any
) -> None:
    """把 intake 置为已确认并指向落成的发票。

    ``supersedes_intake`` 必须在 update_fields 里：重开蓝票的组内配对靠它，
    漏写会让「整组撤销」找不到另一半（表现为只回滚一半，最贵的那类错）。
    """
    intake.status = InvoiceIntakeStatus.CONFIRMED
    intake.confirmed_contract_id = contract_id
    intake.confirmed_payment_id = payment_id
    intake.confirmed_by = user
    intake.confirmed_at = timezone.now()
    intake.invoice_id = invoice_id
    intake.save(
        update_fields=[
            "status",
            "confirmed_contract",
            "confirmed_payment",
            "confirmed_by",
            "confirmed_at",
            "invoice",
            "supersedes_intake",
            "updated_at",
        ]
    )


@transaction.atomic
def confirm_red_reenact(
    *,
    red_intake_id: int,
    new_intake_id: int | None,
    user: Any,
    note: str = "",
    amount_override: bool = False,
) -> dict[str, Any]:
    """一次裁定完成「冲红 + 重开」：红票冲原票，新蓝票替代原票入账。

    ``new_intake_id`` 为空时退化为「只冲红」（不开新票），但审计日志动作名不同——
    真正的“客户不要票了”应走 :func:`confirm_red_only`，从入口就区分开。

    返回 ``{"red_intake": …, "new_intake": … | None, "red_invoice_id": …, "new_invoice_id": …}``。
    """
    from apps.core.exceptions import NotFoundError

    red = _lock_pending_intake(red_intake_id, user)
    if not red.is_red:
        from apps.core.exceptions import ValidationException

        raise ValidationException("这不是红字发票，请走普通确认", code="INVOICE_RED_NOT_RED")

    contract_id = red.suggested_contract_id
    if not contract_id:
        from apps.core.exceptions import ValidationException

        raise ValidationException("红字发票未匹配到项目，请先指定项目", code="INVOICE_INTAKE_NO_CONTRACT")
    _red_guard_amount(red)
    offset = _red_guards(red, contract_id=contract_id)

    new: InvoiceIntake | None = None
    if new_intake_id is not None:
        new = _lock_pending_intake(new_intake_id, user)
        if new.pk == red.pk:
            from apps.core.exceptions import ValidationException

            raise ValidationException("重开票不能是红票自己", code="INVOICE_REENACT_SELF")
        if new.is_red:
            from apps.core.exceptions import ValidationException

            raise ValidationException("重开的票必须是非红票", code="INVOICE_REENACT_IS_RED")
        _reissue_guards(new, offset=offset, contract_id=contract_id, amount_override=amount_override)

    payment = _resolve_payment_for_red(red, contract_id=contract_id, user=user)
    saved_red, saved_new = _land_red_and_reissue(red=red, new=new, contract_id=contract_id, payment=payment, user=user)

    _mark_confirmed(
        red, contract_id=contract_id, payment_id=payment.pk if payment else None, invoice_id=saved_red.id, user=user
    )
    if new is not None and saved_new is not None:
        new.supersedes_intake_id = red.pk
        _mark_confirmed(
            new, contract_id=contract_id, payment_id=payment.pk if payment else None, invoice_id=saved_new.id, user=user
        )

    if note:
        red.decision_note = note
        red.save(update_fields=["decision_note", "updated_at"])
        if new is not None:
            new.decision_note = note
            new.save(update_fields=["decision_note", "updated_at"])

    if payment is not None:
        from apps.contracts.services.payment.invoice_file_service import InvoiceFileService

        InvoiceFileService().recompute_payment_invoicing(payment)

    override_payload: dict[str, Any] = {"override": bool(amount_override)}
    if amount_override and new is not None:
        override_payload["new_total_amount"] = str(new.total_amount)
        override_payload["offset_total_amount"] = str(getattr(offset, "total_amount", "") or "")
        override_payload["override_note"] = note
    _log_finance(
        red,
        contract_id,
        "invoice_red_reenacted" if new is not None else "invoice_red_only",
        user,
        {
            "invoice_id": saved_red.id,
            "offset_invoice_id": offset.pk,
            "offset_invoice_number": str(getattr(offset, "invoice_number", "") or ""),
            "red_confirmation_no": str(red.red_confirmation_no or ""),
            "new_intake_id": new.pk if new is not None else None,
            "new_invoice_id": saved_new.id if saved_new is not None else None,
            "payment_id": payment.pk if payment is not None else None,
            **override_payload,
        },
    )
    if new is not None:
        _log_finance(
            new,
            contract_id,
            "invoice_intake_confirmed",
            user,
            {"invoice_id": saved_new.id if saved_new else None, "supersedes_intake_id": red.pk},
        )

    logger.info(
        "invoice_red_reenacted",
        extra={
            "red_intake_id": red.pk,
            "new_intake_id": new.pk if new is not None else None,
            "contract_id": contract_id,
            "offset_invoice_id": offset.pk,
            "amount_override": bool(amount_override),
        },
    )
    return {
        "red_intake": red,
        "new_intake": new,
        "red_invoice_id": saved_red.id,
        "new_invoice_id": saved_new.id if saved_new is not None else None,
    }


@transaction.atomic
def confirm_red_only(*, red_intake_id: int, user: Any, note: str = "") -> dict[str, Any]:
    """只冲红、不重开（客户不要这张票了）。

    与 :func:`confirm_red_reenact` 分开一个入口而不是用可选参数：两条路径的审计
    动作名与后续影响不同，而且“忘记传 ``new_intake_id``”会静默变成不重开——
    那正是最贵的一类错。守卫同 G1 / G2 / G6（原票必须在本库、合同必须一致、不能双重冲红）。
    """
    red = _lock_pending_intake(red_intake_id, user)
    if not red.is_red:
        from apps.core.exceptions import ValidationException

        raise ValidationException("这不是红字发票，请走普通确认", code="INVOICE_RED_NOT_RED")
    contract_id = red.suggested_contract_id
    if not contract_id:
        from apps.core.exceptions import ValidationException

        raise ValidationException("红字发票未匹配到项目，请先指定项目", code="INVOICE_INTAKE_NO_CONTRACT")
    _red_guard_amount(red)
    _red_guards(red, contract_id=contract_id)

    payment = _resolve_payment_for_red(red, contract_id=contract_id, user=user)
    saved_red, _ = _land_red_and_reissue(red=red, new=None, contract_id=contract_id, payment=payment, user=user)
    _mark_confirmed(
        red, contract_id=contract_id, payment_id=payment.pk if payment else None, invoice_id=saved_red.id, user=user
    )
    if note:
        red.decision_note = note
        red.save(update_fields=["decision_note", "updated_at"])

    if payment is not None:
        from apps.contracts.services.payment.invoice_file_service import InvoiceFileService

        InvoiceFileService().recompute_payment_invoicing(payment)

    offset = red.offset_invoice
    _log_finance(
        red,
        contract_id,
        "invoice_red_only",
        user,
        {
            "invoice_id": saved_red.id,
            "offset_invoice_id": getattr(offset, "pk", None),
            "offset_invoice_number": str(getattr(offset, "invoice_number", "") or ""),
            "red_confirmation_no": str(red.red_confirmation_no or ""),
            "payment_id": payment.pk if payment is not None else None,
            "override": False,
        },
    )
    logger.info(
        "invoice_red_only_confirmed",
        extra={"red_intake_id": red.pk, "contract_id": contract_id, "offset_invoice_id": getattr(offset, "pk", None)},
    )
    return {"red_intake": red, "new_intake": None, "red_invoice_id": saved_red.id, "new_invoice_id": None}


def _parsed_from_intake(intake: InvoiceIntake) -> Any:
    """把 intake 上已有的识别事实包成 ``ParsedInvoice``，交给 save_invoice 回填。

    只搬「票面事实」，不带任何税号/身份证（扫描阶段就已经把它们挡在外面了）。
    """
    from apps.invoice_recognition.services.invoice_parser import ParsedInvoice

    return ParsedInvoice(
        invoice_number=intake.invoice_number or "",
        invoice_date=intake.invoice_date,
        total_amount=intake.total_amount,
        buyer_name=intake.buyer_name or "",
        project_name="",
        remark=intake.remark or "",
        project_code=intake.project_code or "",
        # 红票事实必须透传：save_invoice 靠它决定文件名尾标与落点（已冲红/）
        red_against_number=str(str(getattr(intake, "red_against_number", "") or "") or ""),
        red_confirmation_no=str(getattr(intake, "red_confirmation_no", "") or ""),
    )


def _log_finance(intake: InvoiceIntake, contract_id: int, action: str, user: Any, extra: dict[str, Any]) -> None:
    """写财务审计日志（失败不阻断主流程：日志记录本身不是业务成功条件）。"""
    try:
        from apps.contracts.models import ContractFinanceLog

        ContractFinanceLog.objects.create(
            contract_id=contract_id,
            action=action,
            actor=user,
            payload={
                "intake_id": intake.pk,
                "invoice_number": intake.invoice_number,
                "total_amount": str(intake.total_amount) if intake.total_amount is not None else "",
                "operator_id": getattr(user, "pk", None),
                **extra,
            },
        )
    except Exception:
        logger.warning("invoice_intake_finance_log_failed", extra={"intake_id": intake.pk}, exc_info=True)


@transaction.atomic
def reject_invoice_intake(*, intake_id: int, user: Any, reason: str) -> InvoiceIntake:
    """标记为无关发票（不是给本所的票 / 已手工处理）。可撤销。"""
    from apps.core.exceptions import NotFoundError, ValidationException

    intake = InvoiceIntake.objects.select_for_update().filter(pk=intake_id).first()
    if intake is None or not can_decide(user, intake):
        raise NotFoundError(f"待认领发票 {intake_id} 不存在")
    if intake.status != InvoiceIntakeStatus.PENDING:
        raise ValidationException("只有待确认的发票可以驳回", code="INVOICE_INTAKE_NOT_PENDING")

    intake.status = InvoiceIntakeStatus.REJECTED
    intake.confirmed_by = user
    intake.confirmed_at = timezone.now()
    intake.decision_note = reason
    intake.save(update_fields=["status", "confirmed_by", "confirmed_at", "decision_note", "updated_at"])
    return intake


@transaction.atomic
def reopen_invoice_intake(*, intake_id: int, user: Any) -> InvoiceIntake:
    """撤销确认/驳回，回到待确认。

    确认过的会**一并删除**已生成的 Invoice 记录、media 文件与合同文件夹副本
    （副本移入 ``_已删除/`` 而非物理删除，可找回）。先删文件再删记录：
    反过来的话记录没了、文件成孤儿，就再也没人知道该删哪个。

    **冲红重开是整组回滚**：从红票点撤销，要连带把它冲掉的原票从 ``已冲红/`` 移回、
    把重开蓝票一并删掉；从重开蓝票点撤销，要走同一个组，结果完全一样。
    半截状态（红票删了、原票还在 ``已冲红/``，或者新票还挂在账上）是比错账
    更难查的东西，所以组内任何一端都不能单独回滚。
    """
    from apps.core.exceptions import NotFoundError, ValidationException

    intake = InvoiceIntake.objects.select_for_update().filter(pk=intake_id).first()
    if intake is None or not can_decide(user, intake):
        raise NotFoundError(f"待认领发票 {intake_id} 不存在")
    if intake.status == InvoiceIntakeStatus.PENDING:
        raise ValidationException("该发票已经是待确认状态", code="INVOICE_INTAKE_ALREADY_PENDING")

    group = _red_group_of(intake)
    if group is not None:
        return _reopen_red_group(group, user)

    if intake.invoice_id is not None:
        _remove_generated_invoice(intake, user)
    _reset_intake_to_pending(intake)
    return intake


def _red_group_of(intake: InvoiceIntake) -> dict[str, Any] | None:
    """这条 intake 属于哪个冲红重开组（不在组里则 ``None``）。

    组的键用 ``supersedes_intake`` 的双向关系（不新增字段）：

    - 重开蓝票 → ``supersedes_intake`` 指向红票；
    - 红票 → 被某条蓝票 ``supersedes_intake`` 指向（反向关系）。

    原票（被冲销的蓝票）的 intake 不自己成组：它只是组内要被恢复的那一端，
    它的撤销走普通路径。
    """
    if intake.supersedes_intake_id:
        red = InvoiceIntake.objects.filter(pk=intake.supersedes_intake_id).first()
        if red is not None:
            return {"red": red, "reissue": intake}
    reissue = InvoiceIntake.objects.filter(supersedes_intake_id=intake.pk).first()
    if reissue is not None:
        return {"red": intake, "reissue": reissue}
    return None


def _reopen_red_group(group: dict[str, Any], user: Any) -> InvoiceIntake:
    """整组回滚：删红票 + 删重开票 + 原票移回原位。

    顺序固定为「先删两张票（文件移 ``_已删除/``）→ 再把原票移回」：
    反过来的话原票已回到根目录、红票却还挂在账上，中途失败就是“两张有效票”，
    会被归档带走。
    """
    red: InvoiceIntake = group["red"]
    reissue: InvoiceIntake | None = group["reissue"]
    offset = red.offset_invoice if red.offset_invoice_id else None
    contract_id = red.confirmed_contract_id or red.suggested_contract_id

    for member in (reissue, red):
        if member is None or member.invoice_id is None:
            continue
        _remove_generated_invoice(member, user)

    if offset is not None and contract_id is not None:
        _restore_invoice_folder_position(offset, contract_id, user)

    if reissue is not None:
        reissue.supersedes_intake_id = None
        reissue.status = InvoiceIntakeStatus.PENDING
        reissue.confirmed_contract = None
        reissue.confirmed_payment = None
        reissue.confirmed_by = None
        reissue.confirmed_at = None
        reissue.save(
            update_fields=[
                "supersedes_intake",
                "status",
                "confirmed_contract",
                "confirmed_payment",
                "confirmed_by",
                "confirmed_at",
                "updated_at",
            ]
        )
    _reset_intake_to_pending(red)
    red.save(
        update_fields=[
            "status",
            "confirmed_contract",
            "confirmed_payment",
            "confirmed_by",
            "confirmed_at",
            "invoice",
            "updated_at",
        ]
    )
    if contract_id is not None:
        _log_finance(
            red,
            contract_id,
            "invoice_red_group_reopened",
            user,
            {
                "red_intake_id": red.pk,
                "reissue_intake_id": reissue.pk if reissue is not None else None,
                "offset_invoice_id": getattr(offset, "pk", None),
            },
        )
    logger.info(
        "invoice_red_group_reopened",
        extra={"red_intake_id": red.pk, "reissue_intake_id": reissue.pk if reissue is not None else None},
    )
    return red


def _restore_invoice_folder_position(offset: Any, contract_id: int, user: Any) -> None:
    """把被冲销的原票从 ``已冲红/`` 移回发票目录（失败只记日志，不阻断撤销）。"""
    subpath = str(getattr(offset, "folder_subpath", "") or "")
    if not subpath or subpath.split("/")[-2:-1] != ["已冲红"]:
        return
    try:
        from apps.contracts.services.payment.invoice_file_service import InvoiceFileService

        InvoiceFileService().move_invoice_back_from_voided(invoice_id=offset.pk, user=user)
    except Exception:
        logger.warning(
            "invoice_folder_restore_failed", extra={"invoice_id": offset.pk, "subpath": subpath}, exc_info=True
        )


def _reset_intake_to_pending(intake: InvoiceIntake) -> None:
    """把 intake 的裁定结果清空（不动 ``supersedes_intake``，调用方按需处理）。"""
    intake.status = InvoiceIntakeStatus.PENDING
    intake.confirmed_contract = None
    intake.confirmed_payment = None
    intake.confirmed_by = None
    intake.confirmed_at = None
    intake.invoice = None


def _remove_generated_invoice(intake: InvoiceIntake, user: Any) -> None:
    """删掉确认时生成的发票（含文件夹副本与 media 文件）。"""
    from apps.contracts.models import Invoice

    if intake.invoice_id is None:
        return
    invoice = Invoice.objects.filter(pk=intake.invoice_id).select_related("payment__contract", "contract").first()
    if invoice is None:
        return

    payment = invoice.payment if invoice.payment_id else None
    contract_id = invoice.contract_id or (payment.contract_id if payment is not None else None)
    _remove_folder_copy(contract_id, invoice, user)
    _remove_media_file(invoice)
    invoice.delete()

    # 删票后必须重算该笔收款的「已开票金额/状态」：不重算的话撤销完
    # 收款还停在 INVOICED_FULL，项目页会一直说「已全额开票」而实际一张票都没了。
    if payment is not None:
        try:
            from apps.contracts.services.payment.invoice_file_service import InvoiceFileService

            InvoiceFileService().recompute_payment_invoicing(payment)
        except Exception:
            logger.warning("invoice_recompute_after_reopen_failed", extra={"payment_id": payment.pk}, exc_info=True)

    if contract_id is not None:
        _log_finance(intake, contract_id, "invoice_intake_reopened", user, {"removed_invoice_id": intake.invoice_id})


def _remove_folder_copy(contract_id: int | None, invoice: Any, user: Any) -> None:
    """把合同文件夹里的副本移进 ``_已删除/``（软删除，可找回）。"""
    subpath = str(getattr(invoice, "folder_subpath", "") or "")
    if contract_id is None or not subpath:
        return
    try:
        from apps.contracts.services.contract.integrations.folder_browse_service import ContractFolderBrowseService

        ContractFolderBrowseService().delete_entry(
            owner_id=contract_id, subpath=subpath, user=user, org_access=None, perm_open_access=False
        )
        logger.info("invoice_folder_copy_trashed", extra={"contract_id": contract_id, "subpath": subpath})
    except Exception:
        # 文件夹可能已解绑/云存储/权限不足：不阻断撤销，但要让用户知道手工去删
        logger.warning(
            "invoice_folder_copy_trash_failed", extra={"contract_id": contract_id, "subpath": subpath}, exc_info=True
        )


def _remove_media_file(invoice: Any) -> None:
    """删 media 仓库里的权威副本。"""
    file_path = str(getattr(invoice, "file_path", "") or "")
    if not file_path:
        return
    try:
        from django.conf import settings

        target = Path(settings.MEDIA_ROOT) / file_path
        if target.exists():
            target.unlink()
    except Exception:
        logger.warning("invoice_media_file_remove_failed", extra={"file_path": file_path}, exc_info=True)


# ── 冲红重开：只读查询（供 API 装配 reatch_group 用）────────────────────


def _group_item(invoice: Any, intake: Any) -> dict[str, Any]:
    """组内一段：票面事实一律优先取 ``Invoice``（真凭证），缺失才回落 intake。"""
    return {
        "intake_id": getattr(intake, "pk", None),
        "invoice_id": getattr(invoice, "pk", None),
        "invoice_number": str(getattr(invoice, "invoice_number", "") or getattr(intake, "invoice_number", "") or ""),
        "total_amount": (
            str(invoice.total_amount)
            if invoice is not None and getattr(invoice, "total_amount", None) is not None
            else (str(intake.total_amount) if intake is not None and intake.total_amount is not None else None)
        ),
    }


def _offset_invoice_of(intake: InvoiceIntake) -> Any:
    """被这张红票冲销的原 ``Invoice``（优先用落库的 FK，回落按票号现查）。

    回落分支是为历史数据：红票入池时扫描器还没写 ``offset_invoice``，
    先行重解析或人工重跑后才有。只查不写——写回属于扫描/裁定层的事。
    """
    from apps.contracts.models import Invoice

    if intake.offset_invoice_id:
        invoice = Invoice.objects.filter(pk=intake.offset_invoice_id).select_related("payment__contract", "contract")
        return invoice.first()
    number = str(str(getattr(intake, "red_against_number", "") or "") or "")
    if not number:
        return None
    return Invoice.objects.filter(invoice_number=number).select_related("payment__contract", "contract").first()


def _intake_of_invoice(invoice: Any) -> InvoiceIntake | None:
    """生成这张 ``Invoice`` 的那条 intake（用于组内 original 段的 intake_id）。"""
    if invoice is None:
        return None
    intake: InvoiceIntake | None = InvoiceIntake.objects.filter(invoice_id=invoice.pk).first()
    return intake


def _reissue_of(intake: InvoiceIntake) -> InvoiceIntake | None:
    """本组的重开蓝票：被这张红票 ``supersedes`` 的那条 intake。"""
    reissue: InvoiceIntake | None = InvoiceIntake.objects.filter(supersedes_intake_id=intake.pk).first()
    return reissue


def _red_intakes_for_reissues(reissue_rows: list[InvoiceIntake]) -> list[InvoiceIntake]:
    """给一批「重开蓝票」找出各自所属的红票（可能为空：红票还没到）。

    路径：重开票 → supersedes_intake（被替代的原票 intake）→ 其 invoice → 同号发票
    被哪张红票点名（``red_against_number``）。

    一次批量查完，不随行数增长：首页 50 行里可能有多组冲红重开。
    """
    from apps.contracts.models import Invoice, InvoiceIntakeStatus

    original_intake_ids = {intake.supersedes_intake_id for intake in reissue_rows if intake.supersedes_intake_id}
    if not original_intake_ids:
        return []

    # 原票 intake -> 它的发票号
    original_numbers = {
        str(number)
        for number in InvoiceIntake.objects.filter(pk__in=original_intake_ids).values_list(
            "invoice__invoice_number", flat=True
        )
        if number
    }
    if not original_numbers:
        return []

    # 同项目的红票（未确认的），其 red_against_number 命中上面的号
    project_codes = {
        str(code)
        for code in InvoiceIntake.objects.filter(pk__in=original_intake_ids).values_list("project_code", flat=True)
        if code
    }
    qs = InvoiceIntake.objects.filter(
        status=InvoiceIntakeStatus.PENDING,
        red_against_number__in=original_numbers,
    ).select_related("offset_invoice")
    if project_codes:
        qs = qs.filter(project_code__in=project_codes)
    return list(qs)


def red_group_facts(intakes: list[InvoiceIntake]) -> dict[int, dict[str, Any] | None]:
    """批量装配「冲红重开组」的**票面事实**，返回 ``{intake_id: group | None}``。

    为什么放在 Service 而不是 API：组的三段各要一次 ORM 查询（原票 / 生成原票的
    intake / 重开蓝票），API 层出现 ``Model.objects`` 会撞四层架构门禁（基线 0）。
    API 只做最后一步"事实 → 响应结构"的改名装配。

    组只按 ``group_key`` 语义给出三段，**不判断该不该折叠**——那是前端的事：

    - ``original`` 原蓝票（可能不在库 → ``None``）
    - ``red``      红票本身；只要 ``is_red`` 成立就一定有这一段
    - ``reissue``  重开蓝票（只有"冲红并重开"才落，可能 ``None``）

    非红票且在库无对应记录的 intake 返回 ``None``（扁平列表里的普通行）。
    """
    groups: dict[int, dict[str, Any] | None] = {intake.pk: None for intake in intakes}
    red_intakes = [intake for intake in intakes if getattr(intake, "is_red", False)]
    if not red_intakes:
        pass

    # 重开票自己不是红票，单独看它算不出组。详情端点只传来这一张时必须
    # **从它反查所属红票**，否则同一张重开票在列表里有组、进详情就没组，
    # 弹窗里「冲红重开」的三段信息凭空消失。
    reissue_rows = [
        intake for intake in intakes if not getattr(intake, "is_red", False) and intake.supersedes_intake_id
    ]
    if reissue_rows:
        red_intakes = [*red_intakes, *_red_intakes_for_reissues(reissue_rows)]
    _red_intakes_dedup = {intake.pk: intake for intake in red_intakes}
    red_intakes = list(_red_intakes_dedup.values())

    if not red_intakes:
        return groups

    # 原票 / 重开票一次性批量取，避免首页 50 行退化成 150 次查询
    offset_ids = {intake.offset_invoice_id for intake in red_intakes if intake.offset_invoice_id}
    offset_numbers = {
        str(intake.red_against_number)
        for intake in red_intakes
        if not intake.offset_invoice_id and str(getattr(intake, "red_against_number", "") or "")
    }
    from apps.contracts.models import Invoice

    offset_by_id = {invoice.pk: invoice for invoice in Invoice.objects.filter(pk__in=offset_ids)}
    offset_by_number = {
        str(invoice.invoice_number): invoice for invoice in Invoice.objects.filter(invoice_number__in=offset_numbers)
    }
    # 重开蓝票的查找**不能**限定在本批 intakes 里。
    #
    # 真实样本：原票（intake #13）早已确认 -> 不在 pending 列表里；重开蓝票
    # ``supersedes_intake`` 指向的是那张**已确认的** 原票 intake。若按
    # ``supersedes_intake_id__in=<本批 pending ids>`` 过滤，就永远匹配不到，
    # 冲红重开组永远拼不起来（实测：红票显示正常但组卡片为空）。
    #
    # 正确口径：先定「原票」，再找「替代了这张原票」的那条待认领 intake。
    offset_intakes = {
        intake.invoice_id: intake
        for intake in InvoiceIntake.objects.filter(invoice_id__in=[inv.pk for inv in offset_by_id.values()])
    }
    # 原票 intake 的 id 集合 -> 用它反查重开票（一次批量，不随行数增长）
    original_intake_ids = {i.pk for i in offset_intakes.values() if i is not None}
    reissue_by_original_intake_id: dict[int, InvoiceIntake] = {}
    if original_intake_ids:
        for candidate in InvoiceIntake.objects.filter(supersedes_intake_id__in=original_intake_ids).order_by("-id"):
            reissue_by_original_intake_id.setdefault(int(candidate.supersedes_intake_id or 0), candidate)

    for red in red_intakes:
        offset = (
            offset_by_id.get(red.offset_invoice_id)
            if red.offset_invoice_id
            else offset_by_number.get(str(red.red_against_number))
        )
        original_intake = offset_intakes.get(offset.pk) if offset is not None else None
        reissue = reissue_by_original_intake_id.get(original_intake.pk) if original_intake is not None else None
        group = {
            "group_key": f"red:{red.red_against_number}",
            "original": _group_item(offset, original_intake) if offset is not None else None,
            "red": _group_item(None, red),
            "reissue": _group_item(None, reissue) if reissue is not None else None,
        }
        # 组事实必须同时发给**组内每一个成员**，不能只给红票。
        #
        # 前端按 ``reatch_group.group_key`` 折叠：只给红票时，重开蓝票自己对不上
        # 任何组，会被当成一条独立行渲染——用户看到“组卡片 + 一条重复的新票”。
        # 实测就是这个现象（#19 既在组里、又单独占一行）。
        groups[red.pk] = group
        if reissue is not None and reissue.pk in groups:
            groups[reissue.pk] = group
    return groups


@transaction.atomic
def reparse_invoice_intake(*, intake_id: int, user: Any) -> InvoiceIntake:
    """重解析单条待认领发票，把票面事实（含红票两个字段）写回 intake。

    用于历史脏数据修复：红票在解析层支持负号之前入池，``total_amount`` 是
    NULL，UI 上就无法判断该冲多少——只有补上金额，"冲红并重新开具"的主按钮
    才敢放行（金额未知时冲红会让账目 ``Sum`` 少一笔负数）。

    只补**空字段**（``None`` / 空串），绝不覆盖人工/前次识别已有的事实。

    ⚠️ 必须自带 ``@transaction.atomic``：函数内用了 ``select_for_update()``，
    没有事务包裹时 Django 会直接抛 ``TransactionManagementError``——
    调用方（API 端点）不会替它开事务，实测在修复历史脏数据时一调就炸。
    """
    from apps.core.exceptions import NotFoundError
    from apps.invoice_recognition.services.invoice_parser import InvoiceParser
    from apps.message_hub.services.base import resolve_media_attachment_path

    intake = InvoiceIntake.objects.select_for_update().filter(pk=intake_id).first()
    if intake is None or not can_decide(user, intake):
        raise NotFoundError(f"待认领发票 {intake_id} 不存在")

    path = resolve_media_attachment_path(intake.attachment_path)
    if path is None:
        from apps.core.exceptions import ValidationException

        raise ValidationException(
            message="发票附件已不在磁盘上，无法重解析，请从邮件原文重新下载后手动上传", code="INVOICE_FILE_MISSING"
        )

    import pdfplumber

    with pdfplumber.open(str(path)) as pdf:
        text = "\n".join((page.extract_text() or "") for page in pdf.pages)
    if not text.strip():
        from apps.core.exceptions import ValidationException

        raise ValidationException(message="该 PDF 抽不出文本，无法重解析", code="INVOICE_PDF_NO_TEXT")
    parsed = InvoiceParser().parse(text)

    updates: dict[str, Any] = {}
    if not intake.invoice_number and parsed.invoice_number:
        updates["invoice_number"] = parsed.invoice_number[:32]
    if intake.invoice_date is None and parsed.invoice_date is not None:
        updates["invoice_date"] = parsed.invoice_date
    if intake.total_amount is None and parsed.total_amount is not None:
        updates["total_amount"] = parsed.total_amount
    if not intake.buyer_name and parsed.buyer_name:
        updates["buyer_name"] = parsed.buyer_name[:120]
    if not intake.project_code and parsed.project_code:
        updates["project_code"] = parsed.project_code[:32]
    if not intake.remark and parsed.remark:
        updates["remark"] = parsed.remark
    if not intake.red_against_number and str(getattr(parsed, "red_against_number", "") or ""):
        updates["red_against_number"] = parsed.red_against_number
    if not intake.red_confirmation_no and str(getattr(parsed, "red_confirmation_no", "") or ""):
        updates["red_confirmation_no"] = parsed.red_confirmation_no

    if updates:
        updates["updated_at"] = timezone.now()
        InvoiceIntake.objects.filter(pk=intake.pk).update(**updates)
        intake.refresh_from_db()

    # 重解析之后**必须重算派生结果**，只改票面字段等于“数字变了、结论没变”：
    #   ① payment_pick 快照是扫描那一刻算的（红票当时金额为 NULL →
    #      `_amounts_match(None)` 恒 False → 被写成「金额与收款不符」，
    #      而真实原因是“根本没识别出来”，提示指错了方向）；
    #   ② 红票→原票的 offset_invoice 与「重开蓝票→被替代 intake」的配对
    #      也依赖票面事实，不重算的话首页永远分不出冲红重开组。
    _refresh_after_reparse(intake)

    logger.info("invoice_intake_reparsed", extra={"intake_id": intake.pk, "fields": sorted(updates)})
    return intake


def _refresh_after_reparse(intake: InvoiceIntake) -> None:
    """重解析后的派生重算：offset 指向、配对、以及红票的收款预选快照。

    全部幂等：同日重跑得到同一结果，不会把台账写成两套。
    """
    from apps.contracts.models import Invoice
    from apps.contracts.services.payment.invoice_intake_scanner import refresh_red_links
    from apps.contracts.services.payment.invoice_match import choose_payment

    # ① offset_invoice：红票票面印的被冲票号，若本库有同号发票则绑定
    if intake.red_against_number and intake.offset_invoice_id is None:
        offset = Invoice.objects.filter(invoice_number=intake.red_against_number).select_related("payment").first()
        if offset is not None:
            InvoiceIntake.objects.filter(pk=intake.pk).update(offset_invoice=offset)
            intake.refresh_from_db()

    # ② 红票的收款预选快照重算（蓝票保持扫描时的结论不动——“重解析”只修票面失败的东西）
    if intake.is_red:
        snapshot = dict(intake.match_snapshot or {})
        contract_id = intake.suggested_contract_id
        if contract_id is not None:
            snapshot["payment_pick"] = choose_payment(
                contract_id=int(contract_id),
                total_amount=intake.total_amount,
                invoice_date=intake.invoice_date,
                is_red=True,
                red_against_number=intake.red_against_number,
                red_offset_found=intake.offset_invoice_id is not None,
            )
            InvoiceIntake.objects.filter(pk=intake.pk).update(match_snapshot=snapshot)
            intake.refresh_from_db()

    # ③ 配对：红票与重开蓝票都得参与一次，否则组卡片永远拼不起来
    if intake.project_code:
        refresh_red_links(intake.project_code)
