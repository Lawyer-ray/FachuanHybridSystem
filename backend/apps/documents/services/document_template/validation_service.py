"""Business logic services."""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ValidationException
from apps.documents.storage import resolve_docx_template_path


class DocumentTemplateValidationService:
    def normalize_file_path(self, file_path: str | None) -> str | None:
        if file_path is None:
            return None
        return file_path.strip()

    def validate_file_path(self, file_path: str) -> bool:
        if not file_path:
            return False
        try:
            return bool(resolve_docx_template_path(file_path).is_file())
        except ValueError:
            return False

    def _require_valid_file_path(self, file_path: str) -> None:
        try:
            resolved = resolve_docx_template_path(file_path)
        except ValueError as exc:
            raise ValidationException(
                message=_("文件路径无效，必须位于当前模板根目录内"),
                code="INVALID_FILE_PATH",
                errors={"file_path": "文件路径无效，必须位于当前模板根目录内"},
            ) from exc

        if not resolved.is_file():
            raise ValidationException(
                message=_("文件不存在: %(p)s") % {"p": file_path},
                code="INVALID_FILE_PATH",
                errors={"file_path": f"文件不存在: {file_path}"},
            )

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
        if normalized_file_path:
            self._require_valid_file_path(normalized_file_path)

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
            self._require_valid_file_path(normalized_file_path)

        return normalized_file_path
