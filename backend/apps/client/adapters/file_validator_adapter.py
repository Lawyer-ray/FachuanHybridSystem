"""文件验证器适配器实现。"""

from __future__ import annotations

from typing import Any

from apps.core.exceptions import ValidationException


class FileValidatorAdapter:
    """文件验证器适配器。

    包装 Validators.validate_uploaded_file，实现 FileValidatorPort 接口。
    """

    # 可执行文件 magic bytes（PE/ELF/Mach-O）
    EXECUTABLE_MAGIC: tuple[bytes, ...] = (
        b"MZ",  # Windows PE
        b"\x7fELF",  # Linux ELF
        b"\xfe\xed\xfa\xce",  # Mach-O 32-bit
        b"\xfe\xed\xfa\xcf",  # Mach-O 64-bit
        b"\xce\xfa\xed\xfe",  # Mach-O 32-bit LE
        b"\xcf\xfa\xed\xfe",  # Mach-O 64-bit LE
    )

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
        if not uploaded_file:
            raise ValidationException(
                "请选择要上传的文件",
                errors={field_name: "文件不能为空"},
            )

        if allowed_extensions:
            filename: str = getattr(uploaded_file, "name", "") or ""
            ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
            if ext not in allowed_extensions:
                raise ValidationException(
                    f"不支持的文件格式: {ext}",
                    errors={field_name: f"允许的格式: {', '.join(allowed_extensions)}"},
                )

        size: int = getattr(uploaded_file, "size", 0) or 0
        if max_size_bytes is not None and size > max_size_bytes:
            raise ValidationException(
                "文件大小超限",
                errors={field_name: f"文件大小不能超过 {max_size_bytes} 字节"},
            )

        # 检测可执行文件 magic bytes
        try:
            header: bytes = uploaded_file.read(8)
            uploaded_file.seek(0)
            if any(header.startswith(magic) for magic in self.EXECUTABLE_MAGIC):
                raise ValidationException(
                    "不允许上传可执行文件",
                    errors={field_name: "文件内容被识别为可执行文件"},
                )
        except (AttributeError, OSError):
            pass

        return uploaded_file
