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
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.contracts.models import InvoiceIntake, InvoiceIntakeStatus

logger = logging.getLogger("apps.contracts")

__all__ = ["confirm_invoice_intake", "reject_invoice_intake", "reopen_invoice_intake", "open_count"]


def _is_admin(user: Any) -> bool:
    return bool(getattr(user, "is_admin", False) or getattr(user, "is_superuser", False))


def open_count(user: Any) -> int:
    """首页角标：与我相关的待认领发票数。"""
    return visible_intakes_qs(user).filter(status=InvoiceIntakeStatus.PENDING).count()


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
    """
    from apps.core.exceptions import NotFoundError, ValidationException

    intake = InvoiceIntake.objects.select_for_update().filter(pk=intake_id).first()
    if intake is None or not can_decide(user, intake):
        raise NotFoundError(f"待认领发票 {intake_id} 不存在")
    if intake.status == InvoiceIntakeStatus.PENDING:
        raise ValidationException("该发票已经是待确认状态", code="INVOICE_INTAKE_ALREADY_PENDING")

    if intake.invoice_id is not None:
        _remove_generated_invoice(intake, user)

    intake.status = InvoiceIntakeStatus.PENDING
    intake.confirmed_contract = None
    intake.confirmed_payment = None
    intake.confirmed_by = None
    intake.confirmed_at = None
    intake.invoice = None
    intake.save(
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
    return intake


def _remove_generated_invoice(intake: InvoiceIntake, user: Any) -> None:
    """删掉确认时生成的发票（含文件夹副本与 media 文件）。"""
    from apps.contracts.models import Invoice

    invoice = Invoice.objects.filter(pk=intake.invoice_id).first()
    if invoice is None:
        return

    contract_id = invoice.contract_id or (invoice.payment.contract_id if invoice.payment_id else None)
    payment = invoice.payment if invoice.payment_id else None
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
