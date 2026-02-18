from __future__ import annotations

import logging
from typing import Any

from ninja import Router

from apps.core.request_context import extract_request_context

from ..schemas import (
    ContractIn,
    ContractOut,
    ContractPartySourceOut,
    ContractPaymentIn,
    ContractUpdate,
    UpdateLawyersIn,
)
from ..services.contract_service import ContractService

logger = logging.getLogger("apps.contracts.api")
router = Router()


def _get_contract_service() -> ContractService:
    """
    工厂函数：创建 ContractService 实例并注入依赖

    Requirements: 1.5
    """
    from apps.cases.services import CaseServiceAdapter
    from apps.client.services import ClientServiceAdapter

    from ..services.contract_payment_service import ContractPaymentService
    from ..services.supplementary_agreement_service import SupplementaryAgreementService

    case_service = CaseServiceAdapter()
    payment_service = ContractPaymentService()
    supplementary_agreement_service = SupplementaryAgreementService(
        client_service=ClientServiceAdapter()  # type: ignore[abstract]
    )

    return ContractService(
        case_service=case_service,  # type: ignore[arg-type]
        payment_service=payment_service,
        supplementary_agreement_service=supplementary_agreement_service,
    )


@router.get("/contracts", response=list[ContractOut])
def list_contracts(request: Any, case_type: str | None = None, status: str | None = None) -> Any:
    """
    获取合同列表

    Requirements: 6.1, 6.2, 6.3
    """
    service = _get_contract_service()
    ctx = extract_request_context(request)

    return service.list_contracts(
        case_type=case_type,
        status=status,
        user=ctx.user,
        org_access=ctx.org_access,
        perm_open_access=ctx.perm_open_access,
    )


@router.get("/contracts/{contract_id}", response=ContractOut)
def get_contract(request: Any, contract_id: int) -> Any:
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
def create_contract_with_cases(request: Any, payload: ContractWithCasesIn) -> Any:
    """
    创建合同并关联案件

    Requirements: 4.1, 4.2, 4.3
    """
    service = _get_contract_service()

    data = payload.dict()
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
    request: Any,
    contract_id: int,
    payload: ContractUpdate,
    sync_cases: bool | None = False,
    confirm_finance: bool | None = False,
    new_payments: list[ContractPaymentIn] | None = None,
) -> Any:
    """
    更新合同

    Requirements: 1.1, 1.2, 1.3, 4.3
    """
    service = _get_contract_service()
    ctx = extract_request_context(request)
    data = payload.dict(exclude_unset=True)

    contract = service.update_contract_with_finance(
        contract_id=contract_id,
        update_data=data,
        user=ctx.user,
        confirm_finance=confirm_finance,  # type: ignore[arg-type]
        new_payments=[p.dict() for p in new_payments] if new_payments else None,
    )

    return contract


@router.post("/contracts", response=ContractOut)
def create_contract(
    request: Any,
    payload: ContractIn,
    payments: list[ContractPaymentIn] | None = None,
    confirm_finance: bool | None = False,
) -> Any:
    """
    创建合同

    Requirements: 1.1, 5.1, 5.3
    """
    service = _get_contract_service()
    ctx = extract_request_context(request)

    data = payload.dict()
    lawyer_ids = data.pop("lawyer_ids", [])

    contract = service.create_contract_with_cases(
        contract_data=data,
        cases_data=None,
        assigned_lawyer_ids=lawyer_ids,
        payments_data=[p.dict() for p in payments] if payments else None,
        confirm_finance=confirm_finance,  # type: ignore[arg-type]
        user=ctx.user,
    )

    return contract


@router.put("/contracts/{contract_id}/lawyers", response=ContractOut)
def update_contract_lawyers(request: Any, contract_id: int, payload: UpdateLawyersIn) -> Any:
    """
    更新合同律师指派

    Requirements: 5.1, 5.2, 5.3
    """
    service = _get_contract_service()

    contract = service.update_contract_lawyers(contract_id=contract_id, lawyer_ids=payload.lawyer_ids)
    return contract


@router.delete("/contracts/{contract_id}")
def delete_contract(request: Any, contract_id: int) -> dict[str, bool]:
    """删除合同"""
    service = _get_contract_service()

    service.delete_contract(contract_id)
    return {"success": True}


@router.get("/contracts/{contract_id}/all-parties", response=list[ContractPartySourceOut])
def get_contract_all_parties(request: Any, contract_id: int) -> Any:
    """
    获取合同及补充协议的所有当事人

    Requirements: 5.1, 5.2, 5.3, 5.4
    """
    service = _get_contract_service()

    parties = service.get_all_parties(contract_id)

    return parties
