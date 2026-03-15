"""文件验证器端口。"""

from __future__ import annotations

from typing import Any, Protocol


class FileValidatorPort(Protocol):
    """文件验证服务端口。

    封装对文件验证逻辑的依赖。
    """

    def validate_uploaded_file(
        self,
        uploaded_file: Any,
        allowed_extensions: list[str] | None = None,
        max_size_bytes: int | None = None,
        field_name: str = "file",
    ) -> Any:
        """验证上传文件。

        Args:
            uploaded_file: 上传的文件对象
            allowed_extensions: 允许的扩展名列表，如 [".pdf", ".jpg"]
            max_size_bytes: 最大文件大小（字节），None 表示不限制
            field_name: 字段名（用于错误信息）

        Returns:
            验证通过的文件对象

        Raises:
            ValidationException: 验证失败
        """
        ...
