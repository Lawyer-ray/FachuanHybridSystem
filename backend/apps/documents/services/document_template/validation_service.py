"""Business logic services."""

from django.utils.translation import gettext_lazy as _
from typing import Any

from apps.core.exceptions import ValidationException
from apps.core.path import Path


class DocumentTemplateValidationService:
    def normalize_file_path(self, file_path: str | None) -> str | None | None:
        if file_path is None:
            return None
        return file_path.strip()

    def validate_file_path(self, file_path: str) -> Any:
        if not file_path:
            return False
        return Path(file_path).is_file()

    def require_single_source(self, file: Any, file_path: str | None) -> str | None:
        if not file and not file_path:
            raise ValidationException(
                message=_("必须提供上传文件或文件路径"),
                code="INVALID_FILE_SOURCE",
                errors={"file": "必须提供上传文件或文件路径"},
            )

        if file and file_path:
            raise ValidationException(
                message=_("不能同时提供上传文件和文件路径"),
                code="INVALID_FILE_SOURCE",
                errors={"file": "不能同时提供上传文件和文件路径"},
            )

        normalized_file_path = self.normalize_file_path(file_path)
        if normalized_file_path and not self.validate_file_path(normalized_file_path):
            raise ValidationException(
                message=f"文件不存在: {normalized_file_path}",
                code="INVALID_FILE_PATH",
                errors={"file_path": f"文件不存在: {normalized_file_path}"},
            )

        return normalized_file_path

    def validate_update_file_source(self, file: Any, file_path: str | None) -> str | None:
        if file is not None and file_path is not None:
            raise ValidationException(
                message=_("不能同时提供上传文件和文件路径"),
                code="INVALID_FILE_SOURCE",
                errors={"file": "不能同时提供上传文件和文件路径"},
            )

        normalized_file_path = self.normalize_file_path(file_path)
        file_changed = file is not None or file_path is not None
        if file_changed and file is None:
            if not normalized_file_path:
                raise ValidationException(
                    message=_("文件路径不能为空"),
                    code="INVALID_FILE_PATH",
                    errors={"file_path": "文件路径不能为空"},
                )
            if not self.validate_file_path(normalized_file_path):
                raise ValidationException(
                    message=f"文件不存在: {normalized_file_path}",
                    code="INVALID_FILE_PATH",
                    errors={"file_path": f"文件不存在: {normalized_file_path}"},
                )

        return normalized_file_path
