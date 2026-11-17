"""contracts 集成服务工厂函数。

覆盖 contract/integrations 下没有既有工厂的 5 个服务（material / invoice_upload /
oa_party_resolution / oa_sync / batch_folder_binding）。admin 层只路由到这里，不再裸构造 Service。
"""

from __future__ import annotations

from .batch_folder_binding_service import ContractBatchFolderBindingService
from .contract_oa_sync_service import ContractOASyncService
from .invoice_upload_service import InvoiceUploadService
from .material_service import MaterialService
from .oa_party_resolution_service import OaPartyResolutionService


def build_material_service() -> MaterialService:
    """构建归档材料文件服务实例（无状态，可安全缓存）。"""
    return MaterialService()


def build_invoice_upload_service() -> InvoiceUploadService:
    """构建发票上传服务实例（无状态，可安全缓存）。"""
    return InvoiceUploadService()


def build_oa_party_resolution_service() -> OaPartyResolutionService:
    """构建 OA 当事人解析服务实例，保留 `__init__` 内部对 ClientPartyResolveService 的兜底。"""
    return OaPartyResolutionService()


def build_contract_oa_sync_service() -> ContractOASyncService:
    """构建合同 OA 同步服务实例（无状态，可安全缓存）。"""
    return ContractOASyncService()


def build_contract_batch_folder_binding_service() -> ContractBatchFolderBindingService:
    """构建批量绑定文件夹服务实例。

    不注入 `folder_binding_service`：构造参数默认走内部惰性兜底，与改造前逐字等价。
    """
    return ContractBatchFolderBindingService()
