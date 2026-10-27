"""发票落库：识别结果 + 原始文件 + Invoice 记录，一次事务完成。

**为什么不用 InvoiceUploadService.save_invoice_file 直接建记录**：那个方法是
「存文件 + 建记录」的 admin 写入原语（文件先落库、字段由表单另存），
本服务是「拖一张发票进来」的完整链路：识别 → 命名 → 落盘 → 记账 → 回填开票金额，
任何一步失败都必须整体回滚，不能留下「有文件没记录」或「记录指向不存在的文件」。

存储组织分两段，各自解决不同的检索需求：

1. **media 仓库**（`contracts/invoices/{payment_id}/`）：权威副本，
   `Invoice.file_path` 指向它，前端预览/下载走这里（带下载票据鉴权）。
2. **合同文件夹**（绑定目录下的 `发票/日期_销售方_金额.pdf`）：律师在 Finder 里
   翻合同目录时能直接看到发票原件。命名带日期/销售方/金额，是为了让同一个目录里
   几十张发票天然按时间排好、一眼看出是谁开的。

第二段是「锦上添花」：合同未绑定文件夹 / 云存储绑定 / 目录不可达时静默跳过并
在返回值里说明原因，不影响开票记账本身。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.db import transaction

from apps.core.exceptions import ValidationException

logger = logging.getLogger("apps.contracts")

__all__ = ["InvoiceFileService", "SavedInvoice"]


@dataclass(frozen=True)
class SavedInvoice:
    """一张发票的落库结果（API 层直接映射成响应，不再二次查询）。"""

    id: int
    original_filename: str
    stored_filename: str
    file_path: str
    file_url: str
    invoice_code: str
    invoice_number: str
    invoice_date: date | None
    amount: Decimal | None
    tax_amount: Decimal | None
    total_amount: Decimal | None
    seller_name: str
    buyer_name: str
    #: 是否按「同号发票已存在」判为重复（重复时**不**重复计开票金额）
    duplicated: bool
    #: 合同文件夹里落到的相对路径（未落则空串）
    folder_subpath: str = ""
    #: 落文件夹被跳过/失败的原因（空串 = 没跳过）
    folder_skipped_reason: str = ""


class InvoiceFileService:
    """把识别后的发票文件与结构化字段一次性写进某条收款记录。"""

    ALLOWED_EXTENSIONS: tuple[str, ...] = (".pdf", ".jpg", ".jpeg", ".png")
    MAX_SIZE_BYTES = 20 * 1024 * 1024
    #: 合同文件夹下的发票子目录名（中文名让律师一眼看懂）
    FOLDER_NAME = "发票"
    _ILLEGAL_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

    # ------------------------------------------------------------------ 写

    @transaction.atomic
    def save_invoice(
        self,
        *,
        payment_id: int,
        uploaded_file: Any,
        parsed: Any | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
        to_contract_folder: bool = True,
    ) -> SavedInvoice:
        """保存一张发票并回填收款的开票金额。

        `parsed` 是 invoice_recognition 的 ``ParsedInvoice``（可为 None：纯上传不识别）。
        识别字段只作为**建议值**写入，律师可在前端改动后再提交。
        """
        from apps.contracts.admin.wiring_admin import get_invoice_upload_service
        from apps.contracts.models import Invoice

        payment = self._load_payment(payment_id, user=user, org_access=org_access, perm_open_access=perm_open_access)
        self._validate_file(uploaded_file)

        # InvoiceUploadService.save_invoice_file 返回的是**已建好的 Invoice 对象**
        # （它内部就做了 Invoice.objects.create）。这里只能拿它补识别字段，
        # 再自己 create 一次会撞上 uniq_invoice_payment_file_path 并产生孤儿记录。
        invoice = get_invoice_upload_service().save_invoice_file(uploaded_file, payment_id)
        file_path = invoice.file_path
        original_filename = invoice.original_filename

        seller = str(getattr(parsed, "seller_name", "") or "")
        buyer = str(getattr(parsed, "buyer_name", "") or "")
        inv_date = self._as_date(getattr(parsed, "invoice_date", None))
        amount = self._as_decimal(getattr(parsed, "amount", None))
        tax_amount = self._as_decimal(getattr(parsed, "tax_amount", None))
        total_amount = self._as_decimal(getattr(parsed, "total_amount", None))
        number = str(getattr(parsed, "invoice_number", "") or "")
        code = str(getattr(parsed, "invoice_code", "") or "")

        duplicated = (
            bool(number)
            and Invoice.objects.filter(payment__contract_id=payment.contract_id, invoice_number=number).exists()
        )

        # 识别字段回填到刚建的那条 Invoice（只写回有值的字段，不覆盖上传原值）
        invoice.invoice_code = code
        invoice.invoice_number = number
        invoice.invoice_date = inv_date
        invoice.amount = amount
        invoice.tax_amount = tax_amount
        invoice.total_amount = total_amount
        invoice.save(
            update_fields=[
                "invoice_code",
                "invoice_number",
                "invoice_date",
                "amount",
                "tax_amount",
                "total_amount",
            ]
        )

        if total_amount is not None and not duplicated:
            self._recompute_invoiced_amount(payment)

        folder_subpath, skipped = "", ""
        if to_contract_folder:
            folder_subpath, skipped = self._mirror_to_contract_folder(
                contract_id=payment.contract_id,
                invoice=invoice,
                amount=total_amount,
                seller=seller,
                inv_date=inv_date,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
            )

        return SavedInvoice(
            id=invoice.id,
            original_filename=original_filename,
            stored_filename=self.display_filename(
                amount=total_amount, seller=seller, inv_date=inv_date, ext=self._ext(file_path)
            ),
            file_path=file_path,
            file_url=f"{self._media_url()}{file_path}",
            invoice_code=code,
            invoice_number=number,
            invoice_date=inv_date,
            amount=amount,
            tax_amount=tax_amount,
            total_amount=total_amount,
            seller_name=seller,
            buyer_name=buyer,
            duplicated=duplicated,
            folder_subpath=folder_subpath,
            folder_skipped_reason=skipped,
        )

    def list_invoices(self, contract_id: int, *, payment_ids: list[int] | None = None) -> list[Any]:
        """合同（或其下若干收款）的发票，uploaded_at 倒序扁平列表。"""
        from apps.contracts.models import Invoice

        qs = Invoice.objects.filter(payment__contract_id=contract_id).select_related("payment")
        if payment_ids:
            qs = qs.filter(payment_id__in=payment_ids)
        return list(qs.order_by("-uploaded_at", "-id"))

    @transaction.atomic
    def delete_invoice(
        self,
        *,
        invoice_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, bool]:
        """删除发票（记录 + media 文件），并重算开票金额。

        合同文件夹里的副本**不删**：那是律师本地工作目录里的文件，系统不该在他
        不知情时删掉本地磁盘内容（与删除=移入 `_已删除` 的宽松口径一致）。
        """
        from apps.contracts.admin.wiring_admin import get_invoice_upload_service
        from apps.contracts.models import Invoice
        from apps.core.exceptions import NotFoundError

        try:
            invoice = Invoice.objects.select_related("payment").get(pk=invoice_id)
        except Invoice.DoesNotExist:
            raise NotFoundError(message="发票不存在", code="INVOICE_NOT_FOUND") from None

        payment = self._load_payment(
            invoice.payment_id, user=user, org_access=org_access, perm_open_access=perm_open_access
        )
        get_invoice_upload_service().delete_invoice(invoice.id)
        self._recompute_invoiced_amount(payment)
        return {"success": True}

    # ------------------------------------------------------------------ 内部

    def _load_payment(
        self,
        payment_id: int,
        *,
        user: Any | None,
        org_access: dict[str, Any] | None,
        perm_open_access: bool,
    ) -> Any:
        """取收款并做**合同行级**鉴权（发票跟着收款走，鉴权口径必须与收款一致）。"""
        from apps.contracts.models import ContractPayment
        from apps.contracts.services.contract.domain.access_policy import ContractAccessPolicy
        from apps.core.exceptions import NotFoundError

        try:
            payment = ContractPayment.objects.select_related("contract").get(pk=payment_id)
        except ContractPayment.DoesNotExist:
            raise NotFoundError(message="收款记录不存在", code="PAYMENT_NOT_FOUND") from None

        ContractAccessPolicy().ensure_access(
            contract_id=payment.contract_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )
        return payment

    def _validate_file(self, uploaded_file: Any) -> None:
        name = str(getattr(uploaded_file, "name", "") or "")
        ext = self._ext(name)
        if ext not in self.ALLOWED_EXTENSIONS:
            raise ValidationException(
                message=f"不支持的发票格式：{ext or name}",
                code="INVOICE_FILE_TYPE",
                errors={"file": f"仅支持 {'/'.join(self.ALLOWED_EXTENSIONS)}"},
            )
        size = int(getattr(uploaded_file, "size", 0) or 0)
        if size > self.MAX_SIZE_BYTES:
            raise ValidationException(
                message=f"发票文件超过 {self.MAX_SIZE_BYTES // (1024 * 1024)}MB",
                code="INVOICE_FILE_TOO_LARGE",
                errors={"file": "文件过大"},
            )

    def _recompute_invoiced_amount(self, payment: Any) -> None:
        """按发票合计**全量重算** invoiced_amount 与开票状态（不越过收款金额上限）。

        全量重算而不是增量累加：增删任一发票都能得到同一个正确答案；增量法在并发
        上传两张时会各自基于旧值相加，最终多算一次。
        """
        from django.db.models import Sum

        from apps.contracts.models import Invoice, InvoiceStatus

        total = Invoice.objects.filter(payment_id=payment.id).aggregate(s=Sum("total_amount"))["s"]
        invoiced = Decimal(str(total)) if total is not None else Decimal("0")
        payment_amount = Decimal(str(payment.amount))
        # 开票金额不得超过收款金额（模型约束 chk_contractpayment_invoiced_le_amount）
        invoiced = min(invoiced, payment_amount)

        if invoiced == 0:
            status = InvoiceStatus.UNINVOICED
        elif invoiced < payment_amount:
            status = InvoiceStatus.INVOICED_PARTIAL
        else:
            status = InvoiceStatus.INVOICED_FULL

        payment.invoiced_amount = invoiced
        payment.invoice_status = status
        payment.save(update_fields=["invoiced_amount", "invoice_status", "updated_at"])

    def _mirror_to_contract_folder(
        self,
        *,
        contract_id: int,
        invoice: Any,
        amount: Decimal | None,
        seller: str,
        inv_date: date | None,
        user: Any | None,
        org_access: dict[str, Any] | None,
        perm_open_access: bool,
    ) -> tuple[str, str]:
        """把发票复制到合同绑定文件夹的 `发票/` 下（失败只记录原因，不抛）。"""
        from apps.contracts.services.contract.integrations.folder_browse_service import ContractFolderBrowseService

        service = ContractFolderBrowseService()
        access = {
            "user": user,
            "org_access": org_access,
            "perm_open_access": perm_open_access,
        }

        try:
            root = service.list_entries(owner_id=contract_id, subpath="", **access)
        except Exception as exc:  # 未绑定 / 云存储 / 目录不可达：都不是开票失败
            logger.info("invoice_folder_mirror_skipped", extra={"contract_id": contract_id, "reason": str(exc)})
            return "", self._skip_reason(exc)

        if not any(f.get("name") == self.FOLDER_NAME for f in (root.get("folders") or [])):
            try:
                service.mkdir(owner_id=contract_id, subpath="", name=self.FOLDER_NAME, **access)
            except Exception as exc:
                # 并发下另一张发票已建好同名目录 → 视为已存在，继续写文件
                logger.info("invoice_folder_mkdir_skipped", extra={"reason": str(exc)})

        display_name = self.display_filename(
            amount=amount, seller=seller, inv_date=inv_date, ext=self._ext(invoice.file_path)
        )
        try:
            saved = service.save_upload_bytes(
                owner_id=contract_id,
                subpath=self.FOLDER_NAME,
                filename=display_name,
                data=Path(self._media_abs(invoice.file_path)).read_bytes(),
                **access,
            )
        except Exception as exc:
            logger.warning("invoice_folder_mirror_failed", exc_info=True)
            return "", self._skip_reason(exc)

        return str(saved.get("subpath") or ""), ""

    def display_filename(self, *, amount: Decimal | None, seller: str, inv_date: date | None, ext: str) -> str:
        """`20260915_广东省中山市香山公证处_100000元.pdf`：日期在前 → 目录天然按时间排。"""
        parts: list[str] = []
        if inv_date:
            parts.append(inv_date.strftime("%Y%m%d"))
        if seller:
            parts.append(self._safe_part(seller, limit=40))
        if amount is not None:
            parts.append(self._short_amount(amount) + "元")
        stem = "_".join(p for p in parts if p) or "发票"
        return f"{stem}{ext or '.pdf'}"

    @staticmethod
    def _short_amount(amount: Decimal) -> str:
        """100000.00 → 100000；1234.50 → 1234.5（文件名不需要补零）。"""
        text = format(amount.normalize(), "f")
        return text.rstrip("0").rstrip(".") if "." in text else text

    @classmethod
    def _safe_part(cls, raw: str, *, limit: int) -> str:
        cleaned = cls._ILLEGAL_NAME_CHARS.sub("", raw).strip(" .")
        return cleaned[:limit] or ""

    @staticmethod
    def _ext(name: str) -> str:
        idx = name.rfind(".")
        return name[idx:].lower() if idx >= 0 else ""

    @staticmethod
    def _as_decimal(value: Any) -> Decimal | None:
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value)).quantize(Decimal("0.01"))
        except Exception:
            return None

    @staticmethod
    def _as_date(value: Any) -> date | None:
        if isinstance(value, date):
            return value
        if isinstance(value, str) and value.strip():
            from django.utils.dateparse import parse_date

            return parse_date(value.strip()[:10])
        return None

    @staticmethod
    def _skip_reason(exc: Exception) -> str:
        return str(getattr(exc, "message", "") or exc or "无法写入合同文件夹")

    @staticmethod
    def _media_url() -> str:
        from django.conf import settings

        return str(settings.MEDIA_URL)

    @staticmethod
    def _media_abs(rel_path: str) -> str:
        from django.conf import settings

        return str(Path(settings.MEDIA_ROOT) / rel_path)
