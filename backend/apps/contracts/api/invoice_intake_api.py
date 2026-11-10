"""发票待认领 API。

挂载：``/api/v1/contracts/finance/invoice-intake``（见 ``apps/contracts/api/__init__.py``）。

四层纪律：本层只做参数提取与响应装配；匹配快照的组装、文件落地与状态机全在
``apps.contracts.services.payment.invoice_intake_service`` 与 ``invoice_intake_scanner``。
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from ninja import Router, Schema

router = Router()

#: 首页卡片最多展示几条（与到账卡同口径）
MAX_PENDING = 50


# ── Schemas ───────────────────────────────────────────────


class InvoiceCandidateOut(Schema):
    contract_id: int
    contract_name: str
    kind: str
    score: float
    reasons: list[str] = []
    caveat: str = ""


class InvoiceExcludedHintOut(Schema):
    contract_id: int
    contract_name: str
    excluded_by: str
    note: str


class PaymentOptionOut(Schema):
    id: int
    amount: str
    received_at: str
    note: str


class InvoiceIntakeOut(Schema):
    id: int
    invoice_number: str
    invoice_date: str | None = None
    total_amount: str | None = None
    buyer_name: str
    project_code: str
    remark: str
    status: str
    status_label: str
    suggested_contract_id: int | None = None
    suggested_contract_name: str | None = None
    suggested_payment_id: int | None = None
    #: 预选收款的确定性（exact / amount_mismatch / ambiguous / no_payment），
    #: 详情里的「收款对照」靠它决定说什么话。
    payment_pick_confidence: str | None = None
    payment_pick_note: str = ""
    #: 该合同下可选的收款列表（详情里做金额对照）。
    #: ⚠️ 这三个字段曾漏定义：前端行组件直接读 payment_options 并 .find()，
    #: 拿到 undefined 就崩，表现为「点详情没反应」（整棵子树被 ErrorBoundary 换掉）。
    payment_options: list[PaymentOptionOut] = []
    confirmed_contract_id: int | None = None
    confirmed_contract_name: str | None = None
    confirmed_payment_id: int | None = None
    invoice_id: int | None = None
    #: 确认后生成的重命名文件名（``发票（合同名）_YYYYMMDD开具.pdf``）。
    #: 首页行内要直接展示并可复制，因此随列表一起下发，不让前端再探一次。
    invoice_display_filename: str = ""
    #: 确认后镜像到合同文件夹的相对落点（未镜像则空串）。详情里展示
    #: 「文件落在哪」，让律师能自己去 Finder 里找到那份副本。
    invoice_folder_subpath: str = ""
    decision_note: str = ""
    candidates: list[InvoiceCandidateOut] = []
    excluded_hints: list[InvoiceExcludedHintOut] = []
    inbox_message_id: int
    subject: str
    sender: str
    #: 附件原始文件名（详情里的「原始文件」块；确认后的展示名另见 invoice_display_filename）
    original_filename: str = ""


class CountOut(Schema):
    count: int


class ConfirmIn(Schema):
    #: 省略 = 采纳系统建议项目
    contract_id: int | None = None
    #: 省略 = 挂合同名下（先开票后付款）/ 采纳系统预选收款
    payment_id: int | None = None
    note: str = ""


class ReasonIn(Schema):
    reason: str = ""


class ActionOut(Schema):
    success: bool
    message: str
    intake_id: int
    status: str
    invoice_id: int | None = None


class ScanOut(Schema):
    scanned: int
    created: int
    days: int


# ── 装配 ──────────────────────────────────────────────────


def _date_str(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _decimal_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def _candidates_of(intake: Any, limit: int | None = 3) -> list[dict[str, Any]]:
    snapshot = intake.match_snapshot or {}
    rows = snapshot.get("candidates") or []
    if limit is not None:
        rows = rows[:limit]
    return [
        {
            "contract_id": row.get("contract_id"),
            "contract_name": row.get("contract_name", ""),
            "kind": row.get("kind", ""),
            "score": float(row.get("score") or 0.0),
            "reasons": row.get("reasons") or [],
            "caveat": row.get("caveat", "") or "",
        }
        for row in rows
    ]


def _hints_of(intake: Any) -> list[dict[str, Any]]:
    snapshot = intake.match_snapshot or {}
    return list(snapshot.get("excluded_hints") or [])


def _payment_options(payment_pick: dict[str, Any]) -> list[dict[str, Any]]:
    """预选快照里的收款选项 → 响应结构（快照缺字段时给空列表，绝不让前端拿到 None）。"""
    rows = payment_pick.get("payment_options") or []
    return [
        {
            "id": int(row.get("id") or 0),
            "amount": str(row.get("amount") or ""),
            "received_at": str(row.get("received_at") or ""),
            "note": str(row.get("note") or ""),
        }
        for row in rows
        if isinstance(row, dict) and row.get("id")
    ]


def _generated_invoice_facts(intake: Any) -> dict[str, str]:
    """确认后那张发票的**展示名 + 文件夹落点**（未确认则两者均空串）。

    展示名走 ``InvoiceFileService.display_filename`` 的同一份命名规则——绝不在这里
    另拼。合同名取**确认到的**合同（可能与建议合同不同：人工改判过）。

    一次查库同时给两个字段：列表只关心文件名，详情还要落点，分两次查是白花。
    """
    blank = {"display_filename": "", "folder_subpath": ""}
    if not intake.invoice_id:
        return blank
    from pathlib import Path

    from apps.contracts.models import Invoice
    from apps.contracts.services.payment.invoice_file_service import InvoiceFileService

    invoice = Invoice.objects.filter(pk=intake.invoice_id).select_related("payment__contract", "contract").first()
    if invoice is None:
        return blank
    contract = invoice.contract or (invoice.payment.contract if invoice.payment_id else None)
    return {
        "display_filename": InvoiceFileService().display_filename(
            contract_name=str(getattr(contract, "name", "") or ""),
            seller=str(invoice.seller_name or ""),
            inv_date=invoice.invoice_date,
            ext=Path(str(invoice.file_path or "")).suffix.lower(),
        ),
        "folder_subpath": str(getattr(invoice, "folder_subpath", "") or ""),
    }


def _to_out(intake: Any, *, limit: int | None = 3) -> dict[str, Any]:
    snapshot = intake.match_snapshot or {}
    payment_pick = snapshot.get("payment_pick") or {}
    generated = _generated_invoice_facts(intake)
    suggested_payment_id = intake.suggested_payment_id
    if suggested_payment_id is None:
        suggested_payment_id = payment_pick.get("suggested_payment_id")

    return {
        "id": intake.pk,
        "invoice_number": intake.invoice_number,
        "invoice_date": _date_str(intake.invoice_date),
        "total_amount": _decimal_str(intake.total_amount),
        "buyer_name": intake.buyer_name,
        "project_code": intake.project_code,
        "remark": intake.remark,
        "status": intake.status,
        "status_label": intake.get_status_display(),
        "suggested_contract_id": intake.suggested_contract_id,
        "suggested_contract_name": getattr(intake.suggested_contract, "name", None),
        "suggested_payment_id": suggested_payment_id,
        "payment_pick_confidence": payment_pick.get("confidence"),
        "payment_pick_note": payment_pick.get("note") or "",
        "payment_options": _payment_options(payment_pick),
        "confirmed_contract_id": intake.confirmed_contract_id,
        "confirmed_contract_name": getattr(intake.confirmed_contract, "name", None),
        "confirmed_payment_id": intake.confirmed_payment_id,
        "invoice_id": intake.invoice_id,
        "invoice_display_filename": generated["display_filename"],
        "invoice_folder_subpath": generated["folder_subpath"],
        "decision_note": intake.decision_note,
        "candidates": _candidates_of(intake, limit=limit),
        "excluded_hints": _hints_of(intake),
        "inbox_message_id": intake.inbox_message_id,
        "subject": getattr(intake.inbox_message, "subject", ""),
        "sender": getattr(intake.inbox_message, "sender", ""),
        "original_filename": intake.original_filename,
    }


# ── 端点 ──────────────────────────────────────────────────


@router.get("/pending", response=list[InvoiceIntakeOut])
def list_pending(request: HttpRequest, limit: int = 20) -> list[Any]:  # pragma: no cover
    """首页卡片：与我相关的**待确认**发票。

    ## 只返回 pending，确认完立刻从这里消失

    「待认领」的意思是“还有事等我做”。处理完的东西就不该留在这里——用户已经
    明确提过一次（“已经处理过的发票为什么还放在前端首页”）。

    曾试过“确认后保留 10 分钟方便复制文件名”，是错的：用界面位置换便利，
    代价是卡片语义不再诚实。想找回已确认的票，走项目页的收款/发票区，
    或将来单独的发票台账——不占「待认领」的位置。
    """
    from apps.contracts.models import InvoiceIntakeStatus
    from apps.contracts.services.payment.invoice_intake_service import visible_intakes_qs

    qs = (
        visible_intakes_qs(request.user)  # type: ignore[attr-defined]
        .filter(status=InvoiceIntakeStatus.PENDING)
        .select_related("suggested_contract", "confirmed_contract", "inbox_message", "inbox_message__source")
        .order_by("-created_at", "-id")[: max(1, min(limit, MAX_PENDING))]
    )
    return [_to_out(intake) for intake in qs]


@router.get("/pending/count", response=CountOut)
def pending_count(request: HttpRequest) -> Any:  # pragma: no cover
    """首页角标（轻量：只 count，不拉快照）。"""
    from apps.contracts.services.payment.invoice_intake_service import open_count

    return {"count": open_count(request.user)}  # type: ignore[attr-defined]


@router.get("/selectable-contracts")
def list_selectable_contracts(request: HttpRequest, search: str = "", limit: int = 50) -> list[Any]:  # pragma: no cover
    """「换个项目」下拉数据源。

    与自动匹配共用同一套资格规则（``intake_eligibility.eligible_contract_qs``）——
    否则会出现"下拉里能选、但自动匹配永远不选"的自相矛盾。
    """
    from apps.contracts.services.payment.intake_service import selectable_contracts

    # exclude_fully_paid=False：与发票匹配器同口径（收满的项目也要能选，
    # 否则“下拉里选不到、自动也不推”的项目就彻底不能开票了）
    rows = selectable_contracts(search=search, exclude_fully_paid=False)[: max(1, min(limit, 100))]
    return [
        {
            "id": contract.pk,
            "name": contract.name,
            "fee_mode": contract.fee_mode,
            "fixed_amount": _decimal_str(contract.fixed_amount),
            "paid_total": _decimal_str(getattr(contract, "paid_total", None)),
            "outstanding_amount": _decimal_str(getattr(contract, "outstanding_amount", None)),
            "expires_note": getattr(contract, "expires_note", ""),
        }
        for contract in rows
    ]


@router.post("/rescan", response=ScanOut)
def rescan(request: HttpRequest, days: int = 60) -> Any:  # pragma: no cover
    """手动补扫近 N 天邮件（幂等）。"""
    from apps.contracts.services.payment.invoice_intake_scanner import scan_since

    return scan_since(days=max(1, min(days, 180)))


@router.get("/{intake_id}", response=InvoiceIntakeOut)
def get_intake(request: HttpRequest, intake_id: int) -> Any:  # pragma: no cover
    """详情：完整候选 + 被排除线索 + 备注原文（limit=None 不裁剪候选）。"""
    from apps.contracts.models import InvoiceIntake
    from apps.contracts.services.payment.invoice_intake_service import can_decide
    from apps.core.exceptions import NotFoundError

    intake = (
        InvoiceIntake.objects.filter(pk=intake_id)
        .select_related("suggested_contract", "confirmed_contract", "inbox_message", "inbox_message__source")
        .first()
    )
    if intake is None or not can_decide(request.user, intake):  # type: ignore[attr-defined]
        raise NotFoundError(f"待认领发票 {intake_id} 不存在")
    return _to_out(intake, limit=None)


@router.post("/{intake_id}/confirm", response=ActionOut)
def confirm_endpoint(request: HttpRequest, intake_id: int, payload: ConfirmIn) -> Any:  # pragma: no cover
    from apps.contracts.services.payment.invoice_intake_service import confirm_invoice_intake

    intake = confirm_invoice_intake(
        intake_id=intake_id,
        contract_id=payload.contract_id,
        payment_id=payload.payment_id,
        user=request.user,  # type: ignore[attr-defined]
        note=payload.note,
    )
    return {
        "success": True,
        "message": "发票已绑定到项目",
        "intake_id": intake.pk,
        "status": intake.status,
        "invoice_id": intake.invoice_id,
    }


@router.post("/{intake_id}/reject", response=ActionOut)
def reject_endpoint(request: HttpRequest, intake_id: int, payload: ReasonIn) -> Any:  # pragma: no cover
    from apps.contracts.services.payment.invoice_intake_service import reject_invoice_intake

    intake = reject_invoice_intake(
        intake_id=intake_id,
        user=request.user,
        reason=payload.reason,  # type: ignore[attr-defined]
    )
    return {
        "success": True,
        "message": "已标记为无关发票",
        "intake_id": intake.pk,
        "status": intake.status,
        "invoice_id": None,
    }


@router.post("/{intake_id}/reopen", response=ActionOut)
def reopen_endpoint(request: HttpRequest, intake_id: int) -> Any:  # pragma: no cover
    from apps.contracts.services.payment.invoice_intake_service import reopen_invoice_intake

    intake = reopen_invoice_intake(intake_id=intake_id, user=request.user)  # type: ignore[attr-defined]
    return {
        "success": True,
        "message": "已撤销，回到待确认",
        "intake_id": intake.pk,
        "status": intake.status,
        "invoice_id": None,
    }
