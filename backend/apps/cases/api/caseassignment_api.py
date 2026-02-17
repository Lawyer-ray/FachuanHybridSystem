"""
案件指派 API
符合四层架构规范：只做请求/响应处理，业务逻辑在 Service 层
"""

from typing import Any

from ninja import Router

from ..schemas import CaseAssignmentIn, CaseAssignmentOut, CaseAssignmentUpdate

router = Router()


def _get_case_assignment_service() -> Any:
    """工厂函数：创建 CaseAssignmentService 实例"""
    from ..services.case_assignment_service import CaseAssignmentService

    return CaseAssignmentService()


@router.get("/assignments", response=list[CaseAssignmentOut])
def list_assignments(request: Any, case_id: int | None = None, lawyer_id: int | None = None) -> list[CaseAssignmentOut]:
    service = _get_case_assignment_service()
    user = getattr(request, "user", None)
    return service.list_assignments(case_id=case_id, lawyer_id=lawyer_id, user=user)  # type: ignore[no-any-return]


@router.post("/assignments", response=CaseAssignmentOut)
def create_assignment(request: Any, payload: CaseAssignmentIn) -> CaseAssignmentOut:
    service = _get_case_assignment_service()
    user = getattr(request, "user", None)
    return service.create_assignment(  # type: ignore[no-any-return]
        case_id=payload.case_id, lawyer_id=payload.lawyer_id, user=user
    )


@router.get("/assignments/{assignment_id}", response=CaseAssignmentOut)
def get_assignment(request: Any, assignment_id: int) -> CaseAssignmentOut:
    service = _get_case_assignment_service()
    user = getattr(request, "user", None)
    return service.get_assignment(assignment_id=assignment_id, user=user)  # type: ignore[no-any-return]


@router.put("/assignments/{assignment_id}", response=CaseAssignmentOut)
def update_assignment(request: Any, assignment_id: int, payload: CaseAssignmentUpdate) -> CaseAssignmentOut:
    service = _get_case_assignment_service()
    user = getattr(request, "user", None)
    data = payload.dict(exclude_unset=True)
    return service.update_assignment(assignment_id=assignment_id, data=data, user=user)  # type: ignore[no-any-return]


@router.delete("/assignments/{assignment_id}")
def delete_assignment(request: Any, assignment_id: int) -> Any:
    service = _get_case_assignment_service()
    user = getattr(request, "user", None)
    return service.delete_assignment(assignment_id=assignment_id, user=user)
