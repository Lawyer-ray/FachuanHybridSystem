from __future__ import annotations

"""
Contracts App Admin模块主文件
统一管理所有合同的Admin界面
"""

from .contract_admin import ContractAdmin
from .contractpayment_admin import ContractPaymentInline
from .supplementary_agreement_admin import SupplementaryAgreementAdmin

# 所有Admin类通过装饰器自动注册
# 无需手动注册，admin/__init__.py中的类会自动处理

__all__ = [
    "ContractAdmin",
    "ContractPaymentInline",
    "SupplementaryAgreementAdmin",
]
