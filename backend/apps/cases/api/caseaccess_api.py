"""
案件访问授权 API

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

from apps.cases.schemas import CaseAccessGrantIn, CaseAccessGrantOut, CaseAccessGrantUpdate
from apps.core.dto.request_context import extract_request_context

router = Router()


def _get_case_access_service() -> Any:
    """
    工厂函数：创建 CaseAccessService 实例

        CaseAccessService 实例
    """
    from apps.cases.services.case.case_access_service import CaseAccessService

    return CaseAccessService()


@router.get("/grants", response=list[CaseAccessGrantOut])
def list_grants(
    request: HttpRequest, case_id: int | None = None, grantee_id: int | None = None
) -> list[CaseAccessGrantOut]:
    service = _get_case_access_service()
    ctx = extract_request_context(request)

    return cast(
        list[CaseAccessGrantOut],
        service.list_grants(
            case_id=case_id,
            grantee_id=grantee_id,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        ),
    )


@router.post("/grants", response=CaseAccessGrantOut)
def create_grant(request: HttpRequest, payload: CaseAccessGrantIn) -> CaseAccessGrantOut:
    service = _get_case_access_service()
    ctx = extract_request_context(request)

    return cast(
        CaseAccessGrantOut,
        service.create_grant(
            case_id=payload.case_id,
            grantee_id=payload.grantee_id,
            user=ctx.user,
        ),
    )


@router.get("/grants/{grant_id}", response=CaseAccessGrantOut)
def get_grant(request: HttpRequest, grant_id: int) -> CaseAccessGrantOut:
    service = _get_case_access_service()
    ctx = extract_request_context(request)

    return cast(
        CaseAccessGrantOut,
        service.get_grant(
            grant_id=grant_id,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        ),
    )


@router.put("/grants/{grant_id}", response=CaseAccessGrantOut)
def update_grant(request: HttpRequest, grant_id: int, payload: CaseAccessGrantUpdate) -> CaseAccessGrantOut:
    service = _get_case_access_service()
    ctx = extract_request_context(request)
    data = payload.model_dump(exclude_unset=True)

    return cast(
        CaseAccessGrantOut,
        service.update_grant(
            grant_id=grant_id,
            data=data,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        ),
    )


@router.delete("/grants/{grant_id}")
def delete_grant(request: HttpRequest, grant_id: int) -> Any:
    service = _get_case_access_service()
    ctx = extract_request_context(request)

    return service.delete_grant(
        grant_id=grant_id,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )
