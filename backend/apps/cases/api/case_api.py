"""
案件 API

API 层职责：
1. 接收 HTTP 请求，验证参数（通过 Schema）
2. 调用 Service 层方法
3. 返回响应

不包含：业务逻辑、权限检查、异常处理（依赖全局异常处理器）
"""
from typing import List, Optional
from ninja import Router

from ..schemas import (
    CaseIn,
    CaseOut,
    CaseUpdate,
    CaseCreateFull,
    CaseFullOut,
)
from ..services import CaseService
from apps.core.interfaces import ServiceLocator

router = Router()


def _get_case_service() -> CaseService:
    """
    创建 CaseService 实例（注入依赖）

    Returns:
        CaseService 实例
    """
    contract_service = ServiceLocator.get_contract_service()
    return CaseService(
        contract_service=contract_service
    )


@router.get("/cases/search", response=List[CaseOut])
def search_cases(
    request,
    q: str,
    limit: Optional[int] = 10,
):
    """
    搜索案件
    
    Args:
        q: 搜索关键词（案号、案件名称、当事人姓名）
        limit: 返回结果数量限制
    """
    service = _get_case_service()
    
    # 提取用户和权限信息
    user = getattr(request, "user", None)
    org_access = getattr(request, "org_access", None)
    perm_open_access = getattr(request, "perm_open_access", False)
    
    # 调用搜索服务
    return service.search_cases(
        query=q,
        limit=limit,
        user=user,
        org_access=org_access,
        perm_open_access=perm_open_access,
    )


@router.get("/cases", response=List[CaseOut])
def list_cases(
    request,
    case_type: Optional[str] = None,
    status: Optional[str] = None,
    case_number: Optional[str] = None,
):
    """
    获取案件列表

    API 层只负责：
    1. 接收查询参数
    2. 调用 Service
    3. 返回结果

    Args:
        case_type: 案件类型过滤
        status: 状态过滤
        case_number: 案号搜索（支持模糊匹配）
    """
    service = _get_case_service()

    # 提取用户和权限信息
    user = getattr(request, "user", None)
    org_access = getattr(request, "org_access", None)
    perm_open_access = getattr(request, "perm_open_access", False)

    # 如果提供了案号，使用案号搜索
    if case_number:
        return service.search_by_case_number(
            case_number=case_number,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    # 否则使用常规列表查询
    return service.list_cases(
        case_type=case_type,
        status=status,
        user=user,
        org_access=org_access,
        perm_open_access=perm_open_access,
    )


@router.get("/cases/{case_id}", response=CaseOut)
def get_case(request, case_id: int):
    """
    获取单个案件

    API 层只负责：
    1. 接收路径参数
    2. 调用 Service
    3. 返回结果（Service 会抛出 NotFoundError 或 ForbiddenError）
    """
    service = _get_case_service()

    # 提取用户和权限信息
    user = getattr(request, "user", None)
    org_access = getattr(request, "org_access", None)
    perm_open_access = getattr(request, "perm_open_access", False)

    # 调用 Service（权限检查在 Service 层）
    return service.get_case(
        case_id=case_id,
        user=user,
        org_access=org_access,
        perm_open_access=perm_open_access,
    )


@router.post("/cases", response=CaseOut)
def create_case(request, payload: CaseIn):
    """
    创建案件

    API 层只负责：
    1. 接收请求数据
    2. 调用 Service
    3. 返回结果
    """
    service = _get_case_service()

    # 提取用户信息
    user = getattr(request, "user", None)

    # 转换 Schema 为字典
    data = payload.dict()

    # 调用 Service（业务逻辑和权限检查在 Service 层）
    return service.create_case(data, user=user)


@router.put("/cases/{case_id}", response=CaseOut)
def update_case(request, case_id: int, payload: CaseUpdate):
    """
    更新案件

    API 层只负责：
    1. 接收参数
    2. 调用 Service
    3. 返回结果
    """
    service = _get_case_service()

    # 提取用户信息
    user = getattr(request, "user", None)

    # 转换 Schema 为字典（只包含设置的字段）
    data = payload.dict(exclude_unset=True)

    # 调用 Service（业务逻辑和权限检查在 Service 层）
    return service.update_case(case_id, data, user=user)


@router.delete("/cases/{case_id}")
def delete_case(request, case_id: int):
    """
    删除案件

    API 层只负责：
    1. 接收参数
    2. 调用 Service
    3. 返回 204 状态码
    """
    service = _get_case_service()

    # 提取用户信息
    user = getattr(request, "user", None)

    # 调用 Service（业务逻辑和权限检查在 Service 层）
    service.delete_case(case_id, user=user)

    return {"success": True}


@router.post("/cases/full", response=CaseFullOut)
def create_case_full(request, payload: CaseCreateFull):
    """
    创建完整案件（包含当事人、指派、日志）

    API 层只负责：
    1. 接收请求数据
    2. 调用 Service
    3. 返回结果
    """
    service = _get_case_service()

    # 提取用户信息
    user = getattr(request, "user", None)
    actor_id = getattr(user, "id", None) if user else None

    # 转换 Schema 为字典
    data = {
        "case": payload.case.dict(),
        "parties": [p.dict() for p in payload.parties] if payload.parties else [],
        "assignments": [a.dict() for a in payload.assignments] if payload.assignments else [],
        "logs": [log.dict() for log in payload.logs] if payload.logs else [],
        "supervising_authorities": [s.dict() for s in payload.supervising_authorities] if payload.supervising_authorities else [],
    }

    # 调用 Service（业务逻辑和权限检查在 Service 层）
    result = service.create_case_full(data, actor_id=actor_id, user=user)

    # 返回响应
    return CaseFullOut(
        case=result["case"],
        parties=result["parties"],
        assignments=result["assignments"],
        logs=result["logs"],
        case_numbers=[],
        supervising_authorities=result.get("supervising_authorities", []),
    )
