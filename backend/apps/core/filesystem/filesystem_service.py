"""Business logic services."""

import io
import logging
import shutil
import zipfile
from collections.abc import Iterable

from apps.core.exceptions import ValidationException
from apps.core.utils.path import Path

from .path_validator import FolderPathValidator

logger = logging.getLogger("apps")

# ── 解压炸弹防护 ────────────────────────────────────────────────────────────
# ZIP 头声明的解压总量 / 成员数上限：超限直接拒绝解压（只读 central directory
# 元数据，不消费压缩数据本身）
ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024  # 2GB
ZIP_MAX_MEMBER_COUNT = 5000


def ensure_zip_within_limits(
    zip_file: zipfile.ZipFile,
    *,
    max_total_uncompressed_bytes: int = ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES,
    max_member_count: int = ZIP_MAX_MEMBER_COUNT,
) -> None:
    """解压前按 ZIP 头声明的 file_size / 成员数做解压炸弹防护。

    Raises:
        ValidationException: 声明总量或成员数超过上限，调用方应拒绝解压。
    """
    infos = zip_file.infolist()
    if len(infos) > max_member_count:
        raise ValidationException(
            message=f"ZIP 条目数超限（{len(infos)} > {max_member_count}），拒绝解压",
            code="ZIP_MEMBER_COUNT_EXCEEDED",
        )
    total_uncompressed = sum(info.file_size for info in infos)
    if total_uncompressed > max_total_uncompressed_bytes:
        raise ValidationException(
            message=f"ZIP 声明解压总量超限（{total_uncompressed} > {max_total_uncompressed_bytes} 字节），拒绝解压",
            code="ZIP_TOTAL_SIZE_EXCEEDED",
        )


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
            logger.warning("创建目录结构失败（已忽略）: base_path=%s", base_path, exc_info=True)
            return False

    def save_bytes(self, base_path: str, relative_dir_parts: list[str], file_name: str, content: bytes) -> str:
        base_dir = Path(base_path)
        safe_file_name = self.validator.sanitize_file_name(file_name)

        file_dir = base_dir
        for part in relative_dir_parts:
            file_dir = file_dir / part

        file_path = self._get_unique_path(file_dir, safe_file_name)
        self.validator.ensure_within_base(base_dir, file_path)

        parent_dir = file_path.parent if hasattr(file_path, "parent") else Path(str(file_path)).dirname()
        self.validator.mkdirs(parent_dir)

        with open(str(file_path), "wb") as f:
            f.write(content)

        return str(file_path)

    def _get_unique_path(self, parent_dir: Path, file_name: str) -> Path:
        """如果文件已存在则返回带序号后缀的唯一路径，如 file.docx → file_1.docx"""
        stem = Path(file_name).stem
        suffix = Path(file_name).suffix
        candidate = parent_dir / file_name
        if not candidate.exists():
            return candidate
        counter = 1
        while True:
            new_name = f"{stem}_{counter}{suffix}"
            candidate = parent_dir / new_name
            if not candidate.exists():
                return candidate
            counter += 1

    def extract_zip_bytes(self, base_path: str, zip_content: bytes) -> str:
        base_dir = Path(base_path)
        self.validator.mkdirs(base_dir)

        try:
            with zipfile.ZipFile(io.BytesIO(zip_content), "r") as zip_file:
                # 解压炸弹防护：按声明总量 / 成员数拒绝超限 ZIP
                ensure_zip_within_limits(zip_file)
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
                    # 文件使用唯一路径（防重名）
                    unique_target_path = self._get_unique_path(parent_dir, target_path.name)
                    with zip_file.open(info, "r") as src, open(str(unique_target_path), "wb") as dst:
                        shutil.copyfileobj(src, dst)

        except (zipfile.BadZipFile, OSError, PermissionError) as e:
            raise ValidationException(
                message="ZIP解压失败", code="ZIP_EXTRACT_FAILED", errors={"zip_operation": str(e)}
            ) from e

        return str(base_dir)
