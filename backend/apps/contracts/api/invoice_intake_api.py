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

    # ── 冲红重开（红字发票）──────────────────────────────
    #: 是否红票。前端据此禁用「一键确认」并换成冲红重开卡
    is_red: bool = False
    #: 被红冲的原蓝票号（红票备注栏「被红冲蓝字数电发票号码」）
    red_against_number: str = ""
    #: 红字发票信息确认单编号
    red_confirmation_no: str = ""
    #: 被冲销的原发票（原票不在本库时为 None）
    offset_invoice: OffsetInvoiceOut | None = None
    #: 我替代了哪条 intake（重开蓝票指向红票）
    supersedes_intake_id: int | None = None
    #: 我被哪条 intake 替代（红票指向重开蓝票）
    superseded_by_intake_id: int | None = None
    #: 冲红重开组（非红票为 None）；装配见 §5.2
    reatch_group: RedGroupOut | None = None


class CountOut(Schema):
    count: int


class OffsetInvoiceOut(Schema):
    """被红票冲销的那张原发票（红票详情/首页对照用）。"""

    id: int
    invoice_number: str
    total_amount: str | None = None
    contract_id: int | None = None
    contract_name: str = ""
    folder_subpath: str = ""


class GroupItemOut(Schema):
    """冲红重开组里的一段（原票 / 红票 / 重开票）。

    两段 id 都可空：原票可能**未落账**（只在 intake 里，甚至完全不在系统里），
    红票在裁定前也还没有 ``invoice_id``，所以不能用 ``int``。
    """

    intake_id: int | None = None
    invoice_id: int | None = None
    invoice_number: str = ""
    total_amount: str | None = None


class RedGroupOut(Schema):
    """「原蓝票 → 红票 → 重开蓝票」三态事务的分组事实。

    只在红票上给：前端按 ``group_key`` 把扁平列表折叠成一张卡。
    """

    group_key: str
    original: GroupItemOut | None = None
    red: GroupItemOut
    reissue: GroupItemOut | None = None


class ConfirmRedReenactIn(Schema):
    """「冲红并确认重开」入参。

    ``new_intake_id`` 省略 = 只冲红不开新票——但那属于误用：真要不重开
    应走 ``confirm-red-only``（语义不同，审计日志也不一样）。
    """

    new_intake_id: int | None = None
    note: str = ""
    #: 重开金额与被冲金额不等时需显式置 True 才放行，并在财务日志里留痕
    amount_override: bool = False


class ConfirmRedOnlyIn(Schema):
    note: str = ""


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
    #: 确认后生成的重命名文件名。确认完那一行会就地换成「文件名 + 复制」形态，
    #: 它需要这个名字才能展示与兑底复制——不让前端自己拼命名规则。
    invoice_display_filename: str = ""


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


def _offset_invoice_out(intake: Any) -> dict[str, Any] | None:
    """红票 → 它冲销的那张原发票（未落库或非红票给 None）。"""
    invoice = getattr(intake, "offset_invoice", None)
    if invoice is None:
        return None
    payment = getattr(invoice, "payment", None)
    contract = getattr(invoice, "contract", None) or (getattr(payment, "contract", None) if payment else None)
    return {
        "id": invoice.pk,
        "invoice_number": invoice.invoice_number,
        "total_amount": _decimal_str(invoice.total_amount),
        "contract_id": getattr(contract, "pk", None),
        "contract_name": getattr(contract, "name", "") or "",
        "folder_subpath": str(getattr(invoice, "folder_subpath", "") or ""),
    }


def _group_item_out(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {
        "intake_id": item.get("intake_id"),
        "invoice_id": item.get("invoice_id"),
        "invoice_number": item.get("invoice_number") or "",
        "total_amount": item.get("total_amount"),
    }


def _red_group_out(group: dict[str, Any] | None) -> dict[str, Any] | None:
    """Service 给出的组事实 → 响应结构。

    ``red`` 段是契约里唯一的必填段：一条组存在的前提就是「这张是红票」，
    所以 Service 永远不会给出缺 ``red`` 的组；这里仍做空值兜底，
    免得一个装配 bug 把整个列表打成 500。
    """
    if group is None or group.get("red") is None:
        return None
    return {
        "group_key": group.get("group_key") or "",
        "original": _group_item_out(group.get("original")),
        "red": _group_item_out(group.get("red")),
        "reissue": _group_item_out(group.get("reissue")),
    }


def _to_out(intake: Any, *, limit: int | None = 3, reatch_group: dict[str, Any] | None = None) -> dict[str, Any]:
    snapshot = intake.match_snapshot or {}
    payment_pick = snapshot.get("payment_pick") or {}
    from apps.contracts.services.payment.invoice_intake_service import generated_invoice_facts

    generated = generated_invoice_facts(intake)
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
        "is_red": bool(getattr(intake, "is_red", False)),
        "red_against_number": str(getattr(intake, "red_against_number", "") or ""),
        "red_confirmation_no": str(getattr(intake, "red_confirmation_no", "") or ""),
        "offset_invoice": _offset_invoice_out(intake),
        "supersedes_intake_id": getattr(intake, "supersedes_intake_id", None),
        "superseded_by_intake_id": getattr(intake, "superseded_by_intake_id", None),
        "reatch_group": _red_group_out(reatch_group),
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
    from apps.contracts.services.payment.invoice_intake_service import red_group_facts, visible_intakes_qs

    qs = list(
        visible_intakes_qs(request.user)
        .filter(status=InvoiceIntakeStatus.PENDING)
        .select_related(
            "suggested_contract",
            "confirmed_contract",
            "inbox_message",
            "inbox_message__source",
            # 红票两个 FK 必须预取：首页一次 50 行逐行惰性查询会放大成 100 次
            "offset_invoice",
            "offset_invoice__contract",
            "offset_invoice__payment__contract",
            "supersedes_intake",
        )
        .order_by("-created_at", "-id")[: max(1, min(limit, MAX_PENDING))]
    )
    groups = red_group_facts(qs)
    return [_to_out(intake, reatch_group=groups.get(intake.pk)) for intake in qs]


@router.get("/pending/count", response=CountOut)
def pending_count(request: HttpRequest) -> Any:  # pragma: no cover
    """首页角标（轻量：只 count，不拉快照）。"""
    from apps.contracts.services.payment.invoice_intake_service import open_count

    return {"count": open_count(request.user)}


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
    from apps.contracts.services.payment.invoice_intake_service import get_intake_for_user, red_group_facts

    intake = get_intake_for_user(intake_id=intake_id, user=request.user)
    groups = red_group_facts([intake])
    return _to_out(intake, limit=None, reatch_group=groups.get(intake.pk))


@router.post("/{intake_id}/confirm", response=ActionOut)
def confirm_endpoint(request: HttpRequest, intake_id: int, payload: ConfirmIn) -> Any:  # pragma: no cover
    """确认绑定（蓝票走这里）。

    ## 红票不得从老端点进

    红票的语义是「抵掉一张已存在的票」，不是「新增一笔开票」：走 ``confirm``
    会生成一张金额为负、没有原票关联的 ``Invoice``，账上就多出一张孤立红票。
    因此在此硬拦——必须走 ``confirm-red-reenact`` / ``confirm-red-only``。
    """
    from apps.contracts.services.payment.invoice_intake_service import confirm_invoice_intake, get_intake_for_user
    from apps.core.exceptions import ValidationException

    intake = get_intake_for_user(intake_id=intake_id, user=request.user)
    if intake.is_red:
        raise ValidationException(
            "红字发票请使用「冲红重开」或「仅冲红」入口处理，不能直接确认",
            code="INVOICE_RED_USE_DEDICATED_ENDPOINT",
        )

    intake = confirm_invoice_intake(
        intake_id=intake_id,
        contract_id=payload.contract_id,
        payment_id=payload.payment_id,
        user=request.user,
        note=payload.note,
    )
    from apps.contracts.services.payment.invoice_intake_service import generated_invoice_facts

    generated = generated_invoice_facts(intake)
    return {
        "success": True,
        "message": "发票已绑定到项目",
        "intake_id": intake.pk,
        "status": intake.status,
        "invoice_id": intake.invoice_id,
        "invoice_display_filename": generated["display_filename"],
    }


@router.post("/{intake_id}/confirm-red-reenact", response=ActionOut)
def confirm_red_reenact_endpoint(  # pragma: no cover
    request: HttpRequest, intake_id: int, payload: ConfirmRedReenactIn
) -> Any:
    """一次裁定完成「冲红 + 重开」：红票冲原票，新蓝票替代原票入账。"""
    from apps.contracts.services.payment.invoice_intake_service import confirm_red_reenact, generated_invoice_facts

    result = confirm_red_reenact(
        red_intake_id=intake_id,
        new_intake_id=payload.new_intake_id,
        user=request.user,
        note=payload.note,
        amount_override=payload.amount_override,
    )
    red_intake = result["red_intake"]
    return {
        "success": True,
        "message": "已冲红并确认重开",
        "intake_id": red_intake.pk,
        "status": red_intake.status,
        "invoice_id": red_intake.invoice_id,
        "invoice_display_filename": generated_invoice_facts(red_intake)["display_filename"],
    }


@router.post("/{intake_id}/confirm-red-only", response=ActionOut)
def confirm_red_only_endpoint(
    request: HttpRequest, intake_id: int, payload: ConfirmRedOnlyIn
) -> Any:  # pragma: no cover
    """只冲红不重开（客户不要这张票了）。

    与 ``confirm-red-reenact`` 分开一个端点而不是用可选参数区分：两条路径的
    审计日志动作名、允许的前置条件都不同，混在一个入口里迟早会被误调。
    """
    from apps.contracts.services.payment.invoice_intake_service import confirm_red_only, generated_invoice_facts

    result = confirm_red_only(red_intake_id=intake_id, user=request.user, note=payload.note)
    red_intake = result["red_intake"]
    return {
        "success": True,
        "message": "已冲红（未重开）",
        "intake_id": red_intake.pk,
        "status": red_intake.status,
        "invoice_id": red_intake.invoice_id,
        "invoice_display_filename": generated_invoice_facts(red_intake)["display_filename"],
    }


@router.post("/{intake_id}/reparse", response=ActionOut)
def reparse_endpoint(request: HttpRequest, intake_id: int) -> Any:  # pragma: no cover
    """重解析这张发票（补金额与红票事实，用于历史脏数据修复）。"""
    from apps.contracts.services.payment.invoice_intake_service import generated_invoice_facts, reparse_invoice_intake

    intake = reparse_invoice_intake(intake_id=intake_id, user=request.user)
    return {
        "success": True,
        "message": "已重新解析",
        "intake_id": intake.pk,
        "status": intake.status,
        "invoice_id": intake.invoice_id,
        "invoice_display_filename": generated_invoice_facts(intake)["display_filename"],
    }


@router.post("/{intake_id}/reject", response=ActionOut)
def reject_endpoint(request: HttpRequest, intake_id: int, payload: ReasonIn) -> Any:  # pragma: no cover
    from apps.contracts.services.payment.invoice_intake_service import reject_invoice_intake

    intake = reject_invoice_intake(
        intake_id=intake_id,
        user=request.user,
        reason=payload.reason,
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

    intake = reopen_invoice_intake(intake_id=intake_id, user=request.user)
    return {
        "success": True,
        "message": "已撤销，回到待确认",
        "intake_id": intake.pk,
        "status": intake.status,
        "invoice_id": None,
    }
