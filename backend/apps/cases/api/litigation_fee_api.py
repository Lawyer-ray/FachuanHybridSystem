"""API endpoints."""

from __future__ import annotations

"""
诉讼费用计算 API

API 层职责:
1. 接收 HTTP 请求,验证参数(通过 Schema)
2. 调用 Service 层方法
3. 返回响应

不包含:业务逻辑、权限检查、异常处理(依赖全局异常处理器)
"""

from decimal import Decimal
from typing import Any, ClassVar

from ninja import Router, Schema

from apps.core.exceptions import ValidationException

router = Router()


def _get_litigation_fee_calculator_service() -> Any:
    """创建 LitigationFeeCalculatorService 实例"""
    from apps.cases.services import LitigationFeeCalculatorService  # type: ignore[attr-defined]

    return LitigationFeeCalculatorService()


class FeeCalculationRequest(Schema):
    """费用计算请求"""

    target_amount: float | None = None
    preservation_amount: float | None = None
    case_type: str | None = None
    cause_of_action: str | None = None
    cause_of_action_id: int | None = None  # 新增:案由ID,用于自动识别特殊案件类型


class FeeCalculationResponse(Schema):
    """费用计算响应"""

    acceptance_fee: float | None = None
    acceptance_fee_half: float | None = None
    preservation_fee: float | None = None
    execution_fee: float | None = None
    payment_order_fee: float | None = None
    bankruptcy_fee: float | None = None
    divorce_fee: float | None = None
    personality_rights_fee: float | None = None
    ip_fee: float | None = None
    fixed_fee: float | None = None
    fee_name: str | None = None
    calculation_details: ClassVar[list[str]] = []
    # 新增字段
    special_case_type: str | None = None  # 特殊案件类型
    fee_display_text: str | None = None  # 特殊费用显示文本
    fee_range_min: float | None = None  # 费用范围最小值
    fee_range_max: float | None = None  # 费用范围最大值
    show_acceptance_fee: bool = True  # 是否显示案件受理费
    show_half_fee: bool = True  # 是否显示减半后受理费
    show_payment_order_fee: bool = False  # 是否显示支付令申请费


@router.post("/calculate-fee", response=FeeCalculationResponse)
def calculate_fee(request: Any, data: FeeCalculationRequest) -> Any:
    """
    计算诉讼费用

    根据涉案金额、财产保全金额、案件类型等参数计算各类诉讼费用.

    Args:
        data: 费用计算请求参数

    Returns:
        FeeCalculationResponse: 包含各类费用明细的响应
    """
    # 输入验证
    if data.target_amount is not None and data.target_amount < 0:
        raise ValidationException("涉案金额不能为负数")

    if data.preservation_amount is not None and data.preservation_amount < 0:
        raise ValidationException("财产保全金额不能为负数")

    # 转换为 Decimal
    target_amount = Decimal(str(data.target_amount)) if data.target_amount is not None else None
    preservation_amount = Decimal(str(data.preservation_amount)) if data.preservation_amount is not None else None

    # 调用 Service 计算费用
    service = _get_litigation_fee_calculator_service()
    result = service.calculate_all_fees(
        target_amount=target_amount,
        preservation_amount=preservation_amount,
        case_type=data.case_type,
        cause_of_action=data.cause_of_action,
        cause_of_action_id=data.cause_of_action_id,
    )

    return FeeCalculationResponse(**result)
