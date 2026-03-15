"""文件上传适配器实现。"""

from __future__ import annotations

from pathlib import Path

from ninja.files import UploadedFile

from apps.core.services.file_upload_service import FileUploadService


class FileUploadAdapter:
    """文件上传服务适配器。

    包装 FileUploadService，实现 FileUploadPort 接口。
    """

    def __init__(self, service: FileUploadService | None = None) -> None:
        """初始化适配器。

        Args:
            service: 可选的文件上传服务实例
        """
        self._service = service or FileUploadService()

    def validate_file(self, file: UploadedFile) -> None:
        """验证上传文件。"""
        self._service.validate_file(file)

    def save_file(
        self,
        file: UploadedFile,
        base_dir: str,
        *,
        preserve_name: bool = False,
    ) -> Path:
        """保存上传文件。"""
        return self._service.save_file(file, base_dir, preserve_name=preserve_name)
