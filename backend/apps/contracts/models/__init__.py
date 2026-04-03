from __future__ import annotations

"""
Contracts 模块模型层

重新导出所有模型类、枚举类,保持向后兼容性.
所有旧的导入路径 `from apps.contracts.models import X` 继续有效.
"""

# client_payment.py - 客户回款相关模型
from .client_payment import ClientPaymentRecord

# contract.py - 合同核心模型和枚举
from .contract import Contract, FeeMode

# finalized_material.py - 结案材料相关模型和枚举
from .finalized_material import FinalizedMaterial, MaterialCategory

# finance.py - 财务日志相关模型和枚举
from .finance import ContractFinanceLog, LogLevel

# folder_binding.py - 文件夹绑定相关模型
from .folder_binding import ContractFolderBinding

# batch_folder_binding.py - 合同类型根目录预设
from .batch_folder_binding import ContractTypeFolderRootPreset

# folder_scan_session.py - 文件夹扫描会话
from .folder_scan_session import ContractFolderScanSession, ContractFolderScanStatus

# contract_oa_sync_session.py - OA同步会话
from .contract_oa_sync_session import ContractOASyncSession, ContractOASyncStatus

# invoice.py - 发票相关模型
from .invoice import Invoice

# party.py - 当事人相关模型和枚举
from .party import ContractAssignment, ContractParty, PartyRole

# payment.py - 收款相关模型和枚举
from .payment import ContractPayment, InvoiceStatus

# supplementary.py - 补充协议相关模型
from .supplementary import SupplementaryAgreement, SupplementaryAgreementParty

__all__ = [
    # contract.py
    "Contract",
    "FeeMode",
    # party.py
    "ContractParty",
    "PartyRole",
    "ContractAssignment",
    # payment.py
    "ContractPayment",
    "InvoiceStatus",
    # finance.py
    "ContractFinanceLog",
    "LogLevel",
    # supplementary.py
    "SupplementaryAgreement",
    "SupplementaryAgreementParty",
    # folder_binding.py
    "ContractFolderBinding",
    # batch_folder_binding.py
    "ContractTypeFolderRootPreset",
    # folder_scan_session.py
    "ContractFolderScanSession",
    "ContractFolderScanStatus",
    # contract_oa_sync_session.py
    "ContractOASyncSession",
    "ContractOASyncStatus",
    # finalized_material.py
    "FinalizedMaterial",
    "MaterialCategory",
    # invoice.py
    "Invoice",
    # client_payment.py
    "ClientPaymentRecord",
]
