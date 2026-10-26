"""绑定文件夹浏览 + 目录管理的通用实现（案件 / 合同共用）。

子类只需实现两个钩子：

- ``_require_access``：属主行级 ACL（失败抛 ``PermissionDenied`` / ``NotFoundError``）；
- ``_local_root``：解析绑定的本地根目录。未绑定、云存储绑定、目录不可达
  一律抛 ``NotFoundError``（message 面向用户），由 API 层统一转 404。

安全口径（与 v27.7.12 的案件版一致）：

- 子路径只收相对路径，规范化后必须收敛在绑定根内（拒 ``../``、绝对路径、
  ``~``、Windows 盘符；``resolve()`` 后 ``is_relative_to`` 兜底符号链接逃逸）；
- 新建 / 重命名的名字拒路径分隔符、``..``、隐藏前缀与 Windows 非法字符；
- 上传文件名经 ``FolderPathValidator.sanitize_file_name`` 清洗，同名自动
  ``_1`` 序号错开；单文件大小上限 ``MAX_UPLOAD_BYTES``。
"""

from __future__ import annotations

import logging
import os
import re
import shutil
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any, ClassVar

from apps.core.exceptions import ConflictError, NotFoundError, ValidationException
from apps.core.filesystem.path_validator import FolderPathValidator

logger = logging.getLogger("apps.core.filesystem")


def _count_child_files(path: Path) -> int:
    """统计目录下**一层**文件数（不递归、跳隐藏文件）。

    只扫一层：事项目录的更深层是它自己的附件目录，递归既慢又可能踩到
    巨大的归档目录；「有没有交付物」看一层就够。
    """
    try:
        return sum(1 for c in path.iterdir() if c.is_file() and not c.name.startswith("."))
    except OSError:
        # 权限不足 / 文件已删：按 0 处理，不让整个列表接口失败
        return 0


class BoundFolderBrowseService:
    """本地绑定文件夹的只读浏览（列目录 / 预览）与轻量管理（新建 / 上传 / 重命名）。"""

    MAX_UPLOAD_BYTES: ClassVar[int] = 200 * 1024 * 1024
    # 删除 = 移到绑定根下该目录（带时间戳，可恢复），不做物理删除
    TRASH_DIR: ClassVar[str] = "_已删除"
    _NAME_MAX_LEN: ClassVar[int] = 200
    _DRIVE_RE = re.compile(r"^[A-Za-z]:/")
    _ILLEGAL_NAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

    def __init__(self) -> None:
        self._validator = FolderPathValidator()

    # ------------------------------------------------------------------
    # 子类钩子
    # ------------------------------------------------------------------

    def _require_access(
        self, *, owner_id: int, user: Any, org_access: dict[str, Any] | None, perm_open_access: bool
    ) -> None:
        raise NotImplementedError

    def _local_root(self, owner_id: int) -> Path:
        raise NotImplementedError

    # ------------------------------------------------------------------
    # 对外方法（子类以同签名暴露，保持各自域的调用习惯）
    # ------------------------------------------------------------------

    def list_entries(
        self,
        *,
        owner_id: int,
        subpath: str = "",
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, Any]:
        """列出绑定文件夹下 ``subpath`` 一层的子文件夹与文件（非递归、跳隐藏）。"""
        root, path_display = self._checked_root(
            owner_id=owner_id, user=user, org_access=org_access, perm_open_access=perm_open_access
        )
        target = self._resolve_subpath(root, subpath)
        if not target.exists() or not target.is_dir():
            raise NotFoundError(message="子文件夹不存在", code="FOLDER_NOT_FOUND")

        # 值类型是 str | int：file_count 是数字，其余是路径/名称
        folders: list[dict[str, Any]] = []
        files: list[dict[str, Any]] = []
        for child in sorted(target.iterdir(), key=lambda p: p.name):
            if child.name.startswith("."):
                continue
            if child.is_dir():
                folders.append(
                    {
                        "name": child.name,
                        "subpath": self._subpath_of(root, child),
                        # 子目录下的文件数（不含子目录）：常法页据它判断「事项是否已交付」。
                        # 在这里顺手算而不是让前端逐个请求——30 个事项就是 30 次往返；
                        # 而这层 iterdir 已经在跑，多一次浅扫的代价远小于网络开销。
                        "file_count": _count_child_files(child),
                    }
                )
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
            "path_display": path_display,
            "subpath": self._subpath_of(root, target),
            "parent_subpath": parent,
            "folders": folders,
            "files": files,
        }

    def resolve_file(
        self,
        *,
        owner_id: int,
        subpath: str,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> Path:
        """解析绑定文件夹内单文件的绝对路径（供 API 层 FileResponse 预览）。"""
        root, _ = self._checked_root(
            owner_id=owner_id, user=user, org_access=org_access, perm_open_access=perm_open_access
        )
        target = self._resolve_subpath(root, subpath)
        if not target.exists() or not target.is_file():
            # 与 media 保护视图同口径：路径不存在一律 404，不泄露绑定目录结构
            raise NotFoundError(message="文件不存在", code="FOLDER_FILE_NOT_FOUND")
        return target

    def mkdir(
        self,
        *,
        owner_id: int,
        subpath: str,
        name: str,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, str]:
        """在 ``subpath``（空 = 绑定根）下新建子文件夹。"""
        root, _ = self._checked_root(
            owner_id=owner_id, user=user, org_access=org_access, perm_open_access=perm_open_access
        )
        parent = self._resolve_subpath(root, subpath)
        if not parent.exists() or not parent.is_dir():
            raise NotFoundError(message="父文件夹不存在", code="FOLDER_NOT_FOUND")
        clean = self._clean_entry_name(name)
        target = parent / clean
        if target.exists():
            raise ValidationException(message="同名项目已存在", errors={"name": clean})
        target.mkdir()
        logger.info("bound_folder_mkdir", extra={"owner_id": owner_id, "subpath": subpath, "entry_name": clean})
        return {"subpath": self._subpath_of(root, target), "name": clean}

    def save_uploads(
        self,
        *,
        owner_id: int,
        subpath: str,
        files: list[Any],
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, Any]:
        """把上传文件流式落盘到 ``subpath`` 目录；同名自动加序号，不覆盖既有文件。"""
        if not files:
            raise ValidationException(message="未收到文件", errors={"files": "空"})
        root, _ = self._checked_root(
            owner_id=owner_id, user=user, org_access=org_access, perm_open_access=perm_open_access
        )
        target_dir = self._resolve_subpath(root, subpath)
        if not target_dir.exists() or not target_dir.is_dir():
            raise NotFoundError(message="目标文件夹不存在", code="FOLDER_NOT_FOUND")

        saved: list[dict[str, str]] = []
        for f in files:
            size = getattr(f, "size", 0) or 0
            if size > self.MAX_UPLOAD_BYTES:
                raise ValidationException(
                    message=f"单个文件超过上限 {self.MAX_UPLOAD_BYTES // (1024 * 1024)}MB",
                    errors={"files": getattr(f, "name", "")},
                )
            clean = self._validator.sanitize_file_name(getattr(f, "name", "") or "")
            dest = self._unique_destination(target_dir, clean)
            # 绑定文件夹是用户本地工作目录（非 media 仓库），流式分块直写避免大文件整读进内存
            with open(dest, "wb") as out:
                for chunk in f.chunks():
                    out.write(chunk)
            saved.append({"name": dest.name, "subpath": self._subpath_of(root, dest)})

        logger.info("bound_folder_upload", extra={"owner_id": owner_id, "subpath": subpath, "count": len(saved)})
        return {"saved": saved}

    def save_file_content(
        self,
        *,
        owner_id: int,
        subpath: str,
        data: bytes,
        expect_mtime: float | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, Any]:
        """原地覆写绑定文件夹内的已有文件（编辑器保存）。

        **与 save_uploads 的区别**：那个是「同名自动加序号、不覆盖」（拖拽上传
        不能误盖旧稿）；这里是明确的「覆盖这一份」，不能加序号——加序号就变成
        另存为，律师看到的还是旧内容。

        **不保留备份**：产品决定（客户原稿覆盖即覆盖）。备份带在 `_历史/` 下
        会让目录变脏，而真正的版本追溯是审查链路的 `DocumentVersion` 干的活。

        **乐观锁**：`expect_mtime` 是打开时文件的 mtime。两人同开同一份时，
        后保存的一方 mtime 已经变了，直接覆写会静默丢掉前一个人的修改。
        不一致就报 409，让前端提示「文件已被他人修改」。
        """
        root, _ = self._checked_root(
            owner_id=owner_id, user=user, org_access=org_access, perm_open_access=perm_open_access
        )
        target = self._resolve_subpath(root, subpath)
        if not target.exists():
            raise NotFoundError(message="文件不存在，无法保存", code="FOLDER_NOT_FOUND")
        if target.is_dir():
            raise ValidationException(message="目标是文件夹，不能写入", errors={"subpath": subpath})
        if len(data) > self.MAX_UPLOAD_BYTES:
            raise ValidationException(
                message=f"文件超过上限 {self.MAX_UPLOAD_BYTES // (1024 * 1024)}MB",
                errors={"subpath": subpath},
            )

        if expect_mtime is not None:
            actual = target.stat().st_mtime
            # 1 秒容差：不同文件系统的 mtime 精度不同（ext4 纳秒 / HFS+ 秒），
            # 严格相等会误报冲突
            if abs(actual - expect_mtime) > 1.0:
                raise ConflictError(
                    message="文件已被他人修改，请重新打开后再保存",
                    code="FILE_MODIFIED",
                    errors={"mtime": actual, "expect": expect_mtime},
                )

        # 原子替换：先写临时文件再 os.replace，避免写一半断电/异常留下半截文档
        tmp = target.with_name(target.name + f".tmp{os.getpid()}")
        try:
            with open(tmp, "wb") as out:
                out.write(data)
            os.replace(tmp, target)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)

        logger.info(
            "bound_folder_overwrite",
            extra={"owner_id": owner_id, "subpath": subpath, "size": len(data)},
        )
        return {
            "subpath": subpath,
            "name": target.name,
            "size": len(data),
            "modified_at": datetime.fromtimestamp(target.stat().st_mtime, tz=UTC).isoformat(),
        }

    def save_new_file(
        self,
        *,
        owner_id: int,
        subpath: str,
        name: str,
        data: bytes,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, Any]:
        """在 `subpath` 所在目录另存为新文件（同名自动加序号，不覆盖）。

        `subpath` 指向**源文件**（用来定位目录），`name` 是新文件名。
        走 `_unique_destination` 与上传同一套同名去重逻辑。
        """
        root, _ = self._checked_root(
            owner_id=owner_id, user=user, org_access=org_access, perm_open_access=perm_open_access
        )
        src = self._resolve_subpath(root, subpath)
        if src.is_dir():
            raise ValidationException(message="目标是文件夹，不能另存", errors={"subpath": subpath})
        target_dir = src.parent
        clean = self._validator.sanitize_file_name(self._clean_entry_name(name))
        if len(data) > self.MAX_UPLOAD_BYTES:
            raise ValidationException(
                message=f"文件超过上限 {self.MAX_UPLOAD_BYTES // (1024 * 1024)}MB",
                errors={"name": clean},
            )

        dest = self._unique_destination(target_dir, clean)
        tmp = dest.with_name(dest.name + f".tmp{os.getpid()}")
        try:
            with open(tmp, "wb") as out:
                out.write(data)
            os.replace(tmp, dest)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)

        logger.info(
            "bound_folder_save_as",
            extra={"owner_id": owner_id, "src": subpath, "dest": self._subpath_of(root, dest)},
        )
        return {"subpath": self._subpath_of(root, dest), "name": dest.name, "size": len(data)}

    def rename(
        self,
        *,
        owner_id: int,
        subpath: str,
        new_name: str,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, str]:
        """重命名 ``subpath`` 指向的文件或文件夹（同目录内改名）。"""
        root, _ = self._checked_root(
            owner_id=owner_id, user=user, org_access=org_access, perm_open_access=perm_open_access
        )
        target = self._resolve_subpath(root, subpath)
        if not target.exists():
            raise NotFoundError(message="目标不存在", code="FOLDER_NOT_FOUND")
        if target == root:
            raise ValidationException(message="不能重命名绑定根目录", errors={"subpath": subpath})
        clean = self._clean_entry_name(new_name)
        dest = target.parent / clean
        if dest.exists():
            raise ValidationException(message="同名项目已存在", errors={"name": clean})
        target.rename(dest)
        logger.info("bound_folder_rename", extra={"owner_id": owner_id, "subpath": subpath, "entry_name": clean})
        return {"subpath": self._subpath_of(root, dest), "name": clean}

    def copy_entry(
        self,
        *,
        owner_id: int,
        subpath: str,
        dest_subpath: str = "",
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, str]:
        """把 ``subpath`` 指向的文件/文件夹复制到 ``dest_subpath`` 目录（同名自动加序号）。"""
        root, _ = self._checked_root(
            owner_id=owner_id, user=user, org_access=org_access, perm_open_access=perm_open_access
        )
        src = self._resolve_subpath(root, subpath)
        dest_dir = self._resolve_subpath(root, dest_subpath)
        if not src.exists():
            raise NotFoundError(message="复制源不存在", code="FOLDER_NOT_FOUND")
        if src == root:
            raise ValidationException(message="不能复制绑定根目录", errors={"subpath": subpath})
        if not dest_dir.exists() or not dest_dir.is_dir():
            raise NotFoundError(message="目标文件夹不存在", code="FOLDER_NOT_FOUND")
        if src.is_dir() and (dest_dir == src or dest_dir.is_relative_to(src)):
            raise ValidationException(message="不能复制到自身内部", errors={"dest_subpath": dest_subpath})

        dest = self._unique_destination(dest_dir, src.name)
        if src.is_dir():
            # copytree 对符号链接默认保留链接本身，不会跟随读出绑定根外的内容
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)
        logger.info(
            "bound_folder_copy",
            extra={"owner_id": owner_id, "src": subpath, "dest": self._subpath_of(root, dest)},
        )
        return {"subpath": self._subpath_of(root, dest), "name": dest.name}

    def delete_entry(
        self,
        *,
        owner_id: int,
        subpath: str,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, str]:
        """删除 = 移到绑定根下的 ``_已删除/``（带时间戳，可随时在树里找回），不做物理删除。"""
        root, _ = self._checked_root(
            owner_id=owner_id, user=user, org_access=org_access, perm_open_access=perm_open_access
        )
        target = self._resolve_subpath(root, subpath)
        if not target.exists():
            raise NotFoundError(message="目标不存在", code="FOLDER_NOT_FOUND")
        if target == root:
            raise ValidationException(message="不能删除绑定根目录", errors={"subpath": subpath})
        if target.name == self.TRASH_DIR:
            raise ValidationException(message="不能删除回收目录", errors={"subpath": subpath})

        trash = root / self.TRASH_DIR
        trash.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = self._unique_destination(trash, f"{stamp}-{target.name}")
        target.rename(dest)
        logger.info(
            "bound_folder_trash",
            extra={"owner_id": owner_id, "subpath": subpath, "trashed_to": self._subpath_of(root, dest)},
        )
        return {"subpath": self._subpath_of(root, dest), "name": dest.name}

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _checked_root(
        self,
        *,
        owner_id: int,
        user: Any | None,
        org_access: dict[str, Any] | None,
        perm_open_access: bool,
    ) -> tuple[Path, str]:
        self._require_access(owner_id=owner_id, user=user, org_access=org_access, perm_open_access=perm_open_access)
        return self._local_root_with_display(owner_id)

    def _local_root_with_display(self, owner_id: int) -> tuple[Path, str]:
        """子类可覆盖以同时给展示名；默认用根路径。"""
        root = self._local_root(owner_id)
        return root, str(root)

    @staticmethod
    def normalize_subpath(subpath: str) -> str:
        """规范化相对子路径：反斜杠转正斜杠、剔除空段与「.」；非法形态直接抛错。"""
        raw = str(subpath or "").strip().replace("\\", "/")
        if not raw:
            return ""
        if raw.startswith("/") or raw.startswith("~") or BoundFolderBrowseService._DRIVE_RE.match(raw):
            raise ValidationException(message="子路径必须使用相对路径", errors={"subpath": raw})
        parts = [part for part in raw.split("/") if part not in {"", "."}]
        if not parts:
            return ""
        if any(part == ".." for part in parts):
            raise ValidationException(message="子路径路径非法", errors={"subpath": raw})
        return "/".join(parts)

    def _resolve_subpath(self, root: Path, subpath: str) -> Path:
        normalized = self.normalize_subpath(subpath)
        # root 先 resolve：macOS 的 /var 等符号链接路径若不解析，target resolve 后会假性越界
        root = root.resolve()
        target = root if not normalized else (root / normalized).resolve()
        if target != root and not target.is_relative_to(root):
            raise ValidationException(message="子路径不在绑定目录内", errors={"subpath": subpath})
        return target

    @classmethod
    def _clean_entry_name(cls, name: str) -> str:
        """新建 / 重命名条目名：拒分隔符、..、隐藏前缀、Windows 非法与控制字符。"""
        clean = str(name or "").strip()
        if not clean:
            raise ValidationException(message="名称不能为空", errors={"name": name or ""})
        if clean in {".", ".."} or clean.startswith("."):
            raise ValidationException(message="名称不能以点开头", errors={"name": clean})
        if len(clean) > cls._NAME_MAX_LEN:
            raise ValidationException(message=f"名称过长（上限 {cls._NAME_MAX_LEN} 字符）", errors={"name": clean})
        if cls._ILLEGAL_NAME_RE.search(clean):
            raise ValidationException(message='名称不能包含 / \\ : * ? " < > | 等字符', errors={"name": clean})
        return clean

    @staticmethod
    def _unique_destination(directory: Path, filename: str) -> Path:
        dest = directory / filename
        if not dest.exists():
            return dest
        stem, suffix = dest.stem, dest.suffix
        for i in range(1, 1000):
            candidate = directory / f"{stem}_{i}{suffix}"
            if not candidate.exists():
                return candidate
        raise ValidationException(message="同名文件过多", errors={"filename": filename})

    @staticmethod
    def _subpath_of(root: Path, path: Path) -> str:
        """绝对路径 → 绑定根下的相对 posix 路径（根本身/根外均为空串）。"""
        try:
            rel = path.resolve().relative_to(root.resolve())
        except ValueError:
            return ""
        rel_str = rel.as_posix()
        return "" if rel_str == "." else rel_str
