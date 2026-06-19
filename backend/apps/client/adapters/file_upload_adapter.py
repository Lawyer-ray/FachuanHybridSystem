"""文件上传适配器实现。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ninja.files import UploadedFile

from apps.core.services.storage_service import save_uploaded_file, validate_file


class FileUploadAdapter:
    """文件上传服务适配器。

    委托给 storage_service 中的 validate_file / save_uploaded_file，
    实现 FileUploadPort 接口。
    """

    def __init__(self, **_kwargs: Any) -> None:
        """初始化适配器。"""

    def validate_file(self, file: UploadedFile) -> None:
        """验证上传文件。"""
        validate_file(file)

    def save_file(
        self,
        file: UploadedFile,
        base_dir: str,
        *,
        preserve_name: bool = False,
    ) -> Path:
        """保存上传文件。"""
        rel_path, _ = save_uploaded_file(
            file,
            rel_dir=base_dir,
            use_uuid_name=not preserve_name,
        )
        from django.conf import settings

        return Path(settings.MEDIA_ROOT) / rel_path
