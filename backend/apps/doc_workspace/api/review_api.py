"""审查接口：发起轮次、看清单、逐条/批量决策、出一页纸。

**所有端点都不产生第二份 docx**：结论要么变成修订、要么变成批注，落在**原文件**上。
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any

from django.http import HttpRequest
from ninja import Router, Schema

from apps.core.security.auth import JWTOrSessionAuth

from ..models import (
    Consequence,
    Delivery,
    Finding,
    FindingKind,
    FindingStatus,
    RejectReason,
    ReviewRun,
    RiskSource,
    RuleClass,
    RunStatus,
    Severity,
    SourceWeight,
    Stage,
    Stance,
    Verdict,
)
from ..services import queries, review_model, review_pipeline

logger = logging.getLogger(__name__)

router = Router(tags=["文档工作面"], auth=JWTOrSessionAuth())


class DocStartReviewIn(Schema):
    kind: str
    owner_id: int
    subpath: str
    stance: str = Stance.NEUTRAL
    contract_type: str = ""
    playbook_id: int | None = None


class DocStartReviewOut(Schema):
    run_id: int
    status: str
    queued: bool
    hint: str = ""


class DocFindingOut(Schema):
    id: int
    ordinal: int
    verdict: str
    severity: str
    kind: str
    clause_type: str
    rule_key: str
    rule_class: str = ""
    stage: str = ""
    risk_source: str = ""
    source_weight: str = ""
    consequence: str = ""
    case_ref: str = ""
    legal_basis: str
    quote: str
    title: str
    reason: str
    suggestion_original: str
    suggestion_replacement: str
    suggestion_note: str
    delivery: str
    status: str
    reject_reason_code: str
    reject_note: str
    docx_rev_ids: list[int] = []
    comment_ids: list[int] = []


class DocReviewRunOut(Schema):
    id: int
    owner_kind: str
    owner_id: int
    subpath: str
    stance: str
    contract_type: str
    status: str
    playbook_key: str
    playbook_version: int | None = None
    summary: dict[str, Any] = {}
    error_message: str = ""
    created_at: datetime
    finished_at: datetime | None = None
    findings: list[DocFindingOut] = []


class DocDecideIn(Schema):
    action: str
    """`accept`（落笔并采纳）| `reject` | `moot` | `stale`"""

    reason_code: str = ""
    note: str = ""


class DocDecideOut(Schema):
    ok: bool
    status: str = ""
    reason: str = ""
    stale: bool = False
    rev_ids: list[int] = []
    comment_ids: list[int] = []


class DocBulkAcceptIn(Schema):
    severity: str = ""
    """只采纳该严重度的结论（`high`/`medium`/`low`）；留空 = 全部待决。"""

    kinds: list[str] = []
    confirm: bool = False
    """必须显式传 true。批量采纳是**不可撤销**的（落笔即写文件），
    没有这道确认就等于给律师一个一键改坏文件的按钮。"""


class DocBulkAcceptOut(Schema):
    accepted: int
    stale: int
    failed: int
    details: list[dict[str, Any]] = []


def _finding_out(f: Finding) -> DocFindingOut:
    return DocFindingOut(
        id=f.id,
        ordinal=f.ordinal,
        verdict=f.verdict,
        severity=f.severity,
        kind=f.kind,
        clause_type=f.clause_type,
        rule_key=f.rule_key,
        rule_class=str(f.rule_class),
        stage=str(f.stage),
        risk_source=str(f.risk_source),
        source_weight=str(f.source_weight),
        consequence=str(f.consequence),
        case_ref=f.case_ref,
        legal_basis=f.legal_basis,
        quote=f.quote,
        title=f.title,
        reason=f.reason,
        suggestion_original=f.suggestion_original,
        suggestion_replacement=f.suggestion_replacement,
        suggestion_note=f.suggestion_note,
        delivery=f.delivery,
        status=f.status,
        reject_reason_code=f.reject_reason_code,
        reject_note=f.reject_note,
        docx_rev_ids=list(f.docx_rev_ids or []),
        comment_ids=list(f.comment_ids or []),
    )


def _run_out(run: ReviewRun, *, with_findings: bool = True) -> DocReviewRunOut:
    findings = [_finding_out(f) for f in run.findings.all()] if with_findings else []
    return DocReviewRunOut(
        id=run.id,
        owner_kind=run.owner_kind,
        owner_id=run.owner_id,
        subpath=run.subpath,
        stance=run.stance,
        contract_type=run.contract_type,
        status=run.status,
        playbook_key=run.playbook_key,
        playbook_version=run.playbook_version,
        summary=dict(run.summary or {}),
        error_message=run.error_message,
        created_at=run.created_at,
        finished_at=run.finished_at,
        findings=findings,
    )


def _dispatch(run_id: int) -> tuple[bool, str]:
    """把执行丢给后台；队列没起来就退回线程，绝不让轮次永远卡在 queued。"""
    try:
        from apps.core.tasking import submit_task

        submit_task(
            "apps.doc_workspace.tasks.execute_review_run",
            run_id,
            task_name=f"doc_review_{run_id}",
            timeout=600,
        )
        return True, ""
    except (ImportError, RuntimeError, OSError, ValueError):
        # django-q 不可用时（未起 qcluster / 配置缺失）退回线程，别让轮次永远停在 queued
        logger.warning("审查任务入队失败，退回线程执行: run=%s", run_id, exc_info=True)

    def _worker() -> None:
        from django.db import connections

        try:
            from ..tasks import execute_review_run

            execute_review_run(run_id)
        finally:
            # 子线程自带连接，不关会卡住测试库/连接的回收
            connections.close_all()

    threading.Thread(target=_worker, name=f"doc-review-{run_id}", daemon=True).start()
    return False, "后台队列未启动，已改用线程执行（关掉进程会中断本次审查）"


@router.post("/review/runs", response=DocStartReviewOut, summary="发起一轮审查（异步）")
def start_review(request: HttpRequest, payload: DocStartReviewIn) -> Any:
    """建轮次 → 丢后台。立刻返回 `run_id`，前端据此轮询状态。

    **不产生第二份 docx**：轮次只是「一次审查动作」，内容仍然是文件夹里那份文件。
    """
    user = getattr(request, "auth", None)
    playbook = queries.get_playbook(payload.playbook_id) if payload.playbook_id else None

    run = review_pipeline.create_run(
        kind=payload.kind,
        owner_id=payload.owner_id,
        subpath=payload.subpath,
        stance=payload.stance,
        contract_type=payload.contract_type,
        playbook=playbook,
        user=user,
        org_access=getattr(user, "org_access", None),
    )
    queued, hint = _dispatch(run.id)
    return DocStartReviewOut(run_id=run.id, status=run.status, queued=queued, hint=hint)


@router.get("/review/runs/latest", response=DocReviewRunOut, summary="该文件最近一轮审查（含清单）")
def latest_run(request: HttpRequest, kind: str, owner_id: int, subpath: str) -> Any:
    run = queries.latest_run(kind=kind, owner_id=owner_id, subpath=subpath)
    if run is None:
        return DocReviewRunOut(
            id=0,
            owner_kind=kind,
            owner_id=owner_id,
            subpath=subpath,
            stance=Stance.NEUTRAL,
            contract_type="",
            status="none",
            playbook_key="",
            created_at=datetime.now(),
        )
    return _run_out(run)


@router.get("/review/runs/{run_id}", response=DocReviewRunOut, summary="轮次详情（含清单）")
def get_run(request: HttpRequest, run_id: int) -> Any:
    run = queries.get_run(run_id)
    if run is None:
        return DocReviewRunOut(
            id=0,
            owner_kind="",
            owner_id=0,
            subpath="",
            stance="",
            contract_type="",
            status="not_found",
            playbook_key="",
            created_at=datetime.now(),
        )
    return _run_out(run)


@router.post("/review/findings/{finding_id}/decide", response=DocDecideOut, summary="逐条决策（采纳即落笔）")
def decide_finding(request: HttpRequest, finding_id: int, payload: DocDecideIn) -> Any:
    """`accept` 会**真的改文件**（修订 / 批注）；`reject` / `moot` 只改状态。

    锚点失效时返回 `stale=true` 且文件零改动——绝不降级成「改到最像的那一段」。
    """
    user = getattr(request, "auth", None)
    finding = queries.get_finding(finding_id)
    if finding is None:
        return DocDecideOut(ok=False, reason="结论不存在")

    if payload.action == "accept":
        result = review_model.apply_finding(finding, user=user, org_access=getattr(user, "org_access", None))
        finding.refresh_from_db()
        return DocDecideOut(
            ok=bool(result.get("applied")),
            status=str(finding.status),
            reason=str(result.get("reason") or ""),
            stale=bool(result.get("stale")),
            rev_ids=list(result.get("rev_ids") or []),
            comment_ids=list(result.get("comment_ids") or []),
        )

    if payload.action == "reject":
        if not payload.reason_code:
            # 在接口层就挡住：自由文本驳回没法统计误报率，而 500 对前端毫无信息量
            return DocDecideOut(ok=False, reason="驳回必须给理由码（reason_code）")
        review_model.reject(finding, reason_code=payload.reason_code, note=payload.note, user=user)
    elif payload.action == "moot":
        review_model.mark_moot(finding, user=user)
    elif payload.action == "stale":
        review_model.mark_stale(finding)
    else:
        return DocDecideOut(ok=False, reason=f"未知动作：{payload.action}")

    finding.refresh_from_db()
    return DocDecideOut(ok=True, status=str(finding.status))


@router.post("/review/runs/{run_id}/bulk-accept", response=DocBulkAcceptOut, summary="按严重度批量采纳（不可撤销）")
def bulk_accept(request: HttpRequest, run_id: int, payload: DocBulkAcceptIn) -> Any:
    """批量采纳。**必须显式 `confirm=true`**：落笔即写文件，撤销要走版本回滚。"""
    if not payload.confirm:
        return DocBulkAcceptOut(accepted=0, stale=0, failed=0, details=[{"reason": "缺少 confirm=true"}])

    user = getattr(request, "auth", None)
    run = queries.get_run(run_id)
    if run is None:
        return DocBulkAcceptOut(accepted=0, stale=0, failed=0, details=[{"reason": "轮次不存在"}])

    targets = queries.proposed_findings(run, severity=payload.severity, kinds=payload.kinds)

    accepted = stale = failed = 0
    details: list[dict[str, Any]] = []
    for finding in targets:
        result = review_model.apply_finding(finding, user=user, org_access=getattr(user, "org_access", None))
        if result.get("applied"):
            accepted += 1
        elif result.get("stale"):
            stale += 1
        else:
            failed += 1
        details.append({"id": finding.id, "applied": bool(result.get("applied")), "reason": result.get("reason", "")})

    return DocBulkAcceptOut(accepted=accepted, stale=stale, failed=failed, details=details)


@router.post("/review/runs/{run_id}/report", summary="一页纸（Top-3，带量化后果）")
def build_report(request: HttpRequest, run_id: int) -> dict[str, str]:
    run = queries.get_run(run_id)
    if run is None:
        return {"markdown": "", "reason": "轮次不存在"}
    return {"markdown": review_pipeline.build_top_report(run)}


@router.get("/review/meta", summary="枚举字典（前端下拉与筛选用）")
def review_meta(request: HttpRequest) -> dict[str, Any]:
    """把枚举一次性给前端，避免前后端各写一份字符串常量然后漂移。"""
    return {
        "verdict": [{"value": v, "label": l} for v, l in Verdict.choices],
        "severity": [{"value": v, "label": l} for v, l in Severity.choices],
        "kind": [{"value": v, "label": l} for v, l in FindingKind.choices],
        "delivery": [{"value": v, "label": l} for v, l in Delivery.choices],
        "status": [{"value": v, "label": l} for v, l in FindingStatus.choices],
        "reject_reason": [{"value": v, "label": l} for v, l in RejectReason.choices],
        "stance": [{"value": v, "label": l} for v, l in Stance.choices],
        "run_status": [{"value": v, "label": l} for v, l in RunStatus.choices],
        "rule_class": [{"value": v, "label": l} for v, l in RuleClass.choices],
        "stage": [{"value": v, "label": l} for v, l in Stage.choices],
        "risk_source": [{"value": v, "label": l} for v, l in RiskSource.choices],
        "source_weight": [{"value": v, "label": l} for v, l in SourceWeight.choices],
        "consequence": [{"value": v, "label": l} for v, l in Consequence.choices],
    }
