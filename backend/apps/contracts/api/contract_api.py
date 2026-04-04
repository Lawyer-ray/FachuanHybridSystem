from __future__ import annotations

import logging
from typing import Any

from django.http import HttpRequest
from ninja import Router

from apps.contracts.schemas import (
    ContractAssignmentOut,
    ContractIn,
    ContractOut,
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


def _get_domain_service() -> Any:
    from apps.contracts.services.contract.wiring import get_contract_domain_service

    return get_contract_domain_service()


@router.get("/contracts", response=list[ContractOut])
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
    service = _get_domain_service()
    ctx = extract_request_context(request)

    result = service.list_contracts(
        case_type=case_type,
        status=status,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )
    # list_contracts 返回 dict（含分页），前端做客户端分页所以只返回 items
    return result["items"] if isinstance(result, dict) else result


class ContractWithCasesIn(ContractIn):
    cases: list[dict[str, Any]] | None = None


@router.post("/contracts/full", response=ContractOut)
def create_contract_with_cases(request: HttpRequest, payload: ContractWithCasesIn) -> Any:
    service = _get_domain_service()
    data = payload.model_dump()
    cases_data = data.pop("cases", None)
    lawyer_ids = data.pop("lawyer_ids", [])
    return service.create_contract_with_cases(
        contract_data=data, cases_data=cases_data, assigned_lawyer_ids=lawyer_ids,
    )


@router.get("/contracts/{contract_id}", response=ContractOut)
def get_contract(request: HttpRequest, contract_id: int) -> Any:
    """
    获取合同详情

    Requirements: 6.1, 6.2, 6.3
    """
    service = _get_domain_service()
    ctx = extract_request_context(request)

    return service.get_contract(
        contract_id=contract_id,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )


@router.put("/contracts/{contract_id}", response=ContractOut)
def update_contract(
    request: HttpRequest,
    contract_id: int,
    payload: ContractUpdate,
    sync_cases: bool = False,
    confirm_finance: bool = False,
    new_payments: list[ContractPaymentIn] | None = None,
) -> Any:
    service = _get_domain_service()
    ctx = extract_request_context(request)
    data = payload.model_dump(exclude_unset=True)
    return service.update_contract_with_finance(
        contract_id=contract_id, update_data=data, user=ctx.user,
        confirm_finance=confirm_finance,
        new_payments=[p.model_dump() for p in new_payments] if new_payments else None,
    )


@router.post("/contracts", response=ContractOut)
def create_contract(
    request: HttpRequest,
    payload: ContractIn,
    payments: list[ContractPaymentIn] | None = None,
    confirm_finance: bool = False,
) -> Any:
    service = _get_domain_service()
    ctx = extract_request_context(request)
    data = payload.model_dump()
    lawyer_ids = data.pop("lawyer_ids", [])
    return service.create_contract_with_cases(
        contract_data=data, cases_data=None, assigned_lawyer_ids=lawyer_ids,
        payments_data=[p.model_dump() for p in payments] if payments else None,
        confirm_finance=confirm_finance, user=ctx.user,
    )


@router.put("/contracts/{contract_id}/lawyers", response=list[ContractAssignmentOut])
def update_contract_lawyers(request: HttpRequest, contract_id: int, payload: UpdateLawyersIn) -> Any:
    service = _get_domain_service()
    assignments = service.update_contract_lawyers(contract_id=contract_id, lawyer_ids=payload.lawyer_ids)
    return [ContractAssignmentOut.from_assignment(item) for item in assignments]


@router.delete("/contracts/{contract_id}")
def delete_contract(request: HttpRequest, contract_id: int) -> dict[str, bool]:
    service = _get_domain_service()
    service.delete_contract(contract_id)
    return {"success": True}


@router.get("/contracts/{contract_id}/all-parties", response=list[ContractPartySourceOut])
def get_contract_all_parties(request: HttpRequest, contract_id: int) -> Any:
    service = _get_domain_service()
    return service.get_all_parties(contract_id)
