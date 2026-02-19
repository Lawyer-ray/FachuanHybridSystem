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

from ninja import Router

from apps.core.request_context import extract_request_context

from apps.cases.schemas import CaseCreateFull, CaseFullOut, CaseIn, CaseOut, CaseUpdate
from apps.cases.services import CaseService

router = Router()


def _get_case_service() -> CaseService:
    """
    创建 CaseService 实例（注入依赖）

    Returns:
        CaseService 实例
    """
    from apps.contracts.services import ContractService
    return CaseService(contract_service=ContractService())


def _get_case_query_facade() -> CaseService:
    """Query facade — 只读操作"""
    from apps.contracts.services import ContractService
    return CaseService(contract_service=ContractService())


def _get_case_mutation_facade() -> CaseService:
    """Mutation facade — 写操作"""
    from apps.contracts.services import ContractService
    return CaseService(contract_service=ContractService())


@router.get("/cases/search", response=list[CaseOut])
def search_cases(
    request: Any,
    q: str,
    limit: int | None = 10,
) -> list[CaseOut]:
    """搜索案件"""
    service = _get_case_query_facade()
    ctx = extract_request_context(request)

    return cast(
        list[CaseOut],
        service.search_cases(
            query=q,
            limit=limit,  # type: ignore[arg-type]
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        ),
    )


@router.get("/cases", response=list[CaseOut])
def list_cases(
    request: Any,
    case_type: str | None = None,
    status: str | None = None,
    case_number: str | None = None,
) -> list[CaseOut]:
    """获取案件列表"""
    service = _get_case_query_facade()
    ctx = extract_request_context(request)

    if case_number:
        return cast(
            list[CaseOut],
            service.search_by_case_number(
                case_number=case_number,
                user=ctx.user,
                org_access=ctx.org_access,
                perm_open_access=ctx.perm_open_access,
            ),
        )

    return cast(
        list[CaseOut],
        service.list_cases(
            case_type=case_type,
            status=status,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        ),
    )


@router.get("/cases/{case_id}", response=CaseOut)
def get_case(request: Any, case_id: int) -> CaseOut:
    """获取单个案件"""
    service = _get_case_query_facade()
    ctx = extract_request_context(request)

    return cast(
        CaseOut,
        service.get_case(
            case_id=case_id,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        ),
    )


@router.post("/cases", response=CaseOut)
def create_case(request: Any, payload: CaseIn) -> CaseOut:
    """创建案件"""
    service = _get_case_mutation_facade()
    ctx = extract_request_context(request)
    data = payload.dict()

    return cast(CaseOut, service.create_case(data, user=ctx.user))


@router.put("/cases/{case_id}", response=CaseOut)
def update_case(request: Any, case_id: int, payload: CaseUpdate) -> CaseOut:
    """更新案件"""
    service = _get_case_mutation_facade()
    ctx = extract_request_context(request)
    data = payload.dict(exclude_unset=True)

    return cast(CaseOut, service.update_case(case_id, data, user=ctx.user))


@router.delete("/cases/{case_id}")
def delete_case(request: Any, case_id: int) -> dict[str, bool]:
    """删除案件"""
    service = _get_case_mutation_facade()
    ctx = extract_request_context(request)

    service.delete_case(case_id, user=ctx.user)

    return {"success": True}


@router.post("/cases/full", response=CaseFullOut)
def create_case_full(request: Any, payload: CaseCreateFull) -> CaseFullOut:
    """创建完整案件（包含当事人、指派、日志）"""
    service = _get_case_mutation_facade()
    ctx = extract_request_context(request)
    actor_id = getattr(ctx.user, "id", None) if ctx.user else None

    data = {
        "case": payload.case.dict(),
        "parties": [p.dict() for p in payload.parties] if payload.parties else [],
        "assignments": [a.dict() for a in payload.assignments] if payload.assignments else [],
        "logs": [log.dict() for log in payload.logs] if payload.logs else [],
        "supervising_authorities": (
            [s.dict() for s in payload.supervising_authorities] if payload.supervising_authorities else []
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
