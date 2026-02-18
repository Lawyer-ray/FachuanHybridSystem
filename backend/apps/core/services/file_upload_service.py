"""
文件上传服务

提供安全的文件上传处理，包含类型验证、大小限制、文件名清理。
"""

from __future__ import annotations

import logging
import mimetypes
import uuid
from pathlib import Path

from django.conf import settings
from ninja.files import UploadedFile

from apps.core.exceptions import ValidationException

logger = logging.getLogger(__name__)

# 文件类型白名单
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx"})
ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)

# 文件大小限制（字节）
MAX_FILE_SIZE: int = 20 * 1024 * 1024  # 20MB


class FileUploadService:
    """文件上传服务"""

    def validate_file(self, file: UploadedFile) -> None:
        """
        验证上传文件

        Args:
            file: 上传的文件对象

        Raises:
            ValidationException: 文件验证失败
        """
        # 验证文件大小
        file_size: int = file.size or 0
        if file_size > MAX_FILE_SIZE:
            raise ValidationException(
                f"文件大小超过限制（最大 {MAX_FILE_SIZE // (1024 * 1024)}MB）",
                code="FILE_TOO_LARGE",
            )

        # 验证文件扩展名
        file_name: str = file.name or ""
        file_ext = Path(file_name).suffix.lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            raise ValidationException(
                f"不支持的文件类型：{file_ext}",
                code="INVALID_FILE_TYPE",
                errors={"allowed_types": sorted(ALLOWED_EXTENSIONS)},
            )

        # 验证 MIME 类型
        content_type: str = file.content_type or ""
        if content_type not in ALLOWED_MIME_TYPES:
            raise ValidationException(
                f"不支持的 MIME 类型：{content_type}",
                code="INVALID_MIME_TYPE",
            )

        # 验证 MIME 类型与扩展名一致
        expected_mime, _ = mimetypes.guess_type(f"file{file_ext}")
        if expected_mime and content_type != expected_mime:
            raise ValidationException(
                "文件类型与扩展名不匹配",
                code="MIME_EXTENSION_MISMATCH",
            )

    def save_file(
        self,
        file: UploadedFile,
        base_dir: str,
        *,
        preserve_name: bool = False,
    ) -> Path:
        """
        保存上传文件

        Args:
            file: 上传的文件对象
            base_dir: 基础目录（相对于 MEDIA_ROOT）
            preserve_name: 是否保留原始文件名

        Returns:
            保存后的文件路径（绝对路径）

        Raises:
            ValidationException: 文件验证失败
        """
        # 验证文件
        self.validate_file(file)

        # 构建保存路径
        media_root = Path(settings.MEDIA_ROOT)
        target_dir = media_root / base_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        file_name_raw: str = file.name or "upload"
        file_ext = Path(file_name_raw).suffix.lower()

        # 生成安全的文件名
        if preserve_name:
            # 清理文件名（移除路径遍历字符）
            safe_name = Path(file_name_raw).name.replace("..", "").replace("/", "").replace("\\", "")
            file_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
        else:
            # 使用 UUID + 原始扩展名
            file_name = f"{uuid.uuid4().hex}{file_ext}"

        target_path = target_dir / file_name

        # 保存文件
        with target_path.open("wb") as f:
            for chunk in file.chunks():
                f.write(chunk)

        logger.info(
            "文件上传成功",
            extra={
                "file_name": file_name_raw,
                "saved_path": str(target_path),
                "file_size": file.size,
            },
        )

        return target_path
