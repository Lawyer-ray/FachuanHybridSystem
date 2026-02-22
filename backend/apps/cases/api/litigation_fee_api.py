"""
诉讼费用计算 API

API 层职责:
1. 接收 HTTP 请求,验证参数(通过 Schema)
2. 调用 Service 层方法
3. 返回响应

不包含:业务逻辑、权限检查、异常处理(依赖全局异常处理器)
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from ninja import Router

from apps.cases.schemas.litigation_fee_schemas import FeeCalculationRequest, FeeCalculationResponse

router = Router()


def _get_litigation_fee_calculator_service() -> Any:
    """创建 LitigationFeeCalculatorService 实例"""
    from apps.cases.services import LitigationFeeCalculatorService  # type: ignore[attr-defined]

    return LitigationFeeCalculatorService()


@router.post("/calculate-fee", response=FeeCalculationResponse)
def calculate_fee(request: HttpRequest, data: FeeCalculationRequest) -> FeeCalculationResponse:
    """
    计算诉讼费用

    根据涉案金额、财产保全金额、案件类型等参数计算各类诉讼费用.

    Args:
        data: 费用计算请求参数

    Returns:
        FeeCalculationResponse: 包含各类费用明细的响应
    """
    service = _get_litigation_fee_calculator_service()

    # 输入验证和 Decimal 转换由 Service 层负责
    target_amount, preservation_amount = service.validate_and_convert_fee_inputs(
        target_amount=data.target_amount,
        preservation_amount=data.preservation_amount,
    )

    result: dict[str, Any] = service.calculate_all_fees(
        target_amount=target_amount,
        preservation_amount=preservation_amount,
        case_type=data.case_type,
        cause_of_action=data.cause_of_action,
        cause_of_action_id=data.cause_of_action_id,
    )

    return FeeCalculationResponse(**result)
