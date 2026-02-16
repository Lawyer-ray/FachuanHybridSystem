"""
保险询价数据类定义

包含保险公司信息和报价结果的数据类.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass
class InsuranceCompany:
    """保险公司信息"""

    c_id: str
    c_code: str
    c_name: str


@dataclass
class PremiumResult:
    """报价结果"""

    company: InsuranceCompany
    premium: Decimal | None
    status: str  # "success" or "failed"
    error_message: str | None
    response_data: dict[str, Any] | None
    request_info: dict[str, Any] | None = None  # 请求信息(用于调试)
