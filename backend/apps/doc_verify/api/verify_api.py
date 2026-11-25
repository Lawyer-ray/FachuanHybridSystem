"""回传件核对 API（挂载前缀 `/api/v1/doc-verify`，见 `apiSystem/apiSystem/api.py`）。

本层只做参数提取与装配：解码、ORM 查询、状态推导、裁决校验全部在
`apps.doc_verify.services.verify` 里。错误一律用仓库既有异常族，
由全局处理器翻成 400/403/404——不在这里吞异常、也不在这里编状态码。

`request` 即使不用也必须写在第一位：Ninja 按位置把请求对象传给处理函数，
删掉它会被当成第一个业务参数（实测 `TypeError: got multiple values for argument`）。
"""

from __future__ import annotations

from typing import Any

from ninja import Router

from apps.cases.services.case.case_visibility import can_access_case
from apps.core.exceptions import PermissionDenied, ValidationException
from apps.doc_verify.schemas import (
    DecisionBatchIn,
    DecisionBatchOut,
    DecisionIn,
    DecisionOut,
    RunFromMaterialIn,
    RunPageOut,
    VerifyRunIn,
    VerifyRunOut,
)
from apps.doc_verify.services.verify import decision as decision_service
from apps.doc_verify.services.verify import from_material as from_material_service
from apps.doc_verify.services.verify import query as query_service
from apps.doc_verify.services.verify import run as run_service

router = Router(tags=["回传件核对"])


def _assert_case_visible(operator: Any, case_id: int | None) -> None:
    """案件级可见性：没绑案件的基线（合同/通用文书）不设案件限制。"""
    if case_id is None:
        return
    if not can_access_case(operator, case_id):
        raise PermissionDenied(message="无权访问该案件", code="CASE_FORBIDDEN", errors={"case_id": case_id})


def _require_operator(request: Any) -> Any:
    """裁决必须落到人头上。

    Ninja 认证的结果在 `request.auth`（JWT/会话都写这里），`request.user` 是
    AuthenticationMiddleware 留下的对象——两者都拿不到（或都是匿名）就拒绝：
    没有裁决人的「放行」在出事时无法证明律师看过。
    """
    for candidate in (getattr(request, "auth", None), getattr(request, "user", None)):
        if candidate is not None and getattr(candidate, "is_authenticated", False):
            return candidate
    raise PermissionDenied(message="无法确认裁决人身份，裁决必须留痕", code="DECISION_OPERATOR_REQUIRED")


@router.post("/runs", response=VerifyRunOut)
def create_run(request: Any, payload: VerifyRunIn) -> dict[str, Any]:
    """提交一份回传件跑核对（幂等：同一基线 + 同字节重复提交返回同一行）。"""
    operator = _require_operator(request)
    data = run_service.decode_inbound_payload(payload.file_base64)
    artifact = query_service.get_artifact(payload.artifact_id)
    _assert_case_visible(operator, artifact.case_id)
    run = run_service.verify_inbound(
        artifact=artifact,
        data=data,
        file_name=payload.file_name,
        source_message_id=payload.source_message_id,
        tier=payload.tier,
    )
    return query_service.run_detail(run)


@router.post("/runs/from-material", response=VerifyRunOut)
def create_run_from_material(request: Any, payload: RunFromMaterialIn) -> dict[str, Any]:
    """用收件箱里已有的附件跑核对：字节由服务端取，前端不必上传整本 PDF。

    参数顺序与 `POST /runs` 一致：基线 404 → 案件不可见 403 → 附件拿不到 404。
    附件取不到是**数据状态**（消息/part_index/字节不在），不是服务端故障。
    """
    operator = _require_operator(request)
    artifact = query_service.get_artifact(payload.artifact_id)
    _assert_case_visible(operator, artifact.case_id)
    run = from_material_service.verify_from_material(
        artifact=artifact,
        message_id=payload.message_id,
        part_index=payload.part_index,
        tier=payload.tier,
        operator=operator,
    )
    return query_service.run_detail(run)


@router.get("/runs", response=RunPageOut)
def list_runs(
    request: Any,
    case_id: int,
    state: str = "",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """该案的全部核对历史（含已裁决的），按 -created_at,-id 分页。

    与 `/unverified` 的分工：那边是「现在还有几条要人看」，这里是「这案核过几次、
    结论怎么变」——历史必须含已裁决的，否则律师看不到结论是被谁翻过来的。
    """
    operator = _require_operator(request)
    _assert_case_visible(operator, case_id)
    return query_service.list_case_runs(case_id=case_id, state=state or None, limit=limit, offset=offset)


@router.get("/runs/{run_id}", response=VerifyRunOut)
def get_run(request: Any, run_id: int) -> dict[str, Any]:
    """单次核对详情（含发现项与覆盖度）。"""
    operator = _require_operator(request)
    run = query_service.get_run(run_id)
    _assert_case_visible(operator, run.artifact.case_id)
    return query_service.run_detail(run)


@router.post("/runs/{run_id}/decision", response=DecisionOut)
def create_decision(request: Any, run_id: int, payload: DecisionIn) -> DecisionOut:
    """记录一条裁决（append-only，不改历史行）。"""
    operator = _require_operator(request)
    run = query_service.get_run(run_id)
    _assert_case_visible(operator, run.artifact.case_id)
    decided = decision_service.record_decision(
        verification=run,
        action=payload.action,
        reason=payload.reason,
        decided_by=operator,
    )
    return DecisionOut(
        id=decided.id,
        verification_id=decided.verification_id,
        action=decided.action,
        reason=decided.reason,
        decided_by_id=decided.decided_by_id,
        decided_at=decided.decided_at,
    )


@router.post("/decisions/batch", response=DecisionBatchOut)
def create_batch_decisions(request: Any, payload: DecisionBatchIn) -> dict[str, Any]:
    """批量记录裁决：逐条判，脏 id 只跳过它自己（原因写进 `items`），不整批失败。"""
    operator = _require_operator(request)
    return decision_service.record_batch_decisions(
        run_ids=payload.run_ids,
        action=payload.action,
        reason=payload.reason,
        decided_by=operator,
    )


@router.get("/unverified", response=list[VerifyRunOut])
def list_unverified(request: Any, case_id: int) -> list[dict[str, Any]]:
    """该案待裁决清单（状态需裁决 + 要求核对 + 无 accept/reject 裁决）。"""
    if case_id <= 0:
        raise ValidationException(message="case_id 必须为正整数", errors={"case_id": case_id})
    _assert_case_visible(_require_operator(request), case_id)
    return query_service.list_unverified(case_id)


@router.get("/pending", response=list[VerifyRunOut])
def list_pending(request: Any, limit: int = 50) -> list[dict[str, Any]]:
    """**跨案件**待裁决清单（按可见性收窄），材料准备页全局入口用。"""
    operator = _require_operator(request)
    return query_service.list_pending(user=operator, limit=limit)
