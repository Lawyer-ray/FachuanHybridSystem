"""Module for folder binding base."""

from __future__ import annotations

import logging
from typing import ClassVar

from apps.core.path import Path

from .browse_policy import FolderBrowsePolicy
from .filesystem_service import FolderFilesystemService
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
    ) -> None:
        self._filesystem_service = filesystem_service
        self._path_validator = path_validator
        self._browse_policy = browse_policy
        self._roots_setting_name = roots_setting_name
        self._fallback_roots_setting_name = fallback_roots_setting_name

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
