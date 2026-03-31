from __future__ import annotations

import logging
from typing import Any

from django.http import HttpRequest
from ninja import Router

from apps.contracts.schemas import (
    ContractIn,
    ContractOut,
    ContractPaginatedOut,
    ContractPartySourceOut,
    ContractPaymentIn,
    ContractUpdate,
    UpdateLawyersIn,
)
from apps.core.dto.request_context import extract_request_context

logger = logging.getLogger("apps.contracts.api")
router = Router()


def _get_contract_service() -> Any:
    from apps.contracts.services.contract.wiring import get_contract_service

    return get_contract_service()


@router.get("/contracts")
def list_contracts(
    request: HttpRequest,
    case_type: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> Any:
    """
    获取合同列表（分页）

    Requirements: 6.1, 6.2, 6.3
    """
    service = _get_contract_service()
    ctx = extract_request_context(request)

    result = service.list_contracts(
        case_type=case_type,
        status=status,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
        page=page,
        page_size=page_size,
    )
    # 手动序列化每个 Contract model → ContractOut，避免 Ninja 嵌套 ModelSchema 的 bug
    items_serialized = [
        ContractOut.from_orm(c).model_dump() for c in result["items"]
    ]
    return {
        "items": items_serialized,
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "total_pages": result["total_pages"],
    }


@router.get("/contracts/{contract_id}", response=ContractOut)
def get_contract(request: HttpRequest, contract_id: int) -> Any:
    """
    获取合同详情

    Requirements: 6.1, 6.2, 6.3
    """
    service = _get_contract_service()
    ctx = extract_request_context(request)

    return service.get_contract(
        contract_id=contract_id,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )


class ContractWithCasesIn(ContractIn):
    cases: list[dict[str, Any]] | None = None


@router.post("/contracts/full", response=ContractOut)
def create_contract_with_cases(request: HttpRequest, payload: ContractWithCasesIn) -> Any:
    """
    创建合同并关联案件

    Requirements: 4.1, 4.2, 4.3
    """
    service = _get_contract_service()

    data = payload.model_dump()
    cases_data = data.pop("cases", None)
    lawyer_ids = data.pop("lawyer_ids", [])

    contract = service.create_contract_with_cases(
        contract_data=data,
        cases_data=cases_data,
        assigned_lawyer_ids=lawyer_ids,
    )

    return contract


@router.put("/contracts/{contract_id}", response=ContractOut)
def update_contract(
    request: HttpRequest,
    contract_id: int,
    payload: ContractUpdate,
    sync_cases: bool = False,
    confirm_finance: bool = False,
    new_payments: list[ContractPaymentIn] | None = None,
) -> Any:
    """
    更新合同

    Requirements: 1.1, 1.2, 1.3, 4.3
    """
    service = _get_contract_service()
    ctx = extract_request_context(request)
    data = payload.model_dump(exclude_unset=True)

    contract = service.update_contract_with_finance(
        contract_id=contract_id,
        update_data=data,
        user=ctx.user,
        confirm_finance=confirm_finance,
        new_payments=[p.model_dump() for p in new_payments] if new_payments else None,
    )

    return contract


@router.post("/contracts", response=ContractOut)
def create_contract(
    request: HttpRequest,
    payload: ContractIn,
    payments: list[ContractPaymentIn] | None = None,
    confirm_finance: bool = False,
) -> Any:
    """
    创建合同

    Requirements: 1.1, 5.1, 5.3
    """
    service = _get_contract_service()
    ctx = extract_request_context(request)

    data = payload.model_dump()
    lawyer_ids = data.pop("lawyer_ids", [])

    contract = service.create_contract_with_cases(
        contract_data=data,
        cases_data=None,
        assigned_lawyer_ids=lawyer_ids,
        payments_data=[p.model_dump() for p in payments] if payments else None,
        confirm_finance=confirm_finance,
        user=ctx.user,
    )

    return contract


@router.put("/contracts/{contract_id}/lawyers", response=ContractOut)
def update_contract_lawyers(request: HttpRequest, contract_id: int, payload: UpdateLawyersIn) -> Any:
    """
    更新合同律师指派

    Requirements: 5.1, 5.2, 5.3
    """
    service = _get_contract_service()

    contract = service.update_contract_lawyers(contract_id=contract_id, lawyer_ids=payload.lawyer_ids)
    return contract


@router.delete("/contracts/{contract_id}")
def delete_contract(request: HttpRequest, contract_id: int) -> dict[str, bool]:
    """删除合同"""
    service = _get_contract_service()

    service.delete_contract(contract_id)
    return {"success": True}


@router.get("/contracts/{contract_id}/all-parties", response=list[ContractPartySourceOut])
def get_contract_all_parties(request: HttpRequest, contract_id: int) -> Any:
    """
    获取合同及补充协议的所有当事人

    Requirements: 5.1, 5.2, 5.3, 5.4
    """
    service = _get_contract_service()

    parties = service.get_all_parties(contract_id)

    return parties
