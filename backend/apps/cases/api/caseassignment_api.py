"""
案件指派 API
符合四层架构规范：只做请求/响应处理，业务逻辑在 Service 层
"""

from __future__ import annotations

from typing import Any

from asgiref.sync import sync_to_async
from django.http import HttpRequest
from ninja import Router

from apps.cases.schemas import CaseAssignmentIn, CaseAssignmentOut, CaseAssignmentUpdate
from apps.core.dto.request_context import extract_request_context

router = Router()


def _get_case_assignment_service() -> Any:
    """工厂函数：创建 CaseAssignmentService 实例"""
    from apps.cases.services.party.case_assignment_service import CaseAssignmentService

    return CaseAssignmentService()


@router.get("/assignments", response=list[CaseAssignmentOut])
async def list_assignments(  # pragma: no cover
    request: HttpRequest, case_id: int | None = None, lawyer_id: int | None = None
) -> list[CaseAssignmentOut]:
    service = _get_case_assignment_service()
    ctx = extract_request_context(request)
    return await sync_to_async(service.list_assignments)(  # type: ignore[no-any-return]
        case_id=case_id, lawyer_id=lawyer_id, user=ctx.user,
        perm_open_access=ctx.perm_open_access,
    )


@router.post("/assignments", response=CaseAssignmentOut)
async def create_assignment(request: HttpRequest, payload: CaseAssignmentIn) -> CaseAssignmentOut:  # pragma: no cover
    service = _get_case_assignment_service()
    ctx = extract_request_context(request)
    return await sync_to_async(service.create_assignment)(  # type: ignore[no-any-return]
        case_id=payload.case_id, lawyer_id=payload.lawyer_id, user=ctx.user,
        perm_open_access=ctx.perm_open_access,
    )


@router.get("/assignments/{assignment_id}", response=CaseAssignmentOut)
async def get_assignment(request: HttpRequest, assignment_id: int) -> CaseAssignmentOut:  # pragma: no cover
    service = _get_case_assignment_service()
    ctx = extract_request_context(request)
    return await sync_to_async(service.get_assignment)(  # type: ignore[no-any-return]
        assignment_id=assignment_id, user=ctx.user,
        perm_open_access=ctx.perm_open_access,
    )


@router.put("/assignments/{assignment_id}", response=CaseAssignmentOut)
async def update_assignment(request: HttpRequest, assignment_id: int, payload: CaseAssignmentUpdate) -> CaseAssignmentOut:  # pragma: no cover
    service = _get_case_assignment_service()
    ctx = extract_request_context(request)
    data = payload.model_dump(exclude_unset=True)
    return await sync_to_async(service.update_assignment)(  # type: ignore[no-any-return]
        assignment_id=assignment_id, data=data, user=ctx.user,
        perm_open_access=ctx.perm_open_access,
    )


@router.delete("/assignments/{assignment_id}")
async def delete_assignment(request: HttpRequest, assignment_id: int) -> Any:  # pragma: no cover
    service = _get_case_assignment_service()
    ctx = extract_request_context(request)
    return await sync_to_async(service.delete_assignment)(
        assignment_id=assignment_id, user=ctx.user,
        perm_open_access=ctx.perm_open_access,
    )
