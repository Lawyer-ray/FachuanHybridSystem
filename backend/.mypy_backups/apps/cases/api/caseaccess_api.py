"""
案件访问授权 API

API 层职责：
1. 接收 HTTP 请求，验证参数（通过 Schema）
2. 调用 Service 层方法
3. 返回响应

不包含：业务逻辑、权限检查、异常处理（依赖全局异常处理器）
"""
from typing import List, Optional
from ninja import Router

from ..schemas import (
    CaseAccessGrantIn,
    CaseAccessGrantOut,
    CaseAccessGrantUpdate,
)

router = Router()


def _get_case_access_service():
    """
    工厂函数：创建 CaseAccessService 实例

    Returns:
        CaseAccessService 实例
    """
    from ..services.case_access_service import CaseAccessService
    return CaseAccessService()


@router.get("/grants", response=List[CaseAccessGrantOut])
def list_grants(request, case_id: Optional[int] = None, grantee_id: Optional[int] = None):
    """
    获取授权列表

    API 层只负责：
    1. 接收查询参数
    2. 调用 Service
    3. 返回结果
    """
    service = _get_case_access_service()

    # 提取用户和权限信息
    user = getattr(request, "user", None)
    org_access = getattr(request, "org_access", None)
    perm_open_access = getattr(request, "perm_open_access", False)

    return service.list_grants(
        case_id=case_id,
        grantee_id=grantee_id,
        user=user,
        org_access=org_access,
        perm_open_access=perm_open_access,
    )


@router.post("/grants", response=CaseAccessGrantOut)
def create_grant(request, payload: CaseAccessGrantIn):
    """
    创建授权

    API 层只负责：
    1. 接收请求数据
    2. 调用 Service
    3. 返回结果
    """
    service = _get_case_access_service()

    # 提取用户信息
    user = getattr(request, "user", None)

    return service.create_grant(
        case_id=payload.case_id,
        grantee_id=payload.grantee_id,
        user=user,
    )


@router.get("/grants/{grant_id}", response=CaseAccessGrantOut)
def get_grant(request, grant_id: int):
    """
    获取单个授权

    API 层只负责：
    1. 接收路径参数
    2. 调用 Service
    3. 返回结果（Service 会抛出 NotFoundError）
    """
    service = _get_case_access_service()

    # 提取用户和权限信息
    user = getattr(request, "user", None)
    org_access = getattr(request, "org_access", None)
    perm_open_access = getattr(request, "perm_open_access", False)

    return service.get_grant(
        grant_id=grant_id,
        user=user,
        org_access=org_access,
        perm_open_access=perm_open_access,
    )


@router.put("/grants/{grant_id}", response=CaseAccessGrantOut)
def update_grant(request, grant_id: int, payload: CaseAccessGrantUpdate):
    """
    更新授权

    API 层只负责：
    1. 接收参数
    2. 调用 Service
    3. 返回结果
    """
    service = _get_case_access_service()

    # 提取用户和权限信息
    user = getattr(request, "user", None)
    org_access = getattr(request, "org_access", None)
    perm_open_access = getattr(request, "perm_open_access", False)

    # 转换 Schema 为字典（只包含设置的字段）
    data = payload.dict(exclude_unset=True)

    return service.update_grant(
        grant_id=grant_id,
        data=data,
        user=user,
        org_access=org_access,
        perm_open_access=perm_open_access,
    )


@router.delete("/grants/{grant_id}")
def delete_grant(request, grant_id: int):
    """
    删除授权

    API 层只负责：
    1. 接收参数
    2. 调用 Service
    3. 返回结果
    """
    service = _get_case_access_service()

    # 提取用户和权限信息
    user = getattr(request, "user", None)
    org_access = getattr(request, "org_access", None)
    perm_open_access = getattr(request, "perm_open_access", False)

    return service.delete_grant(
        grant_id=grant_id,
        user=user,
        org_access=org_access,
        perm_open_access=perm_open_access,
    )
