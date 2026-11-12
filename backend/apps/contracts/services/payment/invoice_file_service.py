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

## 红字发票（冲销票）的落点分流

红票与重开蓝票常同日同合同（开票日期相同、合同名相同），不改名必然在合同文件夹里
撞名，所以红票命名尾部换成 `YYYYMMDD红字开具`；落点也换成 `<发票目录>/已冲红/`，
连同被它冲销的原票一起移进去。

**为什么是目录隔离而不是归档期过滤**：`FinalizedMaterial` 才是归档材料来源，
只要扫描时看不到作废票，归档天然干净；归档代码里每多一条判断，就多一次将来被
漏改的机会。「冲红票和旧票新建一个文件夹单独放」是用户拍定的口径。

`已冲红/` 按需创建（没有冲红的项目不该多一个空目录），移入是**移动而非复制**——
`Invoice.folder_subpath` 是单一可信位置，根目录里不允许再留一份。
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

__all__ = ["InvoiceFileService", "SavedInvoice", "VOIDED_DIR_NAME", "invoice_voided_by", "is_voided"]

#: 冲红隔离目录名（挂在发票目录下）。闸 2（文件夹扫描）与闸 3（归档材料）都按这个名字 /
#: 文件名里的「红字开具」识别作废票，改这里必须同步改那两处
VOIDED_DIR_NAME = "已冲红"
#: 红票文件名的尾部标记（`YYYYMMDD红字开具.pdf`）。归档闸 3 只能靠它判断作废票
VOIDED_NAME_MARKER = "红字开具"


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


#: 落板暂存根目录（与 doc_converter 同一套思路：固定目录覆盖写）。
#: file-url 是路径引用，粘贴方按路径读文件，所以副本**不能**放在 mkdtemp 里
#: 每点一次复制就多一个永久目录（旧实现如此，T 目录里堆满空的
#: `fachuan-invoice-xxxx`）；固定根目录 + 按发票 id 分目录覆盖写，量小且可控。
INVOICE_CLIPBOARD_ROOT_NAME = "fachuan-invoice-clipboard"


def _clipboard_root() -> Path:
    """落板暂存根目录（`<tmp>/fachuan-invoice-clipboard`，按需创建）。"""
    import tempfile

    root = Path(tempfile.gettempdir()) / INVOICE_CLIPBOARD_ROOT_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def _sweep_stale_copies(temp_root: Path) -> None:
    """清扫 24 小时前留下的发票暂存子目录（落板文件要等用户粘贴，只能事后清）。"""
    import shutil
    import time

    cutoff = time.time() - 24 * 3600
    for old in temp_root.glob("invoice-*"):
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


# ── 作废派生（不落库）─────────────────────────────────────────────


def _invoice_contract_id(invoice: Any) -> int | None:
    """发票归属的合同：挂收款时跟收款走，先开票后付款时直接挂合同。"""
    contract_id = getattr(invoice, "contract_id", None)
    if contract_id:
        return int(contract_id)
    payment = getattr(invoice, "payment", None) if getattr(invoice, "payment_id", None) else None
    payment_contract_id = getattr(payment, "contract_id", None)
    return int(payment_contract_id) if payment_contract_id else None


def invoice_voided_by(invoice: Any) -> Any | None:
    """返回冲销这张票的那张**已确认红票** ``Invoice``（没有则 ``None``）。

    判据全部是账务事实，不查任何布尔位：

    1. 存在一条 ``CONFIRMED`` 的 ``InvoiceIntake``，其 ``offset_invoice`` 指向本票；
    2. 该 intake 自己确实是红票（``is_red``：票面有被冲蓝票号或金额为负）；
    3. 它落成的那张 ``Invoice`` 存在且金额为负。

    第 2 条故意加“票面有被冲蓝票号”：解析失败的红票可能 ``total_amount`` 为空，
    这时若只看金额，冲销关系成立但证据不完整；而**金额未知时不允许冲红**（会让
    账目 ``Sum`` 少一笔负数），所以那种 intake 永远不可能被确认，这里自然排除。

    作废状态不落字段（不加 ``is_void``）：作废是由“同项目存在冲销它的已确认红票”
    派生的，存一份就有两份真相，而归档安全正是靠这个派生永远自洽。
    """
    from apps.contracts.models import Invoice, InvoiceIntake, InvoiceIntakeStatus

    invoice_id = getattr(invoice, "pk", None)
    if invoice_id is None:
        return None
    red_invoice_ids = (
        InvoiceIntake.objects.filter(
            status=InvoiceIntakeStatus.CONFIRMED,
            offset_invoice_id=invoice_id,
            invoice__isnull=False,
        )
        .exclude(red_against_number="")
        .values_list("invoice_id", flat=True)
    )
    found: Any = Invoice.objects.filter(pk__in=list(red_invoice_ids), total_amount__lt=0).order_by("pk").first()
    return found


def is_voided(invoice: Any) -> bool:
    """是否已被红票冲销（``invoice_voided_by`` 的布尔形式，供 UI/报告直接问）。"""
    return invoice_voided_by(invoice) is not None


def _is_red_facts(*, number: str, total_amount: Decimal | None) -> bool:
    """红票判据（票面事实）：备注栏有被冲蓝票号，或价税合计为负。"""
    if number:
        return True
    return total_amount is not None and total_amount < 0


def _invoice_is_red(invoice: Any) -> bool:
    """已有的 ``Invoice`` 是不是红票。

    既看票面事实（金额为负），也看生成它的 intake 的 ``is_red``：票据被登记为
    红票却没识别出金额时，文件名仍必须带红字标记，否则与重开蓝票必然撞名。
    """
    if getattr(invoice, "total_amount", None) is not None and invoice.total_amount < 0:
        return True
    from apps.contracts.models import InvoiceIntake

    intake = InvoiceIntake.objects.filter(invoice_id=invoice.pk).first()
    return bool(getattr(intake, "is_red", False)) if intake is not None else False


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
        reject_duplicated_number: bool = False,
    ) -> SavedInvoice:
        """保存一张发票。挂靠二选一：

        - `payment_id`：直接归属到某笔收款（先付款后开票），保存后回填开票金额；
        - `contract_id`：**先开票后付款**——票先挂合同名下，不动任何收款的
          开票金额，等钱到账记收款后走 :meth:`attach_invoice` 关联。

        `parsed` 是 invoice_recognition 的 ``ParsedInvoice``（可为 None：纯上传不识别）。
        识别字段只作为**建议值**写入，律师可在前端改动后再提交。

        `reject_duplicated_number=True` 把“同号发票已存在”从**提示**升级为**拒收**：
        待认领确认（``confirm_invoice_intake`` / ``confirm_red_reenact``）走这条，
        因为那里的同号票几乎必然是“同一张票被确认了两次”；而人手拖文件上传时
        “重传同一张票覆盖”是真实场景，那条路径保持 ``False``（只提示不拦）。
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
        if duplicated and reject_duplicated_number:
            raise ValidationException(
                message=f"发票号码 {number} 已在本项目入账，不能重复确认",
                code="INVOICE_NUMBER_DUPLICATED",
                errors={"invoice_number": number},
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
        is_red = _is_red_facts(number=str(getattr(parsed, "red_against_number", "") or ""), total_amount=total_amount)
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
                is_red=is_red,
            )

        return SavedInvoice(
            id=invoice.id,
            original_filename=original_filename,
            stored_filename=self.display_filename(
                contract_name=contract_name,
                seller=seller,
                inv_date=inv_date,
                ext=_ext(file_path),
                is_red=is_red,
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
        """把「先开票」的合同挂靠发票关联到一笔收款（钱到账后的归属动作）。

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
    def detach_invoice(
        self,
        *,
        invoice_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> tuple[Any, Any | None]:
        """把已关联收款的发票退回合同名下（挂错时的唯一补救动作）。

        财务口径：退回后立刻重算原收款的开票金额——不然会出现「票已不属于这笔
        收款，但已开票金额里还算着它」的错账。media 文件不搬动（`file_path` 只是
        存储位置，展示名另算），原文与合同文件夹里的副本都不受影响。

        返回 ``(invoice, 原收款或 None)``；未关联的发票再解绑是 400（不是静默成功），
        否则前端无法区分「本来就没挂」和「解绑没生效」。
        """
        from apps.contracts.models import Invoice
        from apps.core.exceptions import NotFoundError

        try:
            invoice = Invoice.objects.select_related("payment__contract", "contract").get(pk=invoice_id)
        except Invoice.DoesNotExist:
            raise NotFoundError(message="发票不存在", code="INVOICE_NOT_FOUND") from None

        if invoice.payment_id is None:
            raise ValidationException(message="该发票尚未关联收款，无需解除", code="INVOICE_NOT_ATTACHED")

        payment = self._load_payment(
            invoice.payment_id, user=user, org_access=org_access, perm_open_access=perm_open_access
        )
        invoice.contract = payment.contract
        invoice.payment = None
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
        复制到暂存目录、按 `发票（合同名称）_YYYYMMDD开具.pdf` 命名后落板，
        律师在微信对话框 ⌘V 粘出的就是可直发的文件。临时文件必须**留存**到
        粘贴之后（pasteboard 持有的是 file-url），只顺手清扫超过 24h 的旧副本。
        非 macOS / 无 pyobjc 由调用方先行判断（同 court-sms 口径）。

        返回成功落板的数量；media 原件缺失时返回 0（不抛 500）——调用方据此降级
        复制文件名，比让前端看到「系统错误」有用得多。
        """
        import shutil

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
            is_red=_invoice_is_red(invoice),
        )

        source = Path(_media_abs(invoice.file_path))
        if not source.is_file():
            # 原件丢失（media 被清、迁移未跟）不是「系统错误」，如实报落板失败
            logger.warning(
                "invoice_clipboard_source_missing",
                extra={"invoice_id": invoice_id, "file_path": invoice.file_path},
            )
            return 0

        root = _clipboard_root()
        _sweep_stale_copies(root)
        # 按发票 id 固定子目录：重复点复制只覆盖同名文件，不再每次 mkdtemp 堆一堆空目录
        staging = root / f"invoice-{invoice_id}"
        staging.mkdir(parents=True, exist_ok=True)
        target = staging / display_name
        try:
            shutil.copyfile(source, target)
        except OSError:
            logger.warning("invoice_clipboard_stage_failed", exc_info=True, extra={"invoice_id": invoice_id})
            return 0

        copied = MacClipboardFileService().copy_file_paths([target])
        if copied == 0:
            logger.warning(
                "invoice_clipboard_write_failed", extra={"invoice_id": invoice_id, "display_name": display_name}
            )
            return 0
        # 刷新暂存目录 mtime：否则重复复制（只覆盖文件）会让 24h 清扫把刚落的板文件删了
        target.touch()
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

    def recompute_payment_invoicing(self, payment: Any) -> None:
        """公开入口：外部（如待认领发票撤销）删掉发票后，重算这笔收款的开票状态。

        存在的理由：收款的开票金额是**从发票表推算**出来的派生值，任何绕过本服务
        删发票的路径（待认领撤销、管理后台批量删）都必须调一次这里，否则收款会
        停在旧状态一直说「已全额开票」，而实际一张票都没了。
        """
        self._recompute_invoiced_amount(payment)

    def _recompute_invoiced_amount(self, payment: Any) -> None:
        """按发票合计**全量重算** invoiced_amount 与开票状态。

        全量重算而不是增量累加：增删任一发票都能得到同一个正确答案；增量法在并发
        上传两张时会各自基于旧值相加，最终多算一次。

        口径（已定稿）：``invoiced_amount`` 是**净额**（``Sum`` 含红票负数）。上限
        只对**正数**成立——红票让合计变负是合法的中间态（冲红后尚未重开），用 ``min()``
        截断会把这个中间态错算成“已全额开票”，而此刻一张有效票都没有；负数放行，
        最后统一 ``max(0)`` 兜底（模型约束 ``chk_contractpayment_invoiced_nonneg``）。

        净额下“冲红未重开”与“从没开过票”都是 0，必须靠 ``VOIDED_PENDING_REISSUE``
        区分：财务主动冲红和从没开票是两件事。
        """
        from django.db.models import Sum

        from apps.contracts.models import Invoice, InvoiceStatus

        total = Invoice.objects.filter(payment_id=payment.id).aggregate(s=Sum("total_amount"))["s"]
        invoiced = Decimal(str(total)) if total is not None else Decimal("0")
        payment_amount = Decimal(str(payment.amount))
        # 开票金额不得超过收款金额（模型约束 chk_contractpayment_invoiced_le_amount）
        if invoiced > 0:
            invoiced = min(invoiced, payment_amount)
        invoiced = max(invoiced, Decimal("0"))

        if invoiced == 0:
            status = (
                InvoiceStatus.VOIDED_PENDING_REISSUE if self._has_confirmed_red(payment) else InvoiceStatus.UNINVOICED
            )
        elif invoiced < payment_amount:
            status = InvoiceStatus.INVOICED_PARTIAL
        else:
            status = InvoiceStatus.INVOICED_FULL

        payment.invoiced_amount = invoiced
        payment.invoice_status = status
        payment.save(update_fields=["invoiced_amount", "invoice_status", "updated_at"])

    def _has_confirmed_red(self, payment: Any) -> bool:
        """这笔收款名下是否存在红票（金额为负）。

        只看 ``Invoice``：发票记录**只由确认产生**（待认领仍在池子里时一笔都没落），
        所以“名下有张负额 Invoice”就等于“有张已确认的红票”——不必再回查 intake，
        也不必管它是手工上传还是待认领确认来的。
        """
        from apps.contracts.models import Invoice

        return Invoice.objects.filter(payment_id=payment.id, total_amount__lt=0).exists()

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
        is_red: bool = False,
    ) -> tuple[str, str]:
        """把发票复制到合同绑定文件夹的发票目录下（失败只记录原因，不抛）。

        发票目录不固定在顶层：律所模板多为 `1-律师资料/3-发票`，先在两层目录内
        找名字以「发票」结尾的目录（`发票` / `3-发票` 都认），没有才在顶层建 `发票/`。

        `is_red=True` 时落到 `<发票目录>/已冲红/`（按需创建）：红票与重开蓝票同日同合同，
        混在同一层不仅容易看起来像两张有效票，也让归档要额外判断。
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

        if is_red:
            try:
                subpath = self._ensure_voided_dir(service, contract_id, subpath, access)
            except Exception as exc:
                logger.warning("invoice_voided_dir_mkdir_failed", extra={"subpath": subpath}, exc_info=True)
                return "", _skip_reason(exc)

        display_name = self.display_filename(
            contract_name=contract_name,
            seller=str(invoice.seller_name or ""),
            inv_date=inv_date,
            ext=_ext(invoice.file_path),
            is_red=is_red,
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

    def _ensure_voided_dir(self, service: Any, contract_id: int, invoice_dir: str, access: dict[str, Any]) -> str:
        """`<发票目录>/已冲红/` 的 subpath，不存在则建（**按需创建**）。

        空目录在 Finder 里是噪声，也不该污染律所模板目录，所以只在真要写入时建。
        并发下另一次冲红已建好同名目录时 mkdir 会报“同名项目已存在”，直接当已存在处理。
        """
        target = f"{invoice_dir}/{VOIDED_DIR_NAME}" if invoice_dir else VOIDED_DIR_NAME
        try:
            entries = service.list_entries(owner_id=contract_id, subpath=invoice_dir, **access)
        except Exception:
            entries = {}
        for folder in entries.get("folders") or []:
            if isinstance(folder, dict) and str(folder.get("name") or "").strip() == VOIDED_DIR_NAME:
                return str(folder.get("subpath") or target)
        try:
            created = service.mkdir(owner_id=contract_id, subpath=invoice_dir, name=VOIDED_DIR_NAME, **access)
            return str(created.get("subpath") or target)
        except Exception:
            logger.info("invoice_voided_dir_mkdir_skipped", extra={"subpath": target})
            return target

    @transaction.atomic
    def move_invoice_to_voided(
        self,
        *,
        invoice_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> str:
        """把原票移进 `<发票目录>/已冲红/` 并写回 ``folder_subpath``，返回新 subpath。

        **移动而非复制**：原票从发票目录移出，不允许“根目录一份 + 已冲红一份”；
        ``folder_subpath`` 是撤销时确定位置的唯一依据，不许出现两份。
        未镜像到合同文件夹（``folder_subpath`` 为空）时返回空串（media 副本仍在）。
        """
        return self._relocate_voided(
            invoice_id, to_voided=True, user=user, org_access=org_access, perm_open_access=perm_open_access
        )

    @transaction.atomic
    def move_invoice_back_from_voided(
        self,
        *,
        invoice_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> str:
        """撤销时把原票从 `已冲红/` 移回发票目录，并写回 ``folder_subpath``。

        整组撤销必须移回：半截状态（红票删了、原票还在 `已冲红/`）是比错账更难查的
        东西。不在 `已冲红/` 里时原样返回旧 subpath（幂等，可重入）。
        """
        return self._relocate_voided(
            invoice_id, to_voided=False, user=user, org_access=org_access, perm_open_access=perm_open_access
        )

    def _relocate_voided(
        self,
        invoice_id: int,
        *,
        to_voided: bool,
        user: Any | None,
        org_access: dict[str, Any] | None,
        perm_open_access: bool,
    ) -> str:
        """冲红目录与发票目录之间的文件搬运（两个公开方法的共用实现）。

        **为什么直接用 pathlib 而不走 ``ContractFolderBrowseService``**：浏览服务只提供
        ``rename``（同目录改名）/ ``copy_entry`` + ``delete_entry``（两步，中间失败就留下
        两份或零份）。本动作要求“要么原位要么位置”，而且我们手里已经有绑定根的绝对路径，
        查一次目录列表就能校验“源在已冲红 / 目标不在已冲红”，然后 ``Path.replace``
        在同文件系统上一步完成——比“复制 + 软删”少一半失败面。

        ACL 仍走合同行级鉴权（``ensure_contract_access``），路径合法仍用 ``Path.relative_to``
        校验不越出绑定根（等价于 ``is_within_root``），不新开豁口。
        """
        from apps.contracts.models import Invoice
        from apps.core.exceptions import NotFoundError, ValidationException

        try:
            invoice = Invoice.objects.select_related("payment__contract", "contract").get(pk=invoice_id)
        except Invoice.DoesNotExist:
            raise NotFoundError(message="发票不存在", code="INVOICE_NOT_FOUND") from None

        contract_id = _invoice_contract_id(invoice)
        self.ensure_contract_access(contract_id, user=user, org_access=org_access, perm_open_access=perm_open_access)
        subpath = str(getattr(invoice, "folder_subpath", "") or "")
        if contract_id is None or not subpath:
            return subpath

        from apps.contracts.services.contract.integrations.folder_browse_service import ContractFolderBrowseService

        access: dict[str, Any] = {"user": user, "org_access": org_access, "perm_open_access": perm_open_access}
        service = ContractFolderBrowseService()
        try:
            root = service._local_root(contract_id)  # 子类钩子，取绑定根是唯一来源
        except Exception as exc:  # 未绑定 / 云存储 / 目录不可达：不阻断裁定，folder_subpath 保持原值
            logger.info(
                "invoice_folder_relocate_root_unreachable",
                extra={"contract_id": contract_id, "reason": _skip_reason(exc)},
            )
            return subpath
        source = root / subpath
        if not source.is_file():
            logger.info(
                "invoice_folder_relocate_source_missing", extra={"contract_id": contract_id, "subpath": subpath}
            )
            return subpath

        # `Path("")` 是 `Path(".")`，直接当父目录会把文件移到 "x.pdf/已冲红/" 这种鬼路径下。
        # 发票直接落在绑定根时 parent 为空串，这里显式收敛成 root。
        parent_dir = root / Path(subpath).parent
        if to_voided:
            target_dir = parent_dir / VOIDED_DIR_NAME
            target_dir.mkdir(parents=True, exist_ok=True)
        else:
            # 撤回到发票目录：`<发票目录>/已冲红/x.pdf` → `<发票目录>/x.pdf`。
            # 不在已冲红里时 parent 就是发票目录本身，不动文件（幂等）。
            in_voided = parent_dir.name == VOIDED_DIR_NAME
            target_dir = parent_dir.parent if in_voided else parent_dir
        if not target_dir.is_dir():
            raise ValidationException(message="发票目录不存在，无法移动发票", errors={"subpath": subpath})

        target = target_dir / source.name
        if target.is_file() and target.resolve() == source.resolve():
            return subpath
        if target.exists():
            # 同名不同件：加序号，宁可多一个后缀也不覆盖任何一份原件。
            # 同件（上一轮已移完但 folder_subpath 没落库）时 replace 不会重复写内容。
            target = service._unique_destination(target_dir, source.name)
        source.replace(target)  # 同一文件系统内的原子改名（跨目录就是移动）

        try:
            new_subpath = target.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            raise ValidationException(message="发票移动目标越界", errors={"subpath": subpath}) from None

        Invoice.objects.filter(pk=invoice.pk).update(folder_subpath=new_subpath)
        logger.info(
            "invoice_folder_voided_relocated",
            extra={
                "contract_id": contract_id,
                "invoice_id": invoice.pk,
                "from": subpath,
                "to": new_subpath,
                "to_voided": to_voided,
            },
        )
        return new_subpath

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

    def display_filename(
        self, *, contract_name: str, inv_date: date | None, ext: str, seller: str = "", is_red: bool = False
    ) -> str:
        """`发票（{合同名称}）_YYYYMMDD开具.pdf`——沿用律所手工命名习惯。

        括号里是**合同/案件名称**（律师按案找票，名称才是检索键；销售方在数电票
        里常与购买方串行、识别不稳，且跨案件无区分度）。合同名按 UTF-8 字节截断，
        保证整名不超 macOS 255 字节文件名上限。名称缺失时退销售方，再退「发票」。
        开票日期识别不出则省略日期段；金额不进文件名（窗口里几十个 ¥9,000
        无区分度）。

        `is_red=True` 时尾部换成 `YYYYMMDD红字开具`。两条理由都不允许商量：

        1. 同一天的红票与重开蓝票**开票日期相同、合同名相同**，不改就必然在合同
           文件夹里撞名（`_已删除/` 只能救一次）；
        2. **归档闸 3 依赖它**：`FinalizedMaterial` 只有 `file_path`，反查不回
           `Invoice`，兜底判据只能是文件名里的「红字开具」。命名与归档安全因此闭环。

        ⚠ 只对**新建**发票生效，已入库的历史票不被重命名。
        """
        base = self._safe_part(contract_name, limit=100) or self._safe_part(seller, limit=60)
        head = f"发票（{_clip_utf8(base, max_bytes=210)}）" if base else "发票"
        tail = ""
        if inv_date:
            tail = inv_date.strftime("%Y%m%d") + (VOIDED_NAME_MARKER if is_red else "开具")
        stem = "_".join(p for p in (head, tail) if p)
        return f"{stem}{ext or '.pdf'}"

    @classmethod
    def _safe_part(cls, raw: str, *, limit: int) -> str:
        cleaned = cls._ILLEGAL_NAME_CHARS.sub("", raw).strip(" .")
        return cleaned[:limit] or ""
