"""扫描范围与路径校验（``ContractFolderScanService`` 的 子文件夹解析 / 越界校验 / 相对路径归一化）。

从 ``folder_scan_service.py`` 按子域拆出的 mixin，**方法体仍定义在宿主模块的语义下**：
本模块不持有任何业务名引用，一律经 ``self._host`` 回查 ``folder_scan_service`` 的模块 globals。

.. important::
   在本文件里**禁止**直接写 ``Contract`` / ``Path`` / ``ContractFolderScanSession`` 等裸名——
   它们在本模块 globals 里不存在，会 ``NameError``；且测试 patch 的是**宿主模块的绑定位置**
   （``folder_scan_service.Contract`` 等 53 处），只有经 ``self._host`` 回查才能命中。
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from apps.core.exceptions import ValidationException

from ._scan_service_contract import _ScanServiceContract

logger = logging.getLogger(__name__)


class _ScanScopeMixin(_ScanServiceContract):
    """子域 mixin：具体方法见 ``folder_scan_service.ContractFolderScanService``。"""

    def _extract_scan_subfolder(self, payload: dict[str, Any] | None) -> str:
        scope = (payload or {}).get("scan_scope") or {}
        return str(scope.get("scan_subfolder") or "").strip()

    def _resolve_scan_scope(
        self,
        root_folder: str,
        scan_subfolder: str,
        storage_provider: Any | None = None,
    ) -> dict[str, str]:  # pragma: no cover
        normalized_subfolder = self._normalize_scan_subfolder(scan_subfolder)

        if storage_provider is not None:
            # Cloud storage: use PurePosixPath for path arithmetic
            from pathlib import PurePosixPath

            root = PurePosixPath(root_folder)
            scan_path = root
            if normalized_subfolder:
                scan_path = root / normalized_subfolder
                # Normalize to prevent traversal
                scan_path = PurePosixPath("/") / str(scan_path).lstrip("/")
                root_str = str(root)
                scan_str = str(scan_path)
                is_within = (
                    scan_str.startswith(root_str + "/")
                    or scan_str == root_str
                    or (root_str == "/" and scan_str.startswith("/") and scan_str != "/")
                )
                if not is_within:
                    raise ValidationException(
                        message="扫描子文件夹越界",
                        errors={"scan_subfolder": normalized_subfolder},
                    )
                # 与 _get_accessible_binding 一致：先 is_dir()（PROPFIND）再 exists() 兜底。
                # 坚果云等 WebDAV 的 HEAD 对目录返回 403，单用 exists() 会把存在的子目录判死。
                if not (storage_provider.is_dir(str(scan_path)) or storage_provider.exists(str(scan_path))):
                    raise ValidationException(
                        message="扫描子文件夹不可访问",
                        errors={"scan_subfolder": normalized_subfolder},
                    )

            return {
                "root_folder": str(root),
                "scan_folder": str(scan_path),
                "scan_subfolder": normalized_subfolder,
            }

        # Local filesystem
        root_local = self._host.Path(root_folder).expanduser().resolve()
        scan_path_local = root_local
        if normalized_subfolder:
            scan_path_local = (root_local / normalized_subfolder).resolve()
            if not self._is_within_root(root_local, scan_path_local):
                raise ValidationException(
                    message="扫描子文件夹越界",
                    errors={"scan_subfolder": normalized_subfolder},
                )
            if not scan_path_local.exists() or not scan_path_local.is_dir():
                raise ValidationException(
                    message="扫描子文件夹不可访问",
                    errors={"scan_subfolder": normalized_subfolder},
                )

        return {
            "root_folder": root_local.as_posix(),
            "scan_folder": scan_path_local.as_posix(),
            "scan_subfolder": normalized_subfolder,
        }

    def _normalize_scan_subfolder(self, scan_subfolder: str) -> str:
        raw = str(scan_subfolder or "").strip().replace("\\", "/")
        if not raw:
            return ""
        if raw.startswith("/") or raw.startswith("~") or re.match(r"^[A-Za-z]:/", raw):
            raise ValidationException(message="扫描子文件夹必须使用相对路径", errors={"scan_subfolder": raw})

        parts = [part for part in raw.split("/") if part not in {"", "."}]
        if not parts:
            return ""
        if any(part == ".." for part in parts):
            raise ValidationException(message="扫描子文件夹路径非法", errors={"scan_subfolder": raw})
        return "/".join(parts)

    def _is_within_root(self, root: Path, target: Path) -> bool:
        # 解耦（2026-10-19）：实现上提 apps.core.filesystem.path_confinement（与 cases 侧逐字相同）
        from apps.core.filesystem.path_confinement import is_within

        return is_within(root, target)
