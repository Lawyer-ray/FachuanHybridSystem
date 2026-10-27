"""收款记账增强 API：到账短信识别 + 发票拖拽识别落库。

端点都属「记收款」这条链路，并进合同收款 router（前缀 `/api/v1/contracts/finance`）：

- `POST   /finance/payments/parse-text`        粘一段到账短信 → 草稿（不落库）
- `POST   /finance/payments/{id}/invoices`     拖发票进来 → 识别 + 落盘 + 回填开票金额
- `GET    /finance/payments/{id}/invoices`     某笔收款的发票列表
- `POST   /finance/contracts/{id}/invoices`    **先开票后付款**：票先挂合同名下（不动开票金额）
- `GET    /finance/contracts/{id}/invoices`    合同发票列表（含未核销；`?unlinked=1` 只看待核销）
- `POST   /finance/invoices/{id}/attach`       钱到账后把合同挂靠发票核销到某笔收款
- `POST   /finance/invoices/{id}/copy-to-clipboard`  复制重命名后的发票文件到系统剪贴板
- `DELETE /finance/invoices/{id}`              删发票 + 重算开票金额
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from asgiref.sync import sync_to_async
from django.http import HttpRequest
from ninja import File, Router
from ninja.files import UploadedFile

from apps.contracts.schemas.payment_enhance_schemas import (
    ContractPaymentParseIn,
    ContractPaymentParseOut,
    InvoiceAttachIn,
    InvoiceAttachOut,
    InvoiceCopyOut,
    InvoiceOut,
    InvoiceUploadFailure,
    InvoiceUploadOut,
)
from apps.core.dto.request_context import extract_request_context

logger = logging.getLogger("apps.contracts.api")

router = Router()


# --------------------------------------------------------------------- 短信识别


@router.post("/finance/payments/parse-text", response=ContractPaymentParseOut)
async def parse_payment_text(request: HttpRequest, payload: ContractPaymentParseIn) -> Any:
    """把粘贴的到账短信/转账截图文字解析成收款草稿。

    **只解析不落库**：金额错一位是财务事故，必须先让人在表单里核对。前端拿到草稿
    后预填「记收款」表单，律师改完再走既有的 `POST /finance/payments`。
    """
    from apps.contracts.services.payment.payment_sms_parser import PaymentSmsParser

    parsed = await sync_to_async(PaymentSmsParser().parse)(payload.text)
    return ContractPaymentParseOut(
        amount=str(parsed.amount) if parsed.amount is not None else None,
        received_at=parsed.received_at.isoformat() if parsed.received_at else None,
        payer=parsed.payer,
        note=parsed.note,
        hints=parsed.hints,
    )


# --------------------------------------------------------------------- 发票


@router.get("/finance/payments/{payment_id}/invoices", response=list[InvoiceOut])
async def list_payment_invoices(request: HttpRequest, payment_id: int, contract_id: int) -> Any:
    """某条收款记录下的发票（`contract_id` 必传：发票鉴权口径跟着合同行级 ACL 走）。"""
    service = _invoice_service()
    ctx = await sync_to_async(extract_request_context)(request)
    invoices = await sync_to_async(service.list_invoices)(contract_id, payment_ids=[payment_id])
    return [_invoice_out(inv) for inv in invoices]


@router.get("/finance/contracts/{contract_id}/invoices", response=list[InvoiceOut])
async def list_contract_invoices(request: HttpRequest, contract_id: int, unlinked: bool = False) -> Any:
    """合同发票列表：已核销的 + 先开票挂合同的。`?unlinked=true` 只看待核销。"""
    service = _invoice_service()
    ctx = await sync_to_async(extract_request_context)(request)
    await sync_to_async(service.ensure_contract_access)(
        contract_id, user=ctx.user, org_access=ctx.org_access, perm_open_access=ctx.perm_open_access
    )
    invoices = await sync_to_async(service.list_invoices)(contract_id, unlinked_only=unlinked)
    return [_invoice_out(inv) for inv in invoices]


@router.post("/finance/payments/{payment_id}/invoices", response=InvoiceUploadOut)
async def upload_payment_invoices(
    request: HttpRequest,
    payment_id: int,
    files: list[UploadedFile] = File(...),
) -> Any:
    """上传发票到某笔收款：逐张识别 → 落盘 → 建 Invoice → 重算开票金额 → 复制进合同文件夹。

    **逐张独立成败**：一张坏文件不能让另外九张白传（律师一次拖十几张是常态）。
    失败项进 `failed[]` 并带原因，成功的照常记账。
    """
    return await _upload_invoices(request, files, payment_id=payment_id)


@router.post("/finance/contracts/{contract_id}/invoices", response=InvoiceUploadOut)
async def upload_contract_invoices(
    request: HttpRequest,
    contract_id: int,
    files: list[UploadedFile] = File(...),
) -> Any:
    """**先开票后付款**：票先挂合同名下，不动开票金额。

    钱到账、记完收款后，前端会把这些票列出来让律师一键关联
    （`POST /finance/invoices/{id}/attach`）。逐张独立成败，口径与收款上传一致。
    """
    return await _upload_invoices(request, files, contract_id=contract_id)


@router.post("/finance/invoices/{invoice_id}/attach", response=InvoiceAttachOut)
async def attach_invoice(request: HttpRequest, invoice_id: int, payload: InvoiceAttachIn) -> Any:
    """把合同挂靠的发票核销到一笔收款（钱到账后的动作），并重算该收款开票金额。"""
    service = _invoice_service()
    ctx = await sync_to_async(extract_request_context)(request)
    invoice, payment = await sync_to_async(service.attach_invoice, thread_sensitive=True)(
        invoice_id=invoice_id,
        payment_id=payload.payment_id,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )
    return InvoiceAttachOut(
        invoice=_invoice_out(invoice),
        invoice_status=payment.invoice_status,
        invoice_status_label=payment.get_invoice_status_display(),
        invoiced_amount=str(payment.invoiced_amount),
    )


@router.delete("/finance/invoices/{invoice_id}")
async def delete_payment_invoice(request: HttpRequest, invoice_id: int) -> Any:
    """删除发票并重算开票金额（media 文件同删；合同文件夹里的副本保留）。"""
    service = _invoice_service()
    ctx = await sync_to_async(extract_request_context)(request)
    return await sync_to_async(service.delete_invoice)(
        invoice_id=invoice_id,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )


@router.post("/finance/invoices/{invoice_id}/copy-to-clipboard", response=InvoiceCopyOut)
async def copy_invoice_to_clipboard(request: HttpRequest, invoice_id: int) -> Any:  # pragma: no cover
    """把**重命名后**的发票复制到系统剪贴板（同 Finder ⌘C，微信 ⌘V 直接粘出文件）。

    与法院短信文书同一套后端落板链路（NSPasteboard file-url）；后端非 macOS /
    无 pyobjc 时返回 unsupported，前端降级复制文件名。
    """
    from apps.core.services.mac_clipboard_service import MacClipboardFileService

    clipboard = MacClipboardFileService()
    if not clipboard.is_available():
        return InvoiceCopyOut(success=False, copied=0, reason="unsupported")

    service = _invoice_service()
    ctx = await sync_to_async(extract_request_context)(request)
    copied = await sync_to_async(service.copy_file_to_clipboard, thread_sensitive=True)(
        invoice_id=invoice_id,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )
    if copied == 0:
        return InvoiceCopyOut(success=False, copied=0, reason="发票文件不存在或写入剪贴板失败")
    return InvoiceCopyOut(success=True, copied=copied, reason=None)


# --------------------------------------------------------------------- 装配 / 映射


def _invoice_service() -> Any:
    from apps.contracts.services.payment.invoice_file_service import InvoiceFileService

    return InvoiceFileService()


async def _upload_invoices(
    request: HttpRequest,
    files: list[UploadedFile],
    *,
    payment_id: int | None = None,
    contract_id: int | None = None,
) -> Any:
    """收款/合同两路上传的公共循环：识别降级存票、逐张独立成败。"""
    from apps.core.exceptions import BusinessException, ValidationException

    if not files:
        raise ValidationException("请选择发票文件", errors={"files": "空"})

    service = _invoice_service()
    ctx = await sync_to_async(extract_request_context)(request)
    recognize = _build_recognizer()

    saved: list[InvoiceOut] = []
    failed: list[InvoiceUploadFailure] = []
    duplicated = 0

    for uploaded in files:
        filename = str(getattr(uploaded, "name", "") or "未命名")
        try:
            parsed = await sync_to_async(recognize)(uploaded)
        except Exception as exc:
            # 识别失败不是上传失败：照常存文件并建记录，只是字段留空让人手填。
            # 发票能否入账取决于有没有这张票，不取决于 OCR 认不认得出来。
            # 注意日志字段别用 `filename`：它是 LogRecord 保留字段，会抛 KeyError。
            logger.warning("invoice_recognize_failed", extra={"invoice_file": filename}, exc_info=exc)
            parsed = None

        try:
            result = await sync_to_async(service.save_invoice, thread_sensitive=True)(
                payment_id=payment_id,
                contract_id=contract_id,
                uploaded_file=uploaded,
                parsed=parsed,
                user=ctx.user,
                org_access=ctx.org_access,
                perm_open_access=ctx.perm_open_access,
            )
        except BusinessException as exc:
            failed.append(InvoiceUploadFailure(filename=filename, reason=str(exc.message)))
            continue
        except Exception:
            logger.error("invoice_upload_failed", extra={"invoice_file": filename}, exc_info=True)
            failed.append(InvoiceUploadFailure(filename=filename, reason="保存失败，请重试"))
            continue

        duplicated += 1 if result.duplicated else 0
        saved.append(_saved_out(result, payment_id=payment_id))

    status = (
        await sync_to_async(service.payment_invoice_state, thread_sensitive=True)(payment_id)
        if payment_id
        else {"": ""}
    )
    return InvoiceUploadOut(
        saved=saved,
        failed=failed,
        invoice_status=status.get("invoice_status", ""),
        invoice_status_label=status.get("invoice_status_label", ""),
        invoiced_amount=status.get("invoiced_amount", ""),
        duplicated_count=duplicated,
    )


def _build_recognizer() -> Any:
    """单文件识别：复用 invoice_recognition 的 QuickRecognitionService（OCR/文本层/正则）。

    失败时抛异常，由调用方降级成「只存文件不填字段」——本函数不吞异常，
    否则「识别不出来」和「识别出空值」在日志里分不开。
    """
    from apps.invoice_recognition.services.wiring import get_quick_recognition_service

    service = get_quick_recognition_service()

    def recognize(uploaded_file: Any) -> Any:
        results = service.recognize_files([uploaded_file])
        if not results:
            return None
        result = results[0]
        if not getattr(result, "success", False) or getattr(result, "data", None) is None:
            raise RuntimeError(str(getattr(result, "error", "") or "识别失败"))
        return result.data

    return recognize


def _invoice_out(invoice: Any) -> InvoiceOut:
    from apps.contracts.services.payment.invoice_file_service import InvoiceFileService

    return InvoiceOut(
        id=invoice.id,
        payment_id=invoice.payment_id,
        original_filename=invoice.original_filename,
        display_filename=InvoiceFileService().display_filename(
            contract_name=_invoice_contract_name(invoice),
            seller=invoice.seller_name or "",
            inv_date=invoice.invoice_date,
            ext=Path(invoice.file_path).suffix.lower(),
        ),
        file_url=f"{_media_url()}{invoice.file_path}",
        invoice_code=invoice.invoice_code or "",
        invoice_number=invoice.invoice_number or "",
        invoice_date=invoice.invoice_date.isoformat() if invoice.invoice_date else None,
        amount=_dec_str(invoice.amount),
        tax_amount=_dec_str(invoice.tax_amount),
        total_amount=_dec_str(invoice.total_amount),
        seller_name=invoice.seller_name or "",
        buyer_name=invoice.buyer_name or "",
        uploaded_at=invoice.uploaded_at.isoformat() if invoice.uploaded_at else "",
    )


def _invoice_contract_name(invoice: Any) -> str:
    """括号命名用的合同名称。调用方须已 select_related("payment__contract", "contract")——
    本函数在 async 视图里跑，懒加载 FK 会抛 SynchronousOnlyOperation。"""
    if invoice.payment_id:
        return str(invoice.payment.contract.name or "")
    return str(invoice.contract.name or "")


def _saved_out(result: Any, *, payment_id: int | None) -> InvoiceOut:
    return InvoiceOut(
        id=result.id,
        payment_id=payment_id,
        original_filename=result.original_filename,
        display_filename=result.stored_filename,
        file_url=result.file_url,
        invoice_code=result.invoice_code,
        invoice_number=result.invoice_number,
        invoice_date=result.invoice_date.isoformat() if isinstance(result.invoice_date, date) else None,
        amount=_dec_str(result.amount),
        tax_amount=_dec_str(result.tax_amount),
        total_amount=_dec_str(result.total_amount),
        seller_name=result.seller_name,
        buyer_name=result.buyer_name,
        uploaded_at="",
    )


def _dec_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(Decimal(str(value)).quantize(Decimal("0.01")))


def _media_url() -> str:
    from django.conf import settings

    return str(settings.MEDIA_URL)
