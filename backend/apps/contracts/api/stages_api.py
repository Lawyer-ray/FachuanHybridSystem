"""非诉专项阶段树 API：GET / PUT /contracts/{contract_id}/stages。

挂在合同路由前缀下（与 contract_api 的 `/contracts/{id}` 同前缀），所以真实
URL 是 `/api/v1/contracts/contracts/{id}/stages`。鉴权与行级 ACL 与
`contract_api` 一致：先 `aensure_access`，再读/写；契约在 `stages_service`。
"""

from __future__ import annotations

from typing import Any

from asgiref.sync import sync_to_async
from django.http import HttpRequest
from ninja import Router

from apps.contracts.schemas.stages_schemas import ContractStagesIn, ContractStagesOut
from apps.core.dto.request_context import extract_request_context

router = Router()


def _get_stages_service() -> Any:
    from apps.contracts.services.contract.stages_service import ContractStagesService

    return ContractStagesService()


def _get_access_policy() -> Any:
    from apps.contracts.services.contract.wiring import get_contract_domain_service

    return get_contract_domain_service().access_policy


async def _ensure_access(request: HttpRequest, contract_id: int, ctx: Any) -> None:
    await _get_access_policy().aensure_access(
        contract_id=contract_id,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )


@router.get("/contracts/{contract_id}/stages", response=ContractStagesOut)
async def get_contract_stages(request: HttpRequest, contract_id: int) -> Any:  # pragma: no cover
    """读取非诉专项阶段树，每个节点带推导出的 state（ok / doing / todo）。"""
    service = _get_stages_service()
    ctx = await sync_to_async(extract_request_context)(request)
    await _ensure_access(request, contract_id, ctx)
    stages = await sync_to_async(service.get_stages)(contract_id)
    return {"stages": stages}


@router.put("/contracts/{contract_id}/stages", response=ContractStagesOut)
async def replace_contract_stages(  # pragma: no cover
    request: HttpRequest, contract_id: int, payload: ContractStagesIn
) -> Any:
    """整树覆盖写阶段树。深度 > 3 / key 重复 / name 为空 → 400。"""
    service = _get_stages_service()
    ctx = await sync_to_async(extract_request_context)(request)
    await _ensure_access(request, contract_id, ctx)
    stages = await sync_to_async(service.replace_stages)(contract_id, payload.stages)
    return {"stages": stages}
