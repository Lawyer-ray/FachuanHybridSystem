"""
Contracts App Admin模块主文件
统一管理所有合同的Admin界面
"""
from .contract_admin import ContractAdmin
from .contractassignment_admin import ContractAssignmentAdmin
from .contractpayment_admin import ContractPaymentAdmin, ContractPaymentInline
from .contractfinancelog_admin import ContractFinanceLogAdmin
from .contractreminder_admin import ContractReminderAdmin
from .supplementary_agreement_admin import SupplementaryAgreementAdmin

# 所有Admin类通过装饰器自动注册
# 无需手动注册，admin/__init__.py中的类会自动处理

__all__ = [
    'ContractAdmin',
    'ContractAssignmentAdmin',
    'ContractPaymentAdmin',
    'ContractFinanceLogAdmin',
    'ContractReminderAdmin',
    'ContractPaymentInline',
    'SupplementaryAgreementAdmin'
]
