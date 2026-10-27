"""发票落库：识别结果 + 原始文件 + Invoice 记录，一次事务完成。

**为什么不用 InvoiceUploadService.save_invoice_file 直接建记录**：那个方法是
「存文件 + 建记录」的 admin 写入原语（文件先落库、字段由表单另存），
本服务是「拖一张发票进来」的完整链路：识别 → 命名 → 落盘 → 记账 → 回填开票金额，
任何一步失败都必须整体回滚，不能留下「有文件没记录」或「记录指向不存在的文件」。

存储组织分两段，各自解决不同的检索需求：

1. **media 仓库**（`contracts/invoices/{payment_id}/`，未关联收款的挂
   `contracts/invoices/c{contract_id}/`）：权威副本，`Invoice.file_path` 指向它，
   前端预览/下载走这里（带下载票据鉴权）。
2. **合同文件夹**（绑定目录下发票目录里的 `发票（合同名称）_YYYYMMDD开具.pdf`）：
   律师在 Finder 里翻合同目录时能直接看到发票原件。命名沿用律所既有手工习惯
   （`发票（佛山市某某公司执行某某公司买卖合同纠纷一案）_20261016开具.pdf`，
   括号里是合同/案件名称——律师按案找票，名称是检索键），日期在后让同目录
   几十张票天然按时间排好。发票目录不固定在顶层——律所模板多为 `1-律师资料/3-发票`，
   所以先在两层内找名字以「发票」结尾的目录，找不到再在顶层建 `发票/`。

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
from django.db.models import Q

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
    #: 括号命名用的合同名称（响应重算 display_filename 时免二次查库）
    contract_name: str = ""
    #: 合同文件夹里落到的相对路径（未落则空串）
    folder_subpath: str = ""
    #: 落文件夹被跳过/失败的原因（空串 = 没跳过）
    folder_skipped_reason: str = ""


# ── 模块级工具函数（原类内静态方法；Service 层禁用静态方法装饰器，纯函数一律下沉）──


def _contract_name(contract_id: int) -> str:
    """先开票路径取合同名称（鉴权已过，合同必然存在；名称即括号命名的素材）。"""
    from apps.contracts.models import Contract

    return str(Contract.objects.filter(pk=contract_id).values_list("name", flat=True).first() or "")


def _clip_utf8(text: str, *, max_bytes: int) -> str:
    """按 UTF-8 字节数截断（不切多字节字符中间）：macOS 文件名上限按字节计。"""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _sweep_stale_copies(temp_root: Path) -> None:
    """清扫 24 小时前留下的发票临时副本（落板文件要等用户粘贴，只能事后清）。"""
    import shutil
    import time

    cutoff = time.time() - 24 * 3600
    for old in temp_root.glob("fachuan-invoice-*"):
        try:
            if old.stat().st_mtime < cutoff:
                shutil.rmtree(old, ignore_errors=True)
        except OSError:
            continue


def _access_policy() -> Any:
    from apps.contracts.services.contract.domain.access_policy import ContractAccessPolicy

    return ContractAccessPolicy


def _ext(name: str) -> str:
    idx = name.rfind(".")
    return name[idx:].lower() if idx >= 0 else ""


def _as_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except Exception:
        return None


def _as_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        from django.utils.dateparse import parse_date

        return parse_date(value.strip()[:10])
    return None


def _skip_reason(exc: Exception) -> str:
    return str(getattr(exc, "message", "") or exc or "无法写入合同文件夹")


def _media_url() -> str:
    from django.conf import settings

    return str(settings.MEDIA_URL)


def _media_abs(rel_path: str) -> str:
    from django.conf import settings

    return str(Path(settings.MEDIA_ROOT) / rel_path)


class InvoiceFileService:
    """发票落库：挂某条收款（先付款后开票）或挂合同（先开票后付款）。"""

    ALLOWED_EXTENSIONS: tuple[str, ...] = (".pdf", ".jpg", ".jpeg", ".png")
    MAX_SIZE_BYTES = 20 * 1024 * 1024
    #: 合同文件夹里发票目录的名字特征（`发票` / `3-发票` / `1-律师资料/3-发票`）
    FOLDER_NAME = "发票"
    _ILLEGAL_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

    # ------------------------------------------------------------------ 写

    @transaction.atomic
    def save_invoice(
        self,
        *,
        payment_id: int | None = None,
        contract_id: int | None = None,
        uploaded_file: Any,
        parsed: Any | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
        to_contract_folder: bool = True,
    ) -> SavedInvoice:
        """保存一张发票。挂靠二选一：

        - `payment_id`：直接核销到某笔收款（先付款后开票），保存后回填开票金额；
        - `contract_id`：**先开票后付款**——票先挂合同名下，不动任何收款的
          开票金额，等钱到账记收款后走 :meth:`attach_invoice` 关联。

        `parsed` 是 invoice_recognition 的 ``ParsedInvoice``（可为 None：纯上传不识别）。
        识别字段只作为**建议值**写入，律师可在前端改动后再提交。
        """
        from apps.contracts.admin.wiring_admin import get_invoice_upload_service
        from apps.contracts.models import Invoice

        if payment_id is not None:
            payment = self._load_payment(
                payment_id, user=user, org_access=org_access, perm_open_access=perm_open_access
            )
            contract_id = payment.contract_id
            contract_name = str(payment.contract.name or "")
        else:
            if contract_id is None:
                raise ValidationException(message="payment_id 与 contract_id 必须给一个", code="INVOICE_NO_OWNER")
            payment = None
            self.ensure_contract_access(
                contract_id, user=user, org_access=org_access, perm_open_access=perm_open_access
            )
            contract_name = _contract_name(contract_id)
        self._validate_file(uploaded_file)

        # InvoiceUploadService.save_invoice_file 返回的是**已建好的 Invoice 对象**
        # （它内部就做了 Invoice.objects.create）。这里只能拿它补识别字段，
        # 再自己 create 一次会撞上 uniq_invoice_payment_file_path 并产生孤儿记录。
        invoice = get_invoice_upload_service().save_invoice_file(
            uploaded_file, payment_id=payment_id, contract_id=None if payment_id is not None else contract_id
        )
        file_path = invoice.file_path
        original_filename = invoice.original_filename

        seller = str(getattr(parsed, "seller_name", "") or "")
        buyer = str(getattr(parsed, "buyer_name", "") or "")
        inv_date = _as_date(getattr(parsed, "invoice_date", None))
        amount = _as_decimal(getattr(parsed, "amount", None))
        tax_amount = _as_decimal(getattr(parsed, "tax_amount", None))
        total_amount = _as_decimal(getattr(parsed, "total_amount", None))
        number = str(getattr(parsed, "invoice_number", "") or "")
        code = str(getattr(parsed, "invoice_code", "") or "")

        duplicated = bool(number) and (
            Invoice.objects.filter(
                Q(payment__contract_id=contract_id, invoice_number=number)
                | Q(contract_id=contract_id, invoice_number=number)
            ).exists()
        )

        # 识别字段回填到刚建的那条 Invoice（只写回有值的字段，不覆盖上传原值）
        invoice.invoice_code = code
        invoice.invoice_number = number
        invoice.invoice_date = inv_date
        invoice.amount = amount
        invoice.tax_amount = tax_amount
        invoice.total_amount = total_amount
        invoice.seller_name = self._safe_part(seller, limit=120)
        invoice.buyer_name = self._safe_part(buyer, limit=120)
        invoice.save(
            update_fields=[
                "invoice_code",
                "invoice_number",
                "invoice_date",
                "amount",
                "tax_amount",
                "total_amount",
                "seller_name",
                "buyer_name",
            ]
        )

        if payment is not None and total_amount is not None and not duplicated:
            self._recompute_invoiced_amount(payment)

        folder_subpath, skipped = "", ""
        if to_contract_folder:
            folder_subpath, skipped = self._mirror_to_contract_folder(
                contract_id=contract_id,
                contract_name=contract_name,
                invoice=invoice,
                inv_date=inv_date,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
            )

        return SavedInvoice(
            id=invoice.id,
            original_filename=original_filename,
            stored_filename=self.display_filename(
                contract_name=contract_name,
                seller=seller,
                inv_date=inv_date,
                ext=_ext(file_path),
            ),
            file_path=file_path,
            file_url=f"{_media_url()}{file_path}",
            invoice_code=code,
            invoice_number=number,
            invoice_date=inv_date,
            amount=amount,
            tax_amount=tax_amount,
            total_amount=total_amount,
            seller_name=seller,
            buyer_name=buyer,
            duplicated=duplicated,
            contract_name=contract_name,
            folder_subpath=folder_subpath,
            folder_skipped_reason=skipped,
        )

    def list_invoices(
        self, contract_id: int, *, payment_ids: list[int] | None = None, unlinked_only: bool = False
    ) -> list[Any]:
        """合同（或其下若干收款）的发票，uploaded_at 倒序扁平列表。

        未关联收款的发票（先开票后付款挂在合同名下）也在其中；
        `unlinked_only=True` 只取这部分。
        """
        from apps.contracts.models import Invoice

        qs = Invoice.objects.filter(Q(payment__contract_id=contract_id) | Q(contract_id=contract_id)).select_related(
            "payment__contract", "contract"
        )
        if payment_ids:
            qs = qs.filter(payment_id__in=payment_ids)
        if unlinked_only:
            qs = qs.filter(payment__isnull=True)
        return list(qs.order_by("-uploaded_at", "-id"))

    def payment_invoice_state(self, payment_id: int) -> dict[str, str]:
        """某笔收款当前的开票状态与金额（上传响应就地刷新收款行用）。

        ORM 查询留在 Service 层——API 层出现 Model.objects 会撞四层架构门禁。
        """
        from apps.contracts.models import ContractPayment
        from apps.core.exceptions import NotFoundError

        try:
            payment = ContractPayment.objects.get(pk=payment_id)
        except ContractPayment.DoesNotExist:
            raise NotFoundError(message="收款记录不存在", code="PAYMENT_NOT_FOUND") from None
        return {
            "invoice_status": payment.invoice_status,
            "invoice_status_label": payment.get_invoice_status_display(),
            "invoiced_amount": str(payment.invoiced_amount),
        }

    @transaction.atomic
    def attach_invoice(
        self,
        *,
        invoice_id: int,
        payment_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> tuple[Any, Any]:
        """把「先开票」的合同挂靠发票关联到一笔收款（钱到账后的核销动作）。

        返回 ``(invoice, payment)``；跨合同、已关联别的收款都拒绝——财务数据
        宁可让人重传，不可错挂。
        """
        from apps.contracts.models import Invoice
        from apps.core.exceptions import NotFoundError

        try:
            invoice = Invoice.objects.select_related("payment__contract", "contract").get(pk=invoice_id)
        except Invoice.DoesNotExist:
            raise NotFoundError(message="发票不存在", code="INVOICE_NOT_FOUND") from None

        if invoice.payment_id is not None:
            raise ValidationException(message="该发票已关联收款，先解除关联才能改挂", code="INVOICE_ALREADY_ATTACHED")

        payment = self._load_payment(payment_id, user=user, org_access=org_access, perm_open_access=perm_open_access)
        if invoice.contract_id != payment.contract_id:
            raise ValidationException(message="发票与收款不属于同一合同", code="INVOICE_CONTRACT_MISMATCH")

        invoice.payment = payment
        invoice.contract = None
        invoice.save(update_fields=["payment", "contract"])
        self._recompute_invoiced_amount(payment)
        return invoice, payment

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
            invoice = Invoice.objects.select_related("payment__contract", "contract").get(pk=invoice_id)
        except Invoice.DoesNotExist:
            raise NotFoundError(message="发票不存在", code="INVOICE_NOT_FOUND") from None

        if invoice.payment_id is not None:
            payment = self._load_payment(
                invoice.payment_id, user=user, org_access=org_access, perm_open_access=perm_open_access
            )
        else:
            payment = None
            self.ensure_contract_access(
                invoice.contract_id, user=user, org_access=org_access, perm_open_access=perm_open_access
            )
        get_invoice_upload_service().delete_invoice(invoice.id)
        if payment is not None:
            self._recompute_invoiced_amount(payment)
        return {"success": True}

    def copy_file_to_clipboard(
        self,
        *,
        invoice_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> int:
        """把发票以**重命名后**的文件名复制到 macOS 系统剪贴板（同 Finder ⌘C）。

        media 仓库存的是 UUID 文件名，直接落板粘出去名字面目全非；这里把字节
        复制到临时目录、按 `发票（合同名称）_YYYYMMDD开具.pdf` 命名后落板，
        律师在微信对话框 ⌘V 粘出的就是可直发的文件。临时文件必须**留存**到
        粘贴之后（pasteboard 持有的是 file-url），只顺手清扫超过 24h 的旧副本。
        非 macOS / 无 pyobjc 由调用方先行判断（同 court-sms 口径）。
        """
        import tempfile

        from apps.contracts.models import Invoice
        from apps.core.services.mac_clipboard_service import MacClipboardFileService

        try:
            invoice = Invoice.objects.select_related("payment__contract", "contract").get(pk=invoice_id)
        except Invoice.DoesNotExist:
            from apps.core.exceptions import NotFoundError

            raise NotFoundError(message="发票不存在", code="INVOICE_NOT_FOUND") from None

        # chk_invoice_payment_xor_contract：收款/合同恰好一条有值，断言给 mypy 看
        contract = invoice.payment.contract if invoice.payment is not None else invoice.contract
        assert contract is not None
        self.ensure_contract_access(contract.pk, user=user, org_access=org_access, perm_open_access=perm_open_access)

        display_name = self.display_filename(
            contract_name=str(contract.name or ""),
            seller=str(invoice.seller_name or ""),
            inv_date=invoice.invoice_date,
            ext=_ext(invoice.file_path),
        )

        staging = Path(tempfile.mkdtemp(prefix="fachuan-invoice-"))
        target = staging / display_name
        target.write_bytes(Path(_media_abs(invoice.file_path)).read_bytes())
        _sweep_stale_copies(staging.parent)

        copied = MacClipboardFileService().copy_file_paths([target])
        if copied == 0:
            logger.warning("invoice_clipboard_write_failed", extra={"invoice_id": invoice_id, "name": display_name})
        return copied

    # ------------------------------------------------------------------ 鉴权

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
        from apps.core.exceptions import NotFoundError

        try:
            payment = ContractPayment.objects.select_related("contract").get(pk=payment_id)
        except ContractPayment.DoesNotExist:
            raise NotFoundError(message="收款记录不存在", code="PAYMENT_NOT_FOUND") from None

        ContractAccessPolicy = _access_policy()
        ContractAccessPolicy().ensure_access(
            contract_id=payment.contract_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )
        return payment

    def ensure_contract_access(
        self,
        contract_id: int | None,
        *,
        user: Any | None,
        org_access: dict[str, Any] | None,
        perm_open_access: bool,
    ) -> None:
        """先开票路径的合同行级鉴权（与收款口径一致）。"""
        from apps.core.exceptions import NotFoundError

        if contract_id is None:
            raise NotFoundError(message="发票未挂靠任何合同", code="INVOICE_NO_CONTRACT") from None
        ContractAccessPolicy = _access_policy()
        ContractAccessPolicy().ensure_access(
            contract_id=contract_id, user=user, org_access=org_access, perm_open_access=perm_open_access
        )

    # ------------------------------------------------------------------ 内部

    def _validate_file(self, uploaded_file: Any) -> None:
        name = str(getattr(uploaded_file, "name", "") or "")
        ext = _ext(name)
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
        contract_name: str,
        invoice: Any,
        inv_date: date | None,
        user: Any | None,
        org_access: dict[str, Any] | None,
        perm_open_access: bool,
    ) -> tuple[str, str]:
        """把发票复制到合同绑定文件夹的发票目录下（失败只记录原因，不抛）。

        发票目录不固定在顶层：律所模板多为 `1-律师资料/3-发票`，先在两层目录内
        找名字以「发票」结尾的目录（`发票` / `3-发票` 都认），没有才在顶层建 `发票/`。
        """
        from apps.contracts.services.contract.integrations.folder_browse_service import ContractFolderBrowseService

        service = ContractFolderBrowseService()
        access: dict[str, Any] = {
            "user": user,
            "org_access": org_access,
            "perm_open_access": perm_open_access,
        }

        try:
            subpath = self._locate_invoice_dir(service, contract_id, access)
        except Exception as exc:  # 未绑定 / 云存储 / 目录不可达：都不是开票失败
            logger.info("invoice_folder_mirror_skipped", extra={"contract_id": contract_id, "reason": str(exc)})
            return "", _skip_reason(exc)

        display_name = self.display_filename(
            contract_name=contract_name,
            seller=str(invoice.seller_name or ""),
            inv_date=inv_date,
            ext=_ext(invoice.file_path),
        )
        try:
            saved = service.save_upload_bytes(
                owner_id=contract_id,
                subpath=subpath,
                filename=display_name,
                data=Path(_media_abs(invoice.file_path)).read_bytes(),
                **access,
            )
        except Exception as exc:
            logger.warning("invoice_folder_mirror_failed", exc_info=True)
            return "", _skip_reason(exc)

        return str(saved.get("subpath") or ""), ""

    def _locate_invoice_dir(self, service: Any, contract_id: int, access: dict[str, Any]) -> str:
        """在绑定文件夹两层内找发票目录；找不到就在顶层建 `发票/`。返回子目录 subpath。"""
        root = service.list_entries(owner_id=contract_id, subpath="", **access)

        def _dirs(entries: dict[str, Any]) -> list[dict[str, Any]]:
            return [f for f in (entries.get("folders") or []) if isinstance(f, dict) and f.get("name")]

        l1_dirs = _dirs(root)
        for folder in l1_dirs:
            if self._is_invoice_dir(str(folder["name"])):
                return str(folder.get("subpath") or folder["name"])

        # 第二层：`1-律师资料/3-发票` 这类嵌套
        for folder in l1_dirs:
            try:
                entries = service.list_entries(
                    owner_id=contract_id, subpath=str(folder.get("subpath") or folder["name"]), **access
                )
            except Exception as exc:
                logger.info("invoice_folder_walk_skipped", extra={"folder": str(folder["name"]), "reason": str(exc)})
                continue
            for sub in _dirs(entries):
                if self._is_invoice_dir(str(sub["name"])):
                    return str(sub.get("subpath") or f"{folder['name']}/{sub['name']}")

        try:
            service.mkdir(owner_id=contract_id, subpath="", name=self.FOLDER_NAME, **access)
        except Exception as exc:
            # 并发下另一张发票已建好同名目录 → 视为已存在，继续写文件
            logger.info("invoice_folder_mkdir_skipped", extra={"reason": str(exc)})
        return self.FOLDER_NAME

    @classmethod
    def _is_invoice_dir(cls, name: str) -> bool:
        """`发票` / `3-发票` 认；`发票领取台账` 这类记录性目录不误认（要求以「发票」结尾）。"""
        cleaned = name.strip()
        return cleaned.endswith(cls.FOLDER_NAME) and len(cleaned) <= 12

    def display_filename(self, *, contract_name: str, inv_date: date | None, ext: str, seller: str = "") -> str:
        """`发票（{合同名称}）_YYYYMMDD开具.pdf`——沿用律所手工命名习惯。

        括号里是**合同/案件名称**（律师按案找票，名称才是检索键；销售方在数电票
        里常与购买方串行、识别不稳，且跨案件无区分度）。合同名按 UTF-8 字节截断，
        保证整名不超 macOS 255 字节文件名上限。名称缺失时退销售方，再退「发票」。
        开票日期识别不出则省略日期段；金额不进文件名（窗口里几十个 ¥9,000
        无区分度）。
        """
        base = self._safe_part(contract_name, limit=100) or self._safe_part(seller, limit=60)
        head = f"发票（{_clip_utf8(base, max_bytes=210)}）" if base else "发票"
        tail = inv_date.strftime("%Y%m%d") + "开具" if inv_date else ""
        stem = "_".join(p for p in (head, tail) if p)
        return f"{stem}{ext or '.pdf'}"

    @classmethod
    def _safe_part(cls, raw: str, *, limit: int) -> str:
        cleaned = cls._ILLEGAL_NAME_CHARS.sub("", raw).strip(" .")
        return cleaned[:limit] or ""
