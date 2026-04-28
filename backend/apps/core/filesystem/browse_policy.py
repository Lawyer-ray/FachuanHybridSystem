"""Module for browse policy."""

import sys

from django.conf import settings

from apps.core.exceptions import ValidationException
from apps.core.utils.path import Path

from .path_validator import FolderPathValidator


class FolderBrowsePolicy:
    def __init__(
        self,
        *,
        validator: FolderPathValidator | None = None,
        roots_setting_name: str = "FOLDER_BROWSE_ROOTS",
        fallback_roots_setting_name: str | None = None,
    ) -> None:
        self.validator = validator or FolderPathValidator()
        self.roots_setting_name = roots_setting_name
        self.fallback_roots_setting_name = fallback_roots_setting_name

    def _get_user_downloads_path(self) -> Path | None:
        """获取用户下载目录路径（跨平台）"""
        try:
            if sys.platform == "darwin" or sys.platform.startswith("win"):  # macOS
                downloads = Path("~/Downloads").expanduser()
            else:  # Linux
                downloads = Path("~/Downloads").expanduser()

            if downloads.isdir():
                return downloads  # type: ignore[no-any-return]
        except (OSError, PermissionError):
            pass
        return None

    def get_browse_roots(self) -> list[Path]:
        roots = getattr(settings, self.roots_setting_name, None)
        if roots is None and self.fallback_roots_setting_name:
            roots = getattr(settings, self.fallback_roots_setting_name, None)
        roots = roots or []

        resolved: list[Path] = []

        # 优先添加用户下载目录
        downloads = self._get_user_downloads_path()
        if downloads:
            resolved.append(downloads)

        # 添加配置的根目录
        for root in roots:
            try:
                p = Path(str(root)).expanduser().resolve()
                if p.isdir() and p not in resolved:  # 避免重复
                    resolved.append(p)
            except (OSError, PermissionError):
                continue
        return resolved

    def resolve_under_allowed_roots(self, path: str) -> Path:
        if self.validator.is_network_path(path):
            raise ValidationException("网络路径不支持浏览,但可以直接绑定", code="BROWSE_NOT_SUPPORTED")

        roots = self.get_browse_roots()
        if not roots:
            raise ValidationException("未配置允许浏览的根目录", code="BROWSE_NOT_CONFIGURED")

        try:
            target = Path(str(Path(str(path)).expanduser().resolve()))
        except (OSError, PermissionError):
            raise ValidationException("路径不可访问", code="BROWSE_NOT_ACCESSIBLE") from None

        if not target.isdir():
            raise ValidationException("目标不是文件夹", code="BROWSE_NOT_A_DIRECTORY")

        for root in roots:
            try:
                target.relative_to(root)
                return target
            except ValueError:
                continue

        raise ValidationException("目标路径不在允许范围内", code="BROWSE_FORBIDDEN")

    def list_subdirs(self, path: str, include_hidden: bool = False) -> list[dict[str, str]]:
        target = self.resolve_under_allowed_roots(path)
        results: list[dict[str, str]] = []
        try:
            for child in target.iterdir():
                try:
                    if child.isdir():
                        if not include_hidden and str(child.name).startswith("."):
                            continue
                        results.append({"name": child.name, "path": str(child)})
                except (OSError, PermissionError):
                    continue
        except (OSError, PermissionError):
            raise ValidationException("无权限读取目录", code="BROWSE_PERMISSION_DENIED") from None

        results.sort(key=lambda x: x["name"].lower())
        return results
