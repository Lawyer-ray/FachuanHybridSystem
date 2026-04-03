from __future__ import annotations

"""
Contracts Services Module
合同业务逻辑服务层

重新导出所有服务类，保持向后兼容性.
"""

# 新版服务（从子包导入）
from .contract.contract_admin_service import ContractAdminService
from .contract.batch_folder_binding_service import ContractBatchFolderBindingService
from .contract.contract_display_service import ContractDisplayService
from .contract.contract_progress_service import ContractProgressService
from .contract.contract_service import ContractService
from .contract.contract_service_adapter import ContractServiceAdapter
from .contract.invoice_upload_service import InvoiceUploadService
from .contract.contract_oa_sync_service import ContractOASyncService
from .folder.folder_binding_service import FolderBindingService

__all__ = [
    "ContractAdminService",
    "ContractBatchFolderBindingService",
    "ContractDisplayService",
    "ContractProgressService",
    "ContractService",
    "ContractServiceAdapter",
    "ContractOASyncService",
    "FolderBindingService",
]
