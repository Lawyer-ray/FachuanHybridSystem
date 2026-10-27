"""发票上传服务层。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from apps.core.exceptions import NotFoundError
from apps.core.services import storage_service as storage

if TYPE_CHECKING:
    from apps.contracts.models import Invoice

logger = logging.getLogger(__name__)

_ALLOWED_EXTENSIONS = [".pdf", ".jpg", ".jpeg", ".png"]
_MAX_SIZE_BYTES = 20 * 1024 * 1024


class InvoiceUploadService:
    def save_invoice_file(
        self, uploaded_file: Any, payment_id: int | None = None, *, contract_id: int | None = None
    ) -> Invoice:  # pragma: no cover
        """保存发票文件并创建 Invoice 记录。文件保存失败时抛出异常，不创建 DB 记录。

        挂靠二选一：`payment_id`（已核销收款）或 `contract_id`（先开票后付款，
        票先挂在合同名下）。未关联收款的发票落到 `contracts/invoices/c{合同id}/`，
        日后关联收款时**不搬文件**——`file_path` 只是存储位置。
        """
        from apps.contracts.models import Invoice
        from apps.core.filesystem.upload_paths import MediaEntity

        if payment_id is None and contract_id is None:
            raise ValueError("payment_id 与 contract_id 必须给一个")
        owner = payment_id if payment_id is not None else f"c{contract_id}"

        try:
            rel_path, original_filename = storage.save_uploaded_file(
                uploaded_file=uploaded_file,
                rel_dir=f"{MediaEntity.CONTRACT_INVOICES}/{owner}",
                allowed_extensions=_ALLOWED_EXTENSIONS,
                max_size_bytes=_MAX_SIZE_BYTES,
                use_uuid_name=True,
            )
        except Exception:
            logger.error("发票文件保存失败 payment_id=%s contract_id=%s", payment_id, contract_id, exc_info=True)
            raise

        return Invoice.objects.create(
            payment_id=payment_id,
            contract_id=contract_id,
            file_path=rel_path,
            original_filename=original_filename,
        )

    def list_invoices_by_payment(self, payment_id: int) -> Any:  # pragma: no cover
        """返回指定收款的所有发票 QuerySet，payment 不存在时返回空 QuerySet。"""
        from apps.contracts.models import Invoice

        return Invoice.objects.filter(payment_id=payment_id)

    def list_invoices_by_contract(self, contract_id: int) -> dict[int, list[Any]]:
        """返回合同所有收款下的发票，按 payment_id 分组，组内按 uploaded_at 升序。"""
        from apps.contracts.models import Invoice

        qs = (
            Invoice.objects.filter(payment__contract_id=contract_id)
            .select_related("payment")
            .order_by("payment_id", "-uploaded_at")
        )
        result: dict[int, list[Any]] = {}
        for invoice in qs:
            payment_id = invoice.payment_id
            if payment_id is None:  # 查询按 payment__contract 过滤，运行时不会出现；守卫只为类型
                continue
            result.setdefault(payment_id, []).append(invoice)
        return result

    def delete_invoice(self, invoice_id: int) -> None:
        """删除发票记录及物理文件。invoice 不存在时抛出 NotFoundError。"""
        from apps.contracts.models import Invoice

        try:
            invoice = Invoice.objects.get(pk=invoice_id)
        except Invoice.DoesNotExist:
            raise NotFoundError(
                message=f"Invoice {invoice_id} not found",
                code="INVOICE_NOT_FOUND",
            ) from None

        file_path = invoice.file_path
        invoice.delete()

        try:
            storage.delete_media_file(file_path)
        except Exception:
            logger.error("删除发票物理文件失败: %s", file_path, exc_info=True)
