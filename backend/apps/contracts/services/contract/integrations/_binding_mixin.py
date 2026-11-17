"""绑定与存储提供者（``ContractFolderScanService`` 的 合同存在性 / 可访问绑定 / 云存储 provider 解析）。

从 ``folder_scan_service.py`` 按子域拆出的 mixin，**方法体仍定义在宿主模块的语义下**：
本模块不持有任何业务名引用，一律经 ``self._host`` 回查 ``folder_scan_service`` 的模块 globals。

.. important::
   在本文件里**禁止**直接写 ``Contract`` / ``Path`` / ``ContractFolderScanSession`` 等裸名——
   它们在本模块 globals 里不存在，会 ``NameError``；且测试 patch 的是**宿主模块的绑定位置**
   （``folder_scan_service.Contract`` 等 53 处），只有经 ``self._host`` 回查才能命中。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.contracts.models import ContractFolderBinding

from apps.core.exceptions import NotFoundError, ValidationException

from ._scan_service_contract import _ScanServiceContract

logger = logging.getLogger(__name__)


class _BindingMixin(_ScanServiceContract):
    """子域 mixin：具体方法见 ``folder_scan_service.ContractFolderScanService``。"""

    def _ensure_contract_exists(self, contract_id: int) -> None:  # pragma: no cover
        if self._host.Contract.objects.filter(id=contract_id).exists():
            return
        raise NotFoundError("合同不存在")

    def _get_accessible_binding(self, contract_id: int) -> ContractFolderBinding:  # pragma: no cover
        binding = self._host.ContractFolderBinding.objects.filter(contract_id=contract_id).first()
        if not binding:
            raise ValidationException(message="未绑定文件夹", errors={"contract_id": contract_id})

        storage_type = getattr(binding, "storage_type", "local")
        if storage_type == "local":
            folder = self._host.Path(binding.folder_path)
            if not folder.exists() or not folder.is_dir():
                raise ValidationException(message="绑定文件夹不可访问", errors={"folder_path": binding.folder_path})
        else:
            # Cloud storage: use provider to check accessibility
            from apps.cloud_storage.factory import create_provider_for_binding

            provider = create_provider_for_binding(binding)
            try:
                accessible = provider.is_dir(binding.folder_path) or provider.exists(binding.folder_path)
            except Exception:
                accessible = False
            if not accessible:
                raise ValidationException(message="绑定文件夹不可访问", errors={"folder_path": binding.folder_path})

        return binding

    def _resolve_session_storage_provider(self, session: Any) -> Any | None:
        """从 session → contract → binding 链路解析云存储 provider；失败按本地存储（None）。"""
        try:
            binding = session.contract.folder_binding
            return self._make_provider_for_binding(binding)
        except Exception:
            logger.debug(
                "解析云存储 provider 失败（已忽略，按本地存储确认导入）: contract_id=%s session_id=%s",
                session.contract_id,
                session.id,
                exc_info=True,
            )
            return None

    def _make_provider_for_binding(self, binding: ContractFolderBinding) -> Any | None:  # pragma: no cover
        """Create a cloud storage provider for the binding, or None for local."""
        storage_type = getattr(binding, "storage_type", "local")
        if storage_type == "local":
            return None
        from apps.cloud_storage.factory import create_provider_for_binding

        return create_provider_for_binding(binding)
