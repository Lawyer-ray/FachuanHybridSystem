"""Business logic services."""

import io
import shutil
import zipfile
from collections.abc import Iterable

from apps.core.exceptions import ValidationException
from apps.core.path import Path

from .path_validator import FolderPathValidator


class FolderFilesystemService:
    def __init__(self, validator: FolderPathValidator | None = None) -> None:
        self._validator = validator

    @property
    def validator(self) -> FolderPathValidator:
        if self._validator is None:
            self._validator = FolderPathValidator()
        return self._validator

    def ensure_subdirectories(self, base_path: str, subdir_names: Iterable[str]) -> bool:
        try:
            base_dir = Path(base_path)
            self.validator.mkdirs(base_dir)
            for subdir_name in subdir_names:
                subdir_path = base_dir / subdir_name
                self.validator.mkdirs(subdir_path)
            return True
        except (OSError, PermissionError):
            return False

    def save_bytes(self, base_path: str, relative_dir_parts: list[str], file_name: str, content: bytes) -> str:
        base_dir = Path(base_path)
        safe_file_name = self.validator.sanitize_file_name(file_name)

        file_dir = base_dir
        for part in relative_dir_parts:
            file_dir = file_dir / part

        file_path = file_dir / safe_file_name
        self.validator.ensure_within_base(base_dir, file_path)

        parent_dir = file_path.parent if hasattr(file_path, "parent") else Path(str(file_path)).dirname()
        self.validator.mkdirs(parent_dir)

        with open(str(file_path), "wb") as f:
            f.write(content)

        return str(file_path)

    def extract_zip_bytes(self, base_path: str, zip_content: bytes) -> str:
        base_dir = Path(base_path)
        self.validator.mkdirs(base_dir)

        try:
            with zipfile.ZipFile(io.BytesIO(zip_content), "r") as zip_file:
                for info in zip_file.infolist():
                    member_name = info.filename
                    relative_path = self.validator.sanitize_zip_member_path(member_name)
                    if not relative_path:
                        continue

                    target_path = base_dir
                    for part in relative_path:
                        target_path = target_path / part
                    self.validator.ensure_within_base(base_dir, target_path)

                    if getattr(info, "is_dir", None) and info.is_dir():
                        self.validator.mkdirs(target_path)
                        continue
                    if str(member_name or "").endswith("/"):
                        self.validator.mkdirs(target_path)
                        continue

                    parent_dir = (
                        target_path.parent if hasattr(target_path, "parent") else Path(str(target_path)).dirname()
                    )
                    self.validator.mkdirs(parent_dir)
                    with zip_file.open(info, "r") as src, open(str(target_path), "wb") as dst:
                        shutil.copyfileobj(src, dst)

        except (zipfile.BadZipFile, OSError, PermissionError) as e:
            raise ValidationException(
                message="ZIP解压失败", code="ZIP_EXTRACT_FAILED", errors={"zip_operation": str(e)}
            ) from e

        return str(base_dir)
