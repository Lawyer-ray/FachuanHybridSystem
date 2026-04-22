"""Module for folder binding base."""

from __future__ import annotations

import logging
from typing import ClassVar

from apps.core.utils.path import Path

from .browse_policy import FolderBrowsePolicy
from .filesystem_service import FolderFilesystemService
from .inode_resolver import InodeResolver
from .path_validator import FolderPathValidator

logger = logging.getLogger("apps.core.filesystem")


class BaseFolderBindingService:
    DEFAULT_SUBDIRS: ClassVar[dict[str, str]] = {}

    def __init__(
        self,
        filesystem_service: FolderFilesystemService | None = None,
        path_validator: FolderPathValidator | None = None,
        browse_policy: FolderBrowsePolicy | None = None,
        roots_setting_name: str = "FOLDER_BROWSE_ROOTS",
        fallback_roots_setting_name: str = "CONTRACT_FOLDER_BROWSE_ROOTS",
        inode_resolver: InodeResolver | None = None,
    ) -> None:
        self._filesystem_service = filesystem_service
        self._path_validator = path_validator
        self._browse_policy = browse_policy
        self._roots_setting_name = roots_setting_name
        self._fallback_roots_setting_name = fallback_roots_setting_name
        self._inode_resolver = inode_resolver

    @property
    def path_validator(self) -> FolderPathValidator:
        if self._path_validator is None:
            self._path_validator = FolderPathValidator()
        return self._path_validator

    @property
    def filesystem_service(self) -> FolderFilesystemService:
        if self._filesystem_service is None:
            self._filesystem_service = FolderFilesystemService(validator=self.path_validator)
        return self._filesystem_service

    @property
    def browse_policy(self) -> FolderBrowsePolicy:
        if self._browse_policy is None:
            self._browse_policy = FolderBrowsePolicy(
                validator=self.path_validator,
                roots_setting_name=self._roots_setting_name,
                fallback_roots_setting_name=self._fallback_roots_setting_name,
            )
        return self._browse_policy

    @property
    def inode_resolver(self) -> InodeResolver:
        if self._inode_resolver is None:
            self._inode_resolver = InodeResolver()
        return self._inode_resolver

    def validate_folder_path(self, path: str) -> tuple[bool, str | None]:
        return self.path_validator.validate_folder_path(path)

    def _is_network_path(self, path: str) -> bool:
        return self.path_validator.is_network_path(path)

    def get_browse_roots(self) -> list[Path]:
        return self.browse_policy.get_browse_roots()

    def get_default_browse_path(self) -> Path | None:
        """获取默认浏览路径（用户下载目录）"""
        return self.browse_policy._get_user_downloads_path()

    def resolve_under_allowed_roots(self, path: str) -> Path:
        return self.browse_policy.resolve_under_allowed_roots(path)

    def list_subdirs(self, path: str, include_hidden: bool = False) -> list[dict[str, str]]:
        return self.browse_policy.list_subdirs(path, include_hidden=include_hidden)

    def check_folder_accessible(self, path: str) -> bool:
        try:
            folder = Path(path)
            if hasattr(folder, "exists") and folder.exists():
                if hasattr(folder, "is_dir"):
                    return bool(folder.is_dir())
                if hasattr(folder, "isdir"):
                    return folder.isdir()
            return False
        except (OSError, PermissionError):
            return False

    def check_and_repair_path(self, binding: object) -> tuple[bool, bool]:
        """检查绑定路径可达性，必要时通过 inode 自动修复.

        修复策略：
        1. 先从旧路径的父目录开始 BFS（改名只改最后一段，父目录通常不变）
        2. 如果父目录不可达，逐步向上回退
        3. 最终 fallback 到全局 browse roots

        Args:
            binding: 文件夹绑定对象（需有 folder_path, folder_inode, folder_device 属性）

        Returns:
            (is_accessible, path_auto_repaired) 元组
        """
        folder_path = getattr(binding, "folder_path", "")
        if self.check_folder_accessible(folder_path):
            # 路径可达，顺便补充 inode（如果缺失）
            self._maybe_fill_inode(binding)
            return True, False

        # 路径不可达，尝试 inode 修复
        inode = getattr(binding, "folder_inode", None)
        device = getattr(binding, "folder_device", None)

        if not inode or not device:
            return False, False

        new_path = self._search_by_inode(inode, device, folder_path)

        if new_path is None:
            return False, False

        # 修复路径
        old_path = folder_path
        binding.folder_path = new_path
        has_inode = hasattr(binding, "folder_inode")
        update_fields = ["folder_path", "updated_at"]
        if has_inode:
            # 更新 inode（同分区 mv 后 inode 不变，但跨分区会变）
            new_inode_info = self.inode_resolver.get_inode_info(new_path)
            if new_inode_info:
                binding.folder_inode = new_inode_info[0]
                binding.folder_device = new_inode_info[1]
                update_fields.extend(["folder_inode", "folder_device"])
        binding.save(update_fields=update_fields)
        logger.info(
            "contract_path_auto_repaired",
            extra={
                "binding_id": binding.id,
                "old_path": old_path,
                "new_path": new_path,
                "inode": inode,
                "device": device,
            },
        )
        return True, True

    def _search_by_inode(self, inode: int, device: int, original_path: str) -> str | None:
        """通过 inode 搜索新路径，从旧路径父目录开始逐步回退.

        Args:
            inode: 目标 inode
            device: 目标 device
            original_path: 原始绑定路径

        Returns:
            找到的新路径或 None
        """
        # 策略1：从旧路径父目录开始向上回退 BFS
        parent = Path(original_path).parent
        max_climb = 5
        for _ in range(max_climb):
            if parent.exists() and parent.is_dir():
                # 从父目录开始浅层 BFS（改名只改最后一段，深度2足够）
                result = self.inode_resolver.find_path_by_inode(
                    inode=inode,
                    device=device,
                    search_roots=[parent],
                    max_depth=3,
                )
                if result is not None:
                    return result
            parent = parent.parent
            if parent == parent.parent:
                break  # 到达根目录

        # 策略2：fallback 到全局 browse roots，增大深度
        search_roots = self.get_browse_roots()
        return self.inode_resolver.find_path_by_inode(
            inode=inode,
            device=device,
            search_roots=search_roots,
            max_depth=6,
        )

    def _maybe_fill_inode(self, binding: object) -> None:
        """路径可达但 inode 缺失时，补充 inode+device."""
        # 只有模型有 inode 字段时才处理
        if not hasattr(binding, "folder_inode"):
            return

        inode = getattr(binding, "folder_inode", None)
        if inode is not None:
            return  # 已有 inode，无需补充

        folder_path = getattr(binding, "folder_path", "")
        info = self.inode_resolver.get_inode_info(folder_path)
        if info is None:
            return

        binding.folder_inode = info[0]
        binding.folder_device = info[1]
        binding.save(update_fields=["folder_inode", "folder_device", "updated_at"])
        logger.info(
            "inode_backfilled",
            extra={
                "binding_id": binding.id,
                "folder_path": folder_path,
                "inode": info[0],
                "device": info[1],
            },
        )

    def ensure_subdirectories(self, base_path: str) -> bool:
        ok = self.filesystem_service.ensure_subdirectories(base_path, self.DEFAULT_SUBDIRS.values())
        if not ok:
            logger.error("创建子目录失败", extra={"base_path": base_path})
        return ok

    def format_path_for_display(self, path: str, max_length: int = 50) -> str:
        if not path:
            return ""
        if len(path) <= max_length:
            return path
        start_len = max_length // 3
        end_len = max_length - start_len - 3
        return f"{path[:start_len]}...{path[-end_len:]}"

    def compute_parent_path(self, resolved: Path) -> str | None:
        """计算已解析路径的父路径(如果父路径在允许的根目录范围内).

        Args:
            resolved: 已解析的路径

        Returns:
            父路径字符串,如果父路径不在允许范围内则返回 None
        """
        parent: Path = resolved.parent
        for root in self.get_browse_roots():
            try:
                parent.relative_to(root)
                return str(parent)
            except ValueError:
                continue
        return None

    def is_browsable_path(self, path: str) -> tuple[bool, str | None]:
        """检查路径是否可浏览.

        Args:
            path: 要检查的路径

        Returns:
            (is_browsable, message) 元组.如果不可浏览,message 包含原因.
        """
        if self._is_network_path(path):
            return False, "网络路径不支持浏览,但可以直接绑定"
        return True, None
