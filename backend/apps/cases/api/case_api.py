"""
案件 API

异步端点，Service 层同步调用通过 sync_to_async 包装。
所有 ORM 访问和 Pydantic 序列化均在 sync_to_async 闭包内完成，
防止 SynchronousOnlyOperation 和 Django Ninja re-validation 时的懒加载。
"""

from __future__ import annotations

from typing import Any, cast

from asgiref.sync import sync_to_async
from django.http import HttpRequest
from ninja import Router

from apps.cases.schemas import CaseCreateFull, CaseFullOut, CaseIn, CaseOut, CaseUpdate
from apps.cases.services import CaseService
from apps.core.dto.request_context import extract_request_context

router = Router()


def _serialize_case(case: Any) -> dict:
    """Serialize a Case model to dict inside sync context (avoid lazy FK access in async)."""
    return CaseOut.from_orm(case).model_dump()


def _get_case_service() -> CaseService:
    from apps.contracts.services.contract.wiring import get_contract_service

    return CaseService(contract_service=get_contract_service())


def _get_case_query_facade() -> CaseService:
    return _get_case_service()


def _get_case_mutation_facade() -> CaseService:
    return _get_case_service()


@router.get("/cases/search", response=list[CaseOut])
async def search_cases(  # pragma: no cover
    request: HttpRequest,
    q: str,
    limit: int | None = 10,
) -> list[dict]:
    """搜索案件"""
    service = _get_case_query_facade()
    ctx = extract_request_context(request)

    def _do() -> list[dict]:
        cases = list(service.search_cases(
            query=q,
            limit=limit,  # type: ignore[arg-type]
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        ))
        return [_serialize_case(c) for c in cases]

    return cast(list[dict], await sync_to_async(_do)())


@router.get("/cases", response=list[CaseOut])
async def list_cases(  # pragma: no cover
    request: HttpRequest,
    case_type: str | None = None,
    status: str | None = None,
    case_number: str | None = None,
) -> list[dict]:
    """获取案件列表"""
    service = _get_case_query_facade()
    ctx = extract_request_context(request)

    def _do() -> list[dict]:
        if case_number:
            raw = list(service.search_by_case_number(
                case_number=case_number,
                user=ctx.user,
                org_access=ctx.org_access,
                perm_open_access=ctx.perm_open_access,
            ))
        else:
            raw = list(service.list_cases(
                case_type=case_type,
                status=status,
                user=ctx.user,
                org_access=ctx.org_access,
                perm_open_access=ctx.perm_open_access,
            ))
        return [_serialize_case(c) for c in raw]

    return cast(list[dict], await sync_to_async(_do)())


@router.get("/cases/{case_id}", response=CaseOut)
async def get_case(request: HttpRequest, case_id: int) -> dict:  # pragma: no cover
    """获取单个案件"""
    service = _get_case_query_facade()
    ctx = extract_request_context(request)

    def _get() -> dict:
        case = service.get_case(
            case_id=case_id,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )
        return _serialize_case(case)

    return await sync_to_async(_get)()


@router.post("/cases", response=CaseOut)
async def create_case(request: HttpRequest, payload: CaseIn) -> dict:  # pragma: no cover
    """创建案件"""
    service = _get_case_mutation_facade()
    ctx = extract_request_context(request)
    data = payload.model_dump()

    def _create() -> dict:
        case = service.create_case(data, user=ctx.user)
        return _serialize_case(case)

    return await sync_to_async(_create)()


@router.put("/cases/{case_id}", response=CaseOut)
async def update_case(request: HttpRequest, case_id: int, payload: CaseUpdate) -> dict:  # pragma: no cover
    """更新案件"""
    service = _get_case_mutation_facade()
    ctx = extract_request_context(request)
    data = payload.model_dump(exclude_unset=True)

    def _update() -> dict:
        case = service.update_case(case_id, data, user=ctx.user)
        return _serialize_case(case)

    return await sync_to_async(_update)()


@router.delete("/cases/{case_id}")
async def delete_case(request: HttpRequest, case_id: int) -> dict[str, bool]:  # pragma: no cover
    """删除案件"""
    service = _get_case_mutation_facade()
    ctx = extract_request_context(request)

    await sync_to_async(service.delete_case)(case_id, user=ctx.user)

    return {"success": True}


@router.post("/cases/full", response=CaseFullOut)
async def create_case_full(request: HttpRequest, payload: CaseCreateFull) -> dict:  # pragma: no cover
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

    def _create_full() -> dict:
        result = service.create_case_full(data, actor_id=actor_id, user=ctx.user)
        return CaseFullOut(
            case=CaseOut.from_orm(result["case"]),
            parties=result["parties"],
            assignments=result["assignments"],
            logs=result["logs"],
            case_numbers=[],
            supervising_authorities=result.get("supervising_authorities", []),
        ).model_dump()

    return await sync_to_async(_create_full)()
