"""
案件 API

API 层职责：
1. 接收 HTTP 请求，验证参数（通过 Schema）
2. 调用 Service 层方法
3. 返回响应

不包含：业务逻辑、权限检查、异常处理（依赖全局异常处理器）
"""

from __future__ import annotations

from typing import Any, cast

from django.http import HttpRequest
from ninja import Router

from apps.cases.schemas import CaseCreateFull, CaseFullOut, CaseIn, CaseOut, CaseUpdate
from apps.cases.services import CaseService
from apps.core.dto.request_context import extract_request_context

router = Router()


def _prefetch_log_reminders(cases: list[Any]) -> None:
    """批量预加载案件日志的提醒数据，避免 N+1 查询。"""
    log_ids: list[int] = []
    all_logs = []
    for case in cases:
        for log in case.logs.all():
            if log.id:
                log_ids.append(log.id)
                all_logs.append(log)
    if not log_ids:
        return

    from apps.core.interfaces import ServiceLocator

    try:
        reminder_service = ServiceLocator.get_reminder_service()
        reminders_map = reminder_service.export_case_log_reminders_batch_internal(case_log_ids=log_ids)
        for log in all_logs:
            log._cached_exported_reminders = reminders_map.get(log.id, [])
    except Exception:
        pass


def _get_case_service() -> CaseService:
    from apps.contracts.services.contract.wiring import get_contract_service

    return CaseService(contract_service=get_contract_service())


def _get_case_query_facade() -> CaseService:
    return _get_case_service()


def _get_case_mutation_facade() -> CaseService:
    return _get_case_service()


@router.get("/cases/search", response=list[CaseOut])
def search_cases(
    request: HttpRequest,
    q: str,
    limit: int | None = 10,
) -> list[CaseOut]:
    """搜索案件"""
    service = _get_case_query_facade()
    ctx = extract_request_context(request)

    cases = list(
        service.search_cases(
            query=q,
            limit=limit,  # type: ignore[arg-type]
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )
    )
    _prefetch_log_reminders(cases)
    return cast(list[CaseOut], cases)


@router.get("/cases", response=list[CaseOut])
def list_cases(
    request: HttpRequest,
    case_type: str | None = None,
    status: str | None = None,
    case_number: str | None = None,
) -> list[CaseOut]:
    """获取案件列表"""
    service = _get_case_query_facade()
    ctx = extract_request_context(request)

    if case_number:
        cases = list(
            service.search_by_case_number(
                case_number=case_number,
                user=ctx.user,
                org_access=ctx.org_access,
                perm_open_access=ctx.perm_open_access,
            )
        )
    else:
        cases = list(
            service.list_cases(
                case_type=case_type,
                status=status,
                user=ctx.user,
                org_access=ctx.org_access,
                perm_open_access=ctx.perm_open_access,
            )
        )

    _prefetch_log_reminders(cases)
    return cast(list[CaseOut], cases)


@router.get("/cases/{case_id}", response=CaseOut)
def get_case(request: HttpRequest, case_id: int) -> CaseOut:
    """获取单个案件"""
    service = _get_case_query_facade()
    ctx = extract_request_context(request)

    case = service.get_case(
        case_id=case_id,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )
    _prefetch_log_reminders([case])
    return cast(CaseOut, case)


@router.post("/cases", response=CaseOut)
def create_case(request: HttpRequest, payload: CaseIn) -> CaseOut:
    """创建案件"""
    service = _get_case_mutation_facade()
    ctx = extract_request_context(request)
    data = payload.model_dump()

    return cast(CaseOut, service.create_case(data, user=ctx.user))


@router.put("/cases/{case_id}", response=CaseOut)
def update_case(request: HttpRequest, case_id: int, payload: CaseUpdate) -> CaseOut:
    """更新案件"""
    service = _get_case_mutation_facade()
    ctx = extract_request_context(request)
    data = payload.model_dump(exclude_unset=True)

    return cast(CaseOut, service.update_case(case_id, data, user=ctx.user))


@router.delete("/cases/{case_id}")
def delete_case(request: HttpRequest, case_id: int) -> dict[str, bool]:
    """删除案件"""
    service = _get_case_mutation_facade()
    ctx = extract_request_context(request)

    service.delete_case(case_id, user=ctx.user)

    return {"success": True}


@router.post("/cases/full", response=CaseFullOut)
def create_case_full(request: HttpRequest, payload: CaseCreateFull) -> CaseFullOut:
    """创建完整案件（包含当事人、指派、日志）"""
    service = _get_case_mutation_facade()
    ctx = extract_request_context(request)
    actor_id = getattr(ctx.user, "id", None) if ctx.user else None

    data: dict[str, Any] = {
        "case": payload.case.model_dump(),
        "parties": [p.model_dump() for p in payload.parties] if payload.parties else [],
        "assignments": [a.model_dump() for a in payload.assignments] if payload.assignments else [],
        "logs": [log.model_dump() for log in payload.logs] if payload.logs else [],
        "supervising_authorities": (
            [s.model_dump() for s in payload.supervising_authorities] if payload.supervising_authorities else []
        ),
    }

    result = service.create_case_full(data, actor_id=actor_id, user=ctx.user)

    return CaseFullOut(
        case=result["case"],
        parties=result["parties"],
        assignments=result["assignments"],
        logs=result["logs"],
        case_numbers=[],
        supervising_authorities=result.get("supervising_authorities", []),
    )
