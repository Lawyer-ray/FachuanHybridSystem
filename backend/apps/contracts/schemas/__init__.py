"""
Contract Schemas Package

将原来的 schemas.py 拆分为多个按业务概念组织的模块,
通过此 __init__.py 统一导出所有 Schema,保持向后兼容.

模块结构:
- base.py: 共享导入和基础工具
- client_schemas.py: 客户相关 Schema
- lawyer_schemas.py: 律师、提醒、案件相关 Schema
- party_schemas.py: 合同当事人相关 Schema
- payment_schemas.py: 支付和财务相关 Schema
- supplementary_schemas.py: 补充协议相关 Schema
- folder_binding_schemas.py: 文件夹绑定相关 Schema
- contract_schemas.py: 合同核心 CRUD Schema
"""

from __future__ import annotations

from apps.reminders.schemas import ReminderOut

# Client Schemas
from .client_schemas import ClientIdentityDocOut, ClientOut

# Contract Core Schemas
from .contract_schemas import ContractAssignmentOut, ContractIn, ContractOut, ContractUpdate, UpdateLawyersIn

# Folder Binding Schemas
from .folder_binding_schemas import (
    FolderBindingCreateSchema,
    FolderBindingResponseSchema,
    FolderBrowseEntrySchema,
    FolderBrowseResponseSchema,
)

# Lawyer, Reminder, Case Schemas
from .lawyer_schemas import CaseOut, LawyerOut

# Party Schemas
from .party_schemas import ContractPartyIn, ContractPartyOut, ContractPartySourceOut

# Payment Schemas
from .payment_schemas import (
    ContractPaymentIn,
    ContractPaymentOut,
    ContractPaymentUpdate,
    FinanceStatsItem,
    FinanceStatsOut,
)

# Supplementary Agreement Schemas
from .supplementary_schemas import (
    SupplementaryAgreementIn,
    SupplementaryAgreementInput,
    SupplementaryAgreementOut,
    SupplementaryAgreementPartyIn,
    SupplementaryAgreementPartyInput,
    SupplementaryAgreementPartyOut,
    SupplementaryAgreementUpdate,
)

__all__ = [
    # Client
    "ClientIdentityDocOut",
    "ClientOut",
    # Lawyer, Reminder, Case
    "LawyerOut",
    "ReminderOut",
    "CaseOut",
    # Party
    "ContractPartyIn",
    "ContractPartyOut",
    "ContractPartySourceOut",
    # Payment
    "ContractPaymentIn",
    "ContractPaymentOut",
    "ContractPaymentUpdate",
    "FinanceStatsItem",
    "FinanceStatsOut",
    # Supplementary Agreement
    "SupplementaryAgreementPartyInput",
    "SupplementaryAgreementInput",
    "SupplementaryAgreementIn",
    "SupplementaryAgreementUpdate",
    "SupplementaryAgreementPartyIn",
    "SupplementaryAgreementPartyOut",
    "SupplementaryAgreementOut",
    # Folder Binding
    "FolderBindingCreateSchema",
    "FolderBindingResponseSchema",
    "FolderBrowseEntrySchema",
    "FolderBrowseResponseSchema",
    # Contract Core
    "UpdateLawyersIn",
    "ContractIn",
    "ContractAssignmentOut",
    "ContractOut",
    "ContractUpdate",
]
