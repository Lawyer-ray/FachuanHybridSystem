"""
合同收款 API 层
符合三层架构规范：只做请求/响应处理，业务逻辑在 Service 层
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.http import HttpRequest
from django.utils.dateparse import parse_date
from ninja import Router

from apps.core.request_context import extract_request_context

from ..schemas import ContractPaymentIn, ContractPaymentOut, ContractPaymentUpdate

router = Router()


def _get_payment_service() -> Any:
    """工厂函数：创建 ContractPaymentService 实例"""
    from ..services.contract_payment_service import ContractPaymentService

    return ContractPaymentService()


@router.get("/finance/payments", response=list[ContractPaymentOut])
def list_payments(
    request: HttpRequest,
    contract_id: int | None = None,
    invoice_status: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[Any]:
    """获取收款列表"""
    service = _get_payment_service()
    ctx = extract_request_context(request)

    d1 = parse_date(start_date) if start_date else None
    d2 = parse_date(end_date) if end_date else None

    return list(
        service.list_payments(
            contract_id=contract_id,
            invoice_status=invoice_status,
            start_date=d1,
            end_date=d2,
            user=ctx.user,
            perm_open_access=ctx.perm_open_access,
        )
    )


@router.post("/finance/payments", response=ContractPaymentOut)
def create_payment(request: HttpRequest, payload: ContractPaymentIn) -> Any:
    """创建收款记录"""
    service = _get_payment_service()
    ctx = extract_request_context(request)

    received_at = parse_date(payload.received_at) if payload.received_at else None

    return service.create_payment(
        contract_id=payload.contract_id,
        amount=Decimal(str(payload.amount)),
        received_at=received_at,
        invoice_status=payload.invoice_status,
        invoiced_amount=Decimal(str(payload.invoiced_amount)) if payload.invoiced_amount else None,
        note=payload.note,
        user=ctx.user,
        confirm=payload.confirm,
    )


@router.put("/finance/payments/{payment_id}", response=ContractPaymentOut)
def update_payment(request: HttpRequest, payment_id: int, payload: ContractPaymentUpdate) -> Any:
    """更新收款记录"""
    service = _get_payment_service()
    ctx = extract_request_context(request)

    data = payload.dict(exclude_unset=True)

    if data.get("received_at"):
        data["received_at"] = parse_date(data["received_at"])

    confirm = data.pop("confirm", False)

    return service.update_payment(
        payment_id=payment_id,
        data=data,
        user=ctx.user,
        confirm=confirm,
    )


@router.delete("/finance/payments/{payment_id}")
def delete_payment(request: HttpRequest, payment_id: int) -> Any:
    """删除收款记录"""
    service = _get_payment_service()
    ctx = extract_request_context(request)
    confirm = request.GET.get("confirm") == "true"

    return service.delete_payment(
        payment_id=payment_id,
        user=ctx.user,
        confirm=confirm,
    )
