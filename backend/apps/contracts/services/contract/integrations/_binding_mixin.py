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

from django.core.exceptions import ObjectDoesNotExist

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
        """从 session → contract → binding 链路解析云存储 provider；未绑定按本地存储（None）。

        S13-30（2026-11-23 二轮审计）：原实现 ``except Exception`` 把**任何**异常都
        抹平成「本地存储」（provider 构造失败、凭据缺失也不例外），于是云端绑定被当
        本地处理：``source_path`` 的相对路径去进程 CWD 下找 → 整批导入报「源文件
        不存在」，根因只在 debug 日志里；CWD 下恰好有同名文件则读错文件入库。现在
        只把「未绑定文件夹」（``ObjectDoesNotExist``）当本地，其余异常原样上抛——
        下游 ``_import_pipeline`` 本就能承接真实错误（云端失败会显式 raise）。
        """
        try:
            binding = session.contract.folder_binding
        except ObjectDoesNotExist:
            logger.debug(
                "合同未绑定文件夹，按本地存储确认导入: contract_id=%s session_id=%s",
                session.contract_id,
                session.id,
            )
            return None
        return self._make_provider_for_binding(binding)

    def _make_provider_for_binding(self, binding: ContractFolderBinding) -> Any | None:  # pragma: no cover
        """Create a cloud storage provider for the binding, or None for local."""
        storage_type = getattr(binding, "storage_type", "local")
        if storage_type == "local":
            return None
        from apps.cloud_storage.factory import create_provider_for_binding

        return create_provider_for_binding(binding)
