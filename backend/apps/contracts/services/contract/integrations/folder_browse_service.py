"""合同绑定文件夹的浏览与目录管理（前端详情页右栏「合同文件夹」树）。

通用逻辑在 ``apps.core.filesystem.bound_folder_browse.BoundFolderBrowseService``，
本类只负责合同行级 ACL 与 ``ContractFolderBinding`` 解析。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from apps.contracts.models import ContractFolderBinding
from apps.contracts.services.contract.domain.access_policy import ContractAccessPolicy
from apps.core.exceptions import NotFoundError
from apps.core.filesystem.bound_folder_browse import BoundFolderBrowseService

logger = logging.getLogger("apps.contracts")


class ContractFolderBrowseService(BoundFolderBrowseService):
    """列出合同绑定文件夹的子项 / 预览文件 / 轻量目录管理。"""

    def clean_save_as_name(self, name: str) -> str:
        """把「另存为」的名字过成落盘时用的名字（公共入口）。

        S22-06（2026-11-23 二轮审计）：``folder-save-as-intent`` 端点原来直接点取本类
        的私有成员 ``_validator.sanitize_file_name(_clean_entry_name(name))``——封装
        泄漏：Service 一改名/改签名就静默打断 API 层，而这条清洗链与 ``save_new_file``
        必须同源（登记的名字最终会成为磁盘路径部件）。现在暴露一个公共方法，把这一步
        收敛在 Service 内部。
        """
        return self._validator.sanitize_file_name(self._clean_entry_name(name))

    def _require_access(
        self, *, owner_id: int, user: Any, org_access: dict[str, Any] | None, perm_open_access: bool
    ) -> None:
        ContractAccessPolicy().ensure_access(
            contract_id=owner_id, user=user, org_access=org_access, perm_open_access=perm_open_access
        )

    def _local_root(self, owner_id: int) -> Path:
        binding = ContractFolderBinding.objects.filter(contract_id=owner_id).first()
        if binding is None:
            raise NotFoundError(message="该合同未绑定文件夹", code="FOLDER_BINDING_NOT_FOUND")
        storage_type = getattr(binding, "storage_type", "local")
        if storage_type != "local" and getattr(binding, "storage_account", None) is not None:
            raise NotFoundError(message="云存储绑定暂不支持在线浏览", code="FOLDER_CLOUD_UNSUPPORTED")
        root = Path(str(binding.folder_path)).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            logger.warning("contract_folder_browse_root_missing", extra={"contract_id": owner_id, "root": str(root)})
            raise NotFoundError(message="绑定文件夹不可达，请检查路径", code="FOLDER_ROOT_MISSING")
        return root
