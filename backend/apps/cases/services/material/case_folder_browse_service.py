"""案件绑定文件夹的只读浏览服务（前端办案详情页「文件夹视图」）。

与 folder_scan（扫描 → 分类 → 入库成为日志/材料）不同：本服务只列出绑定
文件夹某一层的子文件夹与文件、解析单文件预览路径，不产生任何写入——
手工整理的文件夹结构（如「2-邮件往来/2026.09.29-收到法院裁定书」）
原样透出，弥补日志视图只含 AI/系统写入记录的盲区。

安全约束：
- 案件行级 ACL（与文件夹绑定端点同款 CaseAccessPolicy）；
- 子路径只收相对路径，规范化后必须收敛在 ``resolved_folder_path`` 内
  （拒绝 ``../``、绝对路径、``~``、Windows 盘符，判据同 folder_scan）；
- 仅支持本地绑定；云存储绑定返回明确提示（待接 provider.list_directory）。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from apps.cases.models import CaseFolderBinding
from apps.cases.services.case.case_access_policy import CaseAccessPolicy
from apps.cases.services.case.case_query_service import CaseQueryService
from apps.core.exceptions import NotFoundError, ValidationException

logger = logging.getLogger("apps.cases")

_DRIVE_RE = re.compile(r"^[A-Za-z]:/")


class CaseFolderBrowseService:
    """列出案件绑定文件夹的子项 / 解析可预览的单文件。"""

    def __init__(self, case_query_service: CaseQueryService | None = None) -> None:
        self._case_query_service = case_query_service or CaseQueryService(access_policy=CaseAccessPolicy())

    # ------------------------------------------------------------------
    # 对外方法
    # ------------------------------------------------------------------

    def list_entries(
        self,
        *,
        case_id: int,
        subpath: str = "",
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, Any]:
        """列出绑定文件夹下 ``subpath`` 一层的子文件夹与文件（非递归）。"""
        binding = self._get_binding_checked(
            case_id=case_id, user=user, org_access=org_access, perm_open_access=perm_open_access
        )
        root = self._local_root(binding)
        if isinstance(root, dict):  # 云/不可达的占位提示
            return {**root, "subpath": "", "parent_subpath": ""}

        target = self._resolve_subpath(root, subpath)
        if not target.exists() or not target.is_dir():
            return self._not_browsable("子文件夹不存在: " + subpath, subpath)

        folders: list[dict[str, str]] = []
        files: list[dict[str, Any]] = []
        for child in sorted(target.iterdir(), key=lambda p: p.name):
            if child.name.startswith("."):
                continue
            if child.is_dir():
                folders.append({"name": child.name, "subpath": self._subpath_of(root, child)})
            elif child.is_file():
                stat = child.stat()
                files.append(
                    {
                        "name": child.name,
                        "subpath": self._subpath_of(root, child),
                        "size": stat.st_size,
                        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                    }
                )

        parent = self._subpath_of(root, target.parent) if target != root else ""
        return {
            "browsable": True,
            "message": None,
            "path_display": binding.folder_path_display or str(binding.resolved_folder_path),
            "subpath": self._subpath_of(root, target),
            "parent_subpath": parent,
            "folders": folders,
            "files": files,
        }

    def resolve_file(
        self,
        *,
        case_id: int,
        subpath: str,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> Path:
        """解析绑定文件夹内单文件的绝对路径（供 API 层 FileResponse 预览）。"""
        binding = self._get_binding_checked(
            case_id=case_id, user=user, org_access=org_access, perm_open_access=perm_open_access
        )
        root = self._local_root(binding)
        if isinstance(root, dict):
            raise NotFoundError(message=root["message"], code="FOLDER_NOT_BROWSABLE")

        target = self._resolve_subpath(root, subpath)
        if not target.exists() or not target.is_file():
            # 与 media 保护视图同口径：路径不存在一律 404，不泄露绑定目录结构
            raise NotFoundError(message="文件不存在", code="FOLDER_FILE_NOT_FOUND")
        return target

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def normalize_subpath(subpath: str) -> str:
        """规范化相对子路径：反斜杠转正斜杠、剔除空段与「.」；非法形态直接抛错。"""
        raw = str(subpath or "").strip().replace("\\", "/")
        if not raw:
            return ""
        if raw.startswith("/") or raw.startswith("~") or _DRIVE_RE.match(raw):
            raise ValidationException(message="子路径必须使用相对路径", errors={"subpath": raw})
        parts = [part for part in raw.split("/") if part not in {"", "."}]
        if not parts:
            return ""
        if any(part == ".." for part in parts):
            raise ValidationException(message="子路径路径非法", errors={"subpath": raw})
        return "/".join(parts)

    def _get_binding_checked(
        self, *, case_id: int, user: Any, org_access: dict[str, Any] | None, perm_open_access: bool
    ) -> CaseFolderBinding:
        case = self._case_query_service.get_case(
            case_id=case_id, user=user, org_access=org_access, perm_open_access=perm_open_access
        )
        binding = CaseFolderBinding.objects.filter(case_id=case.id).first()
        if binding is None:
            raise NotFoundError(message="该案件未绑定文件夹", code="FOLDER_BINDING_NOT_FOUND")
        return binding

    def _local_root(self, binding: CaseFolderBinding) -> Path | dict[str, Any]:
        """本地绑定的可达根目录；云绑定 / 不可达目录返回 not-browsable 占位。"""
        storage_type = getattr(binding, "storage_type", "local")
        if storage_type != "local" and getattr(binding, "storage_account", None) is not None:
            return self._not_browsable("云存储绑定暂不支持在线浏览")
        root = Path(str(binding.resolved_folder_path)).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            logger.warning("case_folder_browse_root_missing", extra={"case_id": binding.case_id, "root": str(root)})
            return self._not_browsable("绑定文件夹不可达，请检查路径")
        return root

    def _resolve_subpath(self, root: Path, subpath: str) -> Path:
        normalized = self.normalize_subpath(subpath)
        # root 先 resolve：macOS 的 /var 等符号链接路径若不解析，target resolve 后会假性越界
        root = root.resolve()
        target = root if not normalized else (root / normalized).resolve()
        if target != root and not target.is_relative_to(root):
            raise ValidationException(message="子路径不在案件绑定目录内", errors={"subpath": subpath})
        return target

    @staticmethod
    def _subpath_of(root: Path, path: Path) -> str:
        """绝对路径 → 绑定根下的相对 posix 路径（根本身/根外均为空串）。"""
        try:
            rel = path.resolve().relative_to(root.resolve())
        except ValueError:
            return ""
        rel_str = rel.as_posix()
        return "" if rel_str == "." else rel_str

    @staticmethod
    def _not_browsable(message: str, subpath: str = "") -> dict[str, Any]:
        return {
            "browsable": False,
            "message": message,
            "path_display": "",
            "subpath": subpath,
            "parent_subpath": "",
            "folders": [],
            "files": [],
        }
