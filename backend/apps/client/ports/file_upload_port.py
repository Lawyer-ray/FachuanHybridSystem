"""文件上传服务端口。"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ninja.files import UploadedFile


class FileUploadPort(Protocol):
    """文件上传服务端口。

    封装对 core 模块 FileUploadService 的依赖。
    """

    def validate_file(self, file: UploadedFile) -> None:
        """验证上传文件。

        Args:
            file: 上传的文件对象

        Raises:
            ValidationException: 文件验证失败
        """
        ...

    def save_file(
        self,
        file: UploadedFile,
        base_dir: str,
        *,
        preserve_name: bool = False,
    ) -> Path:
        """保存上传文件。

        Args:
            file: 上传的文件对象
            base_dir: 基础目录（相对于 MEDIA_ROOT）
            preserve_name: 是否保留原始文件名

        Returns:
            保存后的文件路径（绝对路径）
        """
        ...
