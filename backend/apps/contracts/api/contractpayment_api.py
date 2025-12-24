"""
合同收款 API 层
符合三层架构规范：只做请求/响应处理，业务逻辑在 Service 层
"""
from typing import Optional
from ninja import Router
from django.utils.dateparse import parse_date

from ..schemas import ContractPaymentIn, ContractPaymentOut, ContractPaymentUpdate
from ..services.contract_payment_service import ContractPaymentService

router = Router()


def _get_payment_service() -> ContractPaymentService:
    """工厂函数：创建 ContractPaymentService 实例"""
    return ContractPaymentService()


@router.get("/finance/payments", response=list[ContractPaymentOut])
def list_payments(
    request,
    contract_id: Optional[int] = None,
    invoice_status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """获取收款列表"""
    service = _get_payment_service()
    user = getattr(request, "user", None)
    perm_open_access = getattr(request, "perm_open_access", False)
    
    # 解析日期参数
    d1 = parse_date(start_date) if start_date else None
    d2 = parse_date(end_date) if end_date else None
    
    return service.list_payments(
        contract_id=contract_id,
        invoice_status=invoice_status,
        start_date=d1,
        end_date=d2,
        user=user,
        perm_open_access=perm_open_access,
    )


@router.post("/finance/payments", response=ContractPaymentOut)
def create_payment(request, payload: ContractPaymentIn):
    """创建收款记录"""
    service = _get_payment_service()
    user = getattr(request, "user", None)
    
    # 解析日期
    received_at = parse_date(payload.received_at) if payload.received_at else None
    
    return service.create_payment(
        contract_id=payload.contract_id,
        amount=payload.amount,
        received_at=received_at,
        invoice_status=payload.invoice_status,
        invoiced_amount=payload.invoiced_amount,
        note=payload.note,
        user=user,
        confirm=payload.confirm,
    )


@router.put("/finance/payments/{payment_id}", response=ContractPaymentOut)
def update_payment(request, payment_id: int, payload: ContractPaymentUpdate):
    """更新收款记录"""
    service = _get_payment_service()
    user = getattr(request, "user", None)
    
    # 构建更新数据
    data = payload.dict(exclude_unset=True)
    
    # 解析日期
    if "received_at" in data and data["received_at"]:
        data["received_at"] = parse_date(data["received_at"])
    
    # 提取 confirm 参数
    confirm = data.pop("confirm", False)
    
    return service.update_payment(
        payment_id=payment_id,
        data=data,
        user=user,
        confirm=confirm,
    )


@router.delete("/finance/payments/{payment_id}")
def delete_payment(request, payment_id: int):
    """删除收款记录"""
    service = _get_payment_service()
    user = getattr(request, "user", None)
    confirm = request.GET.get("confirm") == "true"
    
    return service.delete_payment(
        payment_id=payment_id,
        user=user,
        confirm=confirm,
    )
