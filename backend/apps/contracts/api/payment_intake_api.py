"""到账待认领 API。

挂载：``/api/v1/finance/intake``（见 apiSystem/apiSystem/api.py 的 add_router）。

四层纪律：本层只做参数提取与响应装配，业务在
``apps.contracts.services.payment.intake_service``。
"""

from __future__ import annotations

from typing import Any

from asgiref.sync import sync_to_async
from django.http import HttpRequest
from ninja import Router, Schema

router = Router()


# ── Schemas ───────────────────────────────────────────────


class IntakeCandidateOut(Schema):
    contract_id: int
    contract_name: str
    kind: str
    score: float
    reasons: list[str] = []
    outstanding_amount: str | None = None
    fee_mode: str = ""
    caveat: str = ""


class ExcludedHintOut(Schema):
    contract_id: int
    contract_name: str
    excluded_by: str
    note: str


class IntakeOut(Schema):
    id: int
    amount: str
    received_at: str
    payer_name: str
    on_behalf_of: str
    display_payer: str
    status: str
    status_label: str
    bank_remark: str
    suggested_contract_id: int | None = None
    suggested_contract_name: str | None = None
    confirmed_contract_id: int | None = None
    confirmed_contract_name: str | None = None
    payment_id: int | None = None
    decision_note: str = ""
    # 首页窄栏只放前 3 个；详情用 IntakeDetailOut 拿全量
    candidates: list[IntakeCandidateOut] = []
    excluded_hints: list[ExcludedHintOut] = []
    inbox_message_id: int
    subject: str = ""
    sender: str = ""


class IntakeCountOut(Schema):
    count: int


class SelectableContractOut(Schema):
    id: int
    name: str
    fee_mode: str
    fixed_amount: str | None = None
    paid_total: str | None = None
    outstanding_amount: str | None = None
    expires_note: str = ""


class ConfirmIn(Schema):
    contract_id: int | None = None
    note: str = ""


class ReasonIn(Schema):
    reason: str = ""


class ActionOut(Schema):
    success: bool = True
    message: str = ""
    intake_id: int
    status: str
    payment_id: int | None = None


class ScanOut(Schema):
    scanned: int
    created: int
    skipped: int
    days: int


class RematchOut(Schema):
    updated: int
    failed: int


# ── Helpers ───────────────────────────────────────────────


def _candidates_of(intake: Any, limit: int | None = None) -> list[dict[str, Any]]:
    rows = intake.top_candidates(limit) if limit else (intake.match_snapshot or {}).get("candidates") or []
    return [c for c in rows if isinstance(c, dict)]


def _hints_of(intake: Any) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = intake.excluded_hints()
    return hints


def _to_out(intake: Any, *, with_candidates: bool = True, limit: int | None = 3) -> dict[str, Any]:
    message = intake.inbox_message
    source = getattr(message, "source", None) if message else None
    return {
        "id": intake.pk,
        "amount": str(intake.amount),
        "received_at": intake.received_at.isoformat(),
        "payer_name": intake.payer_name,
        "on_behalf_of": intake.on_behalf_of,
        "display_payer": intake.display_payer,
        "status": intake.status,
        "status_label": intake.get_status_display(),
        "bank_remark": intake.bank_remark,
        "suggested_contract_id": intake.suggested_contract_id,
        "suggested_contract_name": (intake.suggested_contract.name if intake.suggested_contract else None),
        "confirmed_contract_id": intake.confirmed_contract_id,
        "confirmed_contract_name": (intake.confirmed_contract.name if intake.confirmed_contract else None),
        "payment_id": intake.payment_id,
        "decision_note": intake.decision_note,
        "candidates": _candidates_of(intake, limit) if with_candidates else [],
        "excluded_hints": _hints_of(intake),
        "inbox_message_id": message.pk if message else 0,
        "subject": (message.subject if message else "") or "",
        "sender": (message.sender if message else "") or "",
    }


# ── Endpoints ─────────────────────────────────────────────


@router.get("/pending", response=list[IntakeOut])
def list_pending(request: HttpRequest, limit: int = 20) -> list[Any]:  # pragma: no cover
    """首页「待认领款项」模块：与我相关、待确认的到账。

    按「与我相关」收敛（收件人 / 主办律师 / 管理员），见 intake_service 模块文档。
    """
    from apps.contracts.models import IntakeStatus
    from apps.contracts.services.payment.intake_service import visible_intakes_qs

    qs = visible_intakes_qs(request.user).filter(status=IntakeStatus.PENDING)[: max(1, min(limit, 100))]
    return [_to_out(x) for x in qs]


@router.get("/pending/count", response=IntakeCountOut)
def pending_count(request: HttpRequest) -> Any:  # pragma: no cover
    """首页角标：待确认条数（轻量，不拉全量）。"""
    from apps.contracts.services.payment.intake_service import open_count

    return {"count": open_count(request.user)}


# ⚠️ 静态路径必须在 `/{intake_id}` **之前**注册：Django 路由按注册顺序匹配，
# 晚注册会被通配 `{intake_id}` 吃掉（症状是 422 int_parsing，把一个字符串当成 int）。


@router.get("/selectable-contracts", response=list[SelectableContractOut])
def list_selectable_contracts(request: HttpRequest, search: str = "", limit: int = 50) -> list[Any]:  # pragma: no cover
    """「换个项目」下拉数据源：所有**合格**在办项目（与自动匹配同一套资格规则）。

    不合格（已收满/已归档/案件全结案）的项目不会出现在这里，避免用户选到
    系统永远不推荐的项目。
    """
    from apps.contracts.services.payment.intake_service import selectable_contracts

    rows = []
    for contract in selectable_contracts(search=search)[: max(1, min(limit, 200))]:
        fixed = contract.fixed_amount
        paid = getattr(contract, "paid_total", None)
        outstanding = None
        if fixed is not None and paid is not None:
            outstanding = str(fixed - paid)
        expires_note = ""
        if getattr(contract, "end_date", None) is not None:
            from django.utils import timezone

            end = contract.end_date
            # 到期项目仍可选（顾问续费打款），但标注出来
            if end is not None and end < timezone.localdate():
                expires_note = f"已于 {end.isoformat()} 到期"
        rows.append(
            {
                "id": contract.pk,
                "name": contract.name,
                "fee_mode": str(contract.fee_mode or ""),
                "fixed_amount": str(fixed) if fixed is not None else None,
                "paid_total": str(paid) if paid is not None else None,
                "outstanding_amount": outstanding,
                "expires_note": expires_note,
            }
        )
    return rows


@router.post("/rescan", response=ScanOut)
def rescan(request: HttpRequest, days: int = 14) -> Any:  # pragma: no cover
    """手动补扫近 N 天的邮件（默认 14 天）。

    用户前两周才开始让财务发到账通知，更早的邮件没有到账通知形态的内容。
    """
    from apps.contracts.services.payment.intake_scanner import scan_since

    return scan_since(days=max(1, min(days, 90)))


@router.post("/rematch", response=RematchOut)
def rematch(request: HttpRequest) -> Any:  # pragma: no cover
    """按当前匹配器逻辑重算所有**待确认**记录的候选快照。

    为什么需要手动触发：match_snapshot 是扫描当时的不可变快照，匹配器改进后
    存量记录不会自动更新。已确认/已关闭的记录不动——那是审计凭证。
    """
    from apps.contracts.services.payment.intake_scanner import rematch_all_pending

    return rematch_all_pending()


@router.get("/{intake_id}", response=IntakeOut)
def get_intake(request: HttpRequest, intake_id: int) -> Any:  # pragma: no cover
    """详情：完整候选 + 被排除线索 + 银行备注原文。"""
    from apps.contracts.services.payment.intake_service import visible_intakes_qs
    from apps.core.exceptions import NotFoundError

    intake = visible_intakes_qs(request.user).filter(pk=intake_id).first()
    if intake is None:
        raise NotFoundError(f"待认领款项 {intake_id} 不存在")
    return _to_out(intake, with_candidates=True, limit=None)


@router.post("/{intake_id}/confirm", response=ActionOut)
def confirm_intake_endpoint(request: HttpRequest, intake_id: int, payload: ConfirmIn) -> Any:  # pragma: no cover
    """确认归属并写入收款记录。

    ``contract_id`` 省略即采纳系统建议；传入即人工改判。
    """
    from apps.contracts.services.payment.intake_service import confirm_intake

    intake = confirm_intake(intake_id=intake_id, contract_id=payload.contract_id, user=request.user, note=payload.note)
    return {
        "success": True,
        "message": "已确认并写入收款记录",
        "intake_id": intake.pk,
        "status": intake.status,
        "payment_id": intake.payment_id,
    }


@router.post("/{intake_id}/reject", response=ActionOut)
def reject_intake_endpoint(request: HttpRequest, intake_id: int, payload: ReasonIn) -> Any:  # pragma: no cover
    """标记为「非记账事件」。"""
    from apps.contracts.services.payment.intake_service import reject_intake

    intake = reject_intake(intake_id=intake_id, user=request.user, reason=payload.reason)
    return {
        "success": True,
        "message": "已标记为非记账事件",
        "intake_id": intake.pk,
        "status": intake.status,
        "payment_id": None,
    }


@router.post("/{intake_id}/ignore", response=ActionOut)
def ignore_intake_endpoint(request: HttpRequest, intake_id: int, payload: ReasonIn) -> Any:  # pragma: no cover
    """标记为「不需记账」（往来款/退款）。"""
    from apps.contracts.services.payment.intake_service import ignore_intake

    intake = ignore_intake(intake_id=intake_id, user=request.user, reason=payload.reason)
    return {
        "success": True,
        "message": "已标记为不需记账",
        "intake_id": intake.pk,
        "status": intake.status,
        "payment_id": None,
    }


@router.post("/{intake_id}/reopen", response=ActionOut)
def reopen_intake_endpoint(request: HttpRequest, intake_id: int) -> Any:  # pragma: no cover
    """撤销裁定回到待确认（已确认的会同时删除生成的收款记录）。"""
    from apps.contracts.services.payment.intake_service import reopen_intake

    intake = reopen_intake(intake_id=intake_id, user=request.user)
    return {
        "success": True,
        "message": "已撤销，回到待确认",
        "intake_id": intake.pk,
        "status": intake.status,
        "payment_id": None,
    }
