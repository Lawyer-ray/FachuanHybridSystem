"""
案件指派 API
符合四层架构规范：只做请求/响应处理，业务逻辑在 Service 层
"""

from __future__ import annotations

from typing import Any, cast

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
def list_assignments(
    request: HttpRequest, case_id: int | None = None, lawyer_id: int | None = None
) -> list[CaseAssignmentOut]:
    service = _get_case_assignment_service()
    ctx = extract_request_context(request)
    return cast(list[CaseAssignmentOut], service.list_assignments(case_id=case_id, lawyer_id=lawyer_id, user=ctx.user))


@router.post("/assignments", response=CaseAssignmentOut)
def create_assignment(request: HttpRequest, payload: CaseAssignmentIn) -> CaseAssignmentOut:
    service = _get_case_assignment_service()
    ctx = extract_request_context(request)
    return cast(
        CaseAssignmentOut,
        service.create_assignment(case_id=payload.case_id, lawyer_id=payload.lawyer_id, user=ctx.user),
    )


@router.get("/assignments/{assignment_id}", response=CaseAssignmentOut)
def get_assignment(request: HttpRequest, assignment_id: int) -> CaseAssignmentOut:
    service = _get_case_assignment_service()
    ctx = extract_request_context(request)
    return cast(CaseAssignmentOut, service.get_assignment(assignment_id=assignment_id, user=ctx.user))


@router.put("/assignments/{assignment_id}", response=CaseAssignmentOut)
def update_assignment(request: HttpRequest, assignment_id: int, payload: CaseAssignmentUpdate) -> CaseAssignmentOut:
    service = _get_case_assignment_service()
    ctx = extract_request_context(request)
    data = payload.dict(exclude_unset=True)
    return cast(CaseAssignmentOut, service.update_assignment(assignment_id=assignment_id, data=data, user=ctx.user))


@router.delete("/assignments/{assignment_id}")
def delete_assignment(request: HttpRequest, assignment_id: int) -> Any:
    service = _get_case_assignment_service()
    ctx = extract_request_context(request)
    return service.delete_assignment(assignment_id=assignment_id, user=ctx.user)
