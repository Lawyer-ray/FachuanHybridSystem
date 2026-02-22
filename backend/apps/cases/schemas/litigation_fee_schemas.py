"""诉讼费用计算相关 Schema 定义"""

from __future__ import annotations

from typing import ClassVar

from ninja import Schema


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
