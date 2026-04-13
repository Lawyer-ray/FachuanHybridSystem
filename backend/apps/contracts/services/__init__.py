from __future__ import annotations

"""
Contracts Services Module
合同业务逻辑服务层

重新导出所有服务类，保持向后兼容性.
"""

# 新版服务（从子包导入）
from .contract.admin import ContractAdminService
from .contract.contract_service import ContractService
from .contract.contract_service_adapter import ContractServiceAdapter
from .contract.integrations import ContractBatchFolderBindingService, ContractOASyncService, InvoiceUploadService
from .contract.query import ContractDisplayService, ContractProgressService
from .folder.folder_binding_service import FolderBindingService
from .payment.contract_payment_service import ContractPaymentService
from .supplementary.supplementary_agreement_service import SupplementaryAgreementService

__all__ = [
    "ContractAdminService",
    "ContractBatchFolderBindingService",
    "ContractDisplayService",
    "ContractProgressService",
    "ContractService",
    "ContractServiceAdapter",
    "ContractOASyncService",
    "ContractPaymentService",
    "FolderBindingService",
    "SupplementaryAgreementService",
]
