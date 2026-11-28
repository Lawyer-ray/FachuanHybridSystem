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
from pathlib import Path
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.contracts.models import InvoiceIntake, InvoiceIntakeStatus

# 以下四个模块承载本模块已搬出的实现，这里**只做再导出**：既有调用方与测试
# （apps/contracts/api/invoice_intake_api.py、tests/ci/unit/contracts/…）仍按
# ``invoice_intake_service.<name>`` 引用这些名字，import 路径不变。
# 依赖方向单向：原模块 → 新模块，新模块不许 import 回本模块。
from apps.contracts.services.payment.invoice_folder_cleanup import (
    _remove_folder_copy,
    _remove_generated_invoice,
    _remove_media_file,
    _restore_invoice_folder_position,
)
from apps.contracts.services.payment.invoice_intake_audit import _log_finance
from apps.contracts.services.payment.invoice_intake_facts import (
    _group_item,
    _is_admin,
    _red_intakes_for_reissues,
    can_decide,
    generated_invoice_facts,
    get_intake_for_user,
    open_count,
    red_group_facts,
    visible_intakes_qs,
)
from apps.contracts.services.payment.invoice_red_guards import (
    RED_AMOUNT_TOLERANCE,
    _contract_of_invoice,
    _ensure_not_red,
    _invoice_is_red,
    _red_guard_amount,
    _red_guards,
    _reissue_guards,
    _resolve_payment_for_red,
)

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
        # ``supersedes_intake`` 指向**被替代的原票 intake**，不是红票。
        #
        # 全链路只有这一个语义（扫描层 ``_find_supersede_target`` 找的是被红票点名的
        # 已确认原票；装配层 ``red_group_facts`` 也按原票 intake 反查重开票）。
        # 曾写成 ``= red.pk``（指向红票），后果是：确认后装配层按原票查不到这条
        # 重开票 → 组卡片缺 reissue 段；而一个项目里如果**不只一组**冲红重开，
        # 按红票去配还会把别的组的重开票错配进本组。
        new.supersedes_intake_id = _original_intake_id_of(red)
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
            {
                "invoice_id": saved_new.id if saved_new else None,
                "supersedes_intake_id": new.supersedes_intake_id,
            },
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


def _original_intake_id_of(red: Any) -> int | None:
    """红票所冲的那张原票对应的 intake id（找不到返回 ``None``）。

    路径：红票 ``offset_invoice``（已入账的原票发票）→ 生成该发票的 intake。
    这条链路是“重开票替代了谁”的唯一可靠来源：原票可能早已确认，不在 pending 里。
    """
    if getattr(red, "offset_invoice_id", None) is None:
        return None
    owner = InvoiceIntake.objects.filter(invoice_id=red.offset_invoice_id).values_list("pk", flat=True).first()
    return int(owner) if owner is not None else None


def _red_group_of(intake: InvoiceIntake) -> dict[str, Any] | None:
    """这条 intake 属于哪个冲红重开组（不在组里则 ``None``）。

    组用 ``supersedes_intake`` 串起，语义统一为「重开蓝票 → 被替代的**原票 intake**」
    （与扫描层 ``_find_supersede_target``、装配层 ``red_group_facts`` 同一口径）。

    两端都要能成组，否则「从哪一端点撤销」会得到不同结果：

    - 从**重开蓝票**点：``supersedes_intake`` 指向原票，要靠原票找红票；
    - 从**红票**点：要找到把原票标为被替代的那条重开票。

    原票 intake 本身不自己成组：它只是组内要被恢复的那一端（它的撤销走普通路径，
    否则「撤销原票」会连带删掉另外两张与它无关的票）。
    """
    # 情形一：intake 自己是重开蓝票（supersedes 指向原票 **intake**）
    if intake.supersedes_intake_id:
        # 先把「原票 intake」换成「原票 Invoice」——红票只认 offset_invoice（Invoice FK），
        # 两个字段类型不同，直接拿 intake id 去比 Invoice id 会拿错票。
        original_invoice_id = (
            InvoiceIntake.objects.filter(pk=intake.supersedes_intake_id).values_list("invoice_id", flat=True).first()
        )
        if original_invoice_id is not None:
            red = InvoiceIntake.objects.filter(offset_invoice_id=original_invoice_id).exclude(pk=intake.pk).first()
            if red is not None:
                return {"red": red, "reissue": intake}

    # 情形二：intake 自己是红票（看有没有重开票把它的原票标为被替代）
    original_id = _original_intake_id_of(intake)
    if original_id is not None:
        reissue = InvoiceIntake.objects.filter(supersedes_intake_id=original_id).exclude(pk=intake.pk).first()
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
        # ``supersedes_intake`` **不能清**：撤销的是“确认”这个动作，不是“这两张票
        # 有替代关系”这个事实。清掉之后两票都回到 pending，却失去了配对，
        # 首页会从「一张冲红重开组卡片」退化成「红票一行 + 新票一行」
        # （重开票还会被当成普通待办，再点一次就多开一张）。
        reissue.status = InvoiceIntakeStatus.PENDING
        reissue.confirmed_contract = None
        reissue.confirmed_payment = None
        reissue.confirmed_by = None
        reissue.confirmed_at = None
        reissue.save(
            update_fields=[
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


def _reset_intake_to_pending(intake: InvoiceIntake) -> None:
    """把 intake 的裁定结果清空（不动 ``supersedes_intake``，调用方按需处理）。"""
    intake.status = InvoiceIntakeStatus.PENDING
    intake.confirmed_contract = None
    intake.confirmed_payment = None
    intake.confirmed_by = None
    intake.confirmed_at = None
    intake.invoice = None


# ── 冲红重开：只读查询（供 API 装配 reatch_group 用）────────────────────


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
