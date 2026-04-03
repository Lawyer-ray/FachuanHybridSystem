"""
合同文件夹绑定服务
处理合同与本地文件夹绑定的业务逻辑
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from apps.contracts.models import Contract, ContractFolderBinding
from apps.core.filesystem import (
    FolderBindingCrudService,
    FolderBrowsePolicy,
    FolderFilesystemService,
    FolderPathValidator,
)
from apps.core.protocols import IDocumentTemplateBindingService

from .contract_subdir_path_resolver import ContractSubdirPathResolver

logger = logging.getLogger("apps.contracts")


class FolderBindingService(FolderBindingCrudService):
    """
    文件夹绑定服务

    职责:
    1. 管理合同与文件夹的绑定关系
    2. 验证文件夹路径格式
    3. 处理文件保存到绑定文件夹
    4. 管理子目录结构
    5. 根据文书模板绑定配置确定保存路径
    """

    # 默认子目录配置(仅在没有文书模板绑定配置时使用)
    DEFAULT_SUBDIRS: ClassVar = {
        "contract_documents": "合同文书",
        "supplementary_agreements": "补充协议",
        "other_files": "其他文件",
    }

    binding_model = ContractFolderBinding
    owner_model = Contract
    owner_rel_field: str = "contract"
    owner_id_field: str = "contract_id"
    owner_label: str = "合同"

    def __init__(
        self,
        document_template_binding_service: IDocumentTemplateBindingService | None = None,
        filesystem_service: FolderFilesystemService | None = None,
        path_validator: FolderPathValidator | None = None,
        browse_policy: FolderBrowsePolicy | None = None,
    ) -> None:
        super().__init__(
            filesystem_service=filesystem_service,
            path_validator=path_validator,
            browse_policy=browse_policy,
            roots_setting_name="FOLDER_BROWSE_ROOTS",
            fallback_roots_setting_name="CONTRACT_FOLDER_BROWSE_ROOTS",
        )
        self._subdir_path_resolver = ContractSubdirPathResolver(
            template_binding_service=document_template_binding_service,
        )

    def _resolve_subdir_path(self, *, owner_type: str, subdir_key: str) -> str | None:
        return self._subdir_path_resolver.resolve(case_type=owner_type, subdir_key=subdir_key)

    def _sanitize_file_name(self, file_name: str) -> str:
        """兼容旧测试入口：委托给统一路径校验器。"""
        return self.path_validator.sanitize_file_name(file_name)

    def _normalize_relative_path(self, relative_path: str) -> str:
        """兼容旧测试入口：委托给统一路径校验器。"""
        return self.path_validator.normalize_relative_path(relative_path)

    # 为了保持向后兼容,提供 contract_id 参数的便捷方法
    def create_binding_for_contract(self, contract_id: int, folder_path: str) -> Any:
        """为合同创建文件夹绑定(便捷方法)"""
        return self.create_binding(owner_id=contract_id, folder_path=folder_path)

    def update_binding_for_contract(self, contract_id: int, folder_path: str) -> Any:
        """为合同更新文件夹绑定(便捷方法)"""
        return self.update_binding(owner_id=contract_id, folder_path=folder_path)

    def delete_binding_for_contract(self, contract_id: int) -> bool:
        """删除合同的文件夹绑定(便捷方法)"""
        return self.delete_binding(owner_id=contract_id)

    def get_binding_for_contract(self, contract_id: int) -> ContractFolderBinding | None:
        """获取合同的文件夹绑定(便捷方法)"""
        binding = self.get_binding(owner_id=contract_id)
        return binding

    def save_file_for_contract(
        self, contract_id: int, file_content: bytes, file_name: str, subdir_key: str = "contract_documents"
    ) -> str | None:
        """为合同保存文件到绑定文件夹(便捷方法)"""
        return self.save_file_to_bound_folder(
            owner_id=contract_id,
            file_content=file_content,
            file_name=file_name,
            subdir_key=subdir_key,
        )

    def extract_zip_for_contract(self, contract_id: int, zip_content: bytes) -> str | None:
        """为合同解压 ZIP 到绑定文件夹(便捷方法)"""
        return self.extract_zip_to_bound_folder(contract_id=contract_id, zip_content=zip_content)  # type: ignore

    def save_file_to_bound_folder(  # type: ignore
        self,
        owner_id: int,
        file_content: bytes,
        file_name: str,
        subdir_key: str = "contract_documents",
    ) -> str | None:
        """保存文件到绑定文件夹（实现 IContractFolderBindingService 协议）"""
        return super().save_file_to_bound_folder(
            owner_id=owner_id,
            file_content=file_content,
            file_name=file_name,
            subdir_key=subdir_key,
        )

    def extract_zip_to_bound_folder(self, contract_id: int, zip_content: bytes) -> str | None:  # type: ignore
        """解压 ZIP 到绑定文件夹（实现 IContractFolderBindingService 协议）"""
        return super().extract_zip_to_bound_folder(owner_id=contract_id, zip_content=zip_content)
