"""撤销/重开的文件与文件夹清理：media 权威副本、合同文件夹副本、``已冲红/`` 位置。

## 为什么这里的 try/except 是刻意的

清理对象活在系统之外：媒体目录可能被手工搬走、合同文件夹可能已解绑或位于云存储、
权限可能不足。这些失败**不该让撤销失败**——撤回账务事实是主流程，文件位置是它的影子。
所以每条清理都是“失败只记 warning、不阻断”，用户仍能从 warning 里拿到手工去删的线索
（判定标准：这次失败会让用户看到一个无法解释的结果 → warning 以上）。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from apps.contracts.models import InvoiceIntake
from apps.contracts.services.payment.invoice_intake_audit import _log_finance

logger = logging.getLogger("apps.contracts")


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
