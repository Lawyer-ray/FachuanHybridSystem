"""
补充协议 API 层
符合三层架构规范：只做请求/响应处理，业务逻辑在 Service 层
异常处理依赖全局异常处理器，API 层不包含 try/except
"""

from __future__ import annotations

from typing import Any

from asgiref.sync import sync_to_async
from django.http import HttpRequest
from ninja import Router

from apps.client.services import ClientServiceAdapter
from apps.contracts.schemas import SupplementaryAgreementIn, SupplementaryAgreementOut, SupplementaryAgreementUpdate
from apps.contracts.services.supplementary.supplementary_agreement_service import SupplementaryAgreementService

router = Router()


def _get_supplementary_agreement_service() -> SupplementaryAgreementService:
    """工厂函数：创建服务实例并注入依赖"""
    return SupplementaryAgreementService(client_service=ClientServiceAdapter())


def _get_contract_access_policy() -> Any:
    from apps.contracts.services.contract.wiring import get_contract_domain_service

    return get_contract_domain_service().access_policy


async def _async_ensure_contract_access(request: Any, contract_id: int) -> None:  # pragma: no cover
    """Async version: verify current user's access to the contract."""
    from apps.core.security import get_request_access_context

    ctx = await sync_to_async(get_request_access_context)(request)
    await _get_contract_access_policy().aensure_access(
        contract_id=contract_id,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )


def _ensure_contract_access(request: Any, contract_id: int) -> None:
    """验证当前用户对合同的访问权限。"""
    from apps.core.security import get_request_access_context

    ctx = get_request_access_context(request)
    _get_contract_access_policy().ensure_access(
        contract_id=contract_id,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )


async def _async_resolve_contract_id_from_agreement(agreement_id: int) -> int:
    """异步从补充协议 ID 解析其所属合同 ID。"""
    from apps.contracts.models import SupplementaryAgreement

    try:
        agreement = await SupplementaryAgreement.objects.values("contract_id").aget(pk=agreement_id)
    except SupplementaryAgreement.DoesNotExist:
        from apps.core.exceptions import NotFoundError

        raise NotFoundError(f"补充协议 {agreement_id} 不存在")
    return agreement["contract_id"]


def _resolve_contract_id_from_agreement(agreement_id: int) -> int:
    """从补充协议 ID 解析其所属合同 ID。"""
    from apps.contracts.models import SupplementaryAgreement

    try:
        agreement = SupplementaryAgreement.objects.values("contract_id").get(pk=agreement_id)
    except SupplementaryAgreement.DoesNotExist:
        from apps.core.exceptions import NotFoundError

        raise NotFoundError(f"补充协议 {agreement_id} 不存在")
    return agreement["contract_id"]


@router.post("/supplementary-agreements", response=SupplementaryAgreementOut)
async def create_supplementary_agreement(  # pragma: no cover
    request: HttpRequest, payload: SupplementaryAgreementIn
) -> SupplementaryAgreementOut:
    await _async_ensure_contract_access(request, payload.contract_id)
    service = _get_supplementary_agreement_service()
    return await sync_to_async(service.create_supplementary_agreement)(
        contract_id=payload.contract_id, name=payload.name, party_ids=payload.party_ids
    )  # type: ignore[return-value]


@router.get("/supplementary-agreements/{agreement_id}", response=SupplementaryAgreementOut)
async def get_supplementary_agreement(request: HttpRequest, agreement_id: int) -> SupplementaryAgreementOut:  # pragma: no cover
    contract_id = await _async_resolve_contract_id_from_agreement(agreement_id)
    await _async_ensure_contract_access(request, contract_id)
    service = _get_supplementary_agreement_service()
    return await sync_to_async(service.get_supplementary_agreement)(agreement_id)  # type: ignore[return-value]


@router.get("/contracts/{contract_id}/supplementary-agreements", response=list[SupplementaryAgreementOut])
async def list_supplementary_agreements(request: HttpRequest, contract_id: int) -> list[SupplementaryAgreementOut]:  # pragma: no cover
    await _async_ensure_contract_access(request, contract_id)
    service = _get_supplementary_agreement_service()
    return await sync_to_async(service.list_by_contract)(contract_id)  # type: ignore[return-value]


@router.put("/supplementary-agreements/{agreement_id}", response=SupplementaryAgreementOut)
async def update_supplementary_agreement(  # pragma: no cover
    request: HttpRequest, agreement_id: int, payload: SupplementaryAgreementUpdate
) -> SupplementaryAgreementOut:
    contract_id = await _async_resolve_contract_id_from_agreement(agreement_id)
    await _async_ensure_contract_access(request, contract_id)
    service = _get_supplementary_agreement_service()
    data = payload.model_dump(exclude_unset=True)
    return await sync_to_async(service.update_supplementary_agreement)(
        agreement_id=agreement_id, name=data.get("name"), party_ids=data.get("party_ids")
    )  # type: ignore[return-value]


@router.delete("/supplementary-agreements/{agreement_id}")
async def delete_supplementary_agreement(request: HttpRequest, agreement_id: int) -> dict[str, bool]:  # pragma: no cover
    contract_id = await _async_resolve_contract_id_from_agreement(agreement_id)
    _ensure_contract_access(request, contract_id)
    service = _get_supplementary_agreement_service()
    await sync_to_async(service.delete_supplementary_agreement)(agreement_id)
    return {"success": True}
