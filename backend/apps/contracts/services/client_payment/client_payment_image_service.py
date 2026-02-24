"""客户回款凭证图片服务层"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils.translation import gettext as _

from apps.client.services import storage
from apps.core.exceptions import ValidationException

logger = logging.getLogger("apps.contracts")


class ClientPaymentImageService:
    """
    客户回款凭证图片服务

    职责:
    - 图片文件的上传、存储、删除
    - 文件格式和大小验证
    """

    ALLOWED_EXTENSIONS = [".jpg", ".jpeg", ".png"]
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

    def __init__(self) -> None:
        """构造函数"""

    def save_image(
        self,
        uploaded_file: Any,
        record_id: int,
    ) -> str:
        """
        保存图片文件

        Args:
            uploaded_file: 上传的文件对象
            record_id: 回款记录 ID

        Returns:
            图片相对路径

        Raises:
            ValidationException: 文件格式或大小不符合要求
        """
        try:
            rel_path, _ = storage.save_uploaded_file(
                uploaded_file=uploaded_file,
                rel_dir=f"contracts/client_payments/{record_id}",
                allowed_extensions=self.ALLOWED_EXTENSIONS,
                max_size_bytes=self.MAX_FILE_SIZE,
            )

            logger.info("上传回款凭证: record_id=%s, path=%s", record_id, rel_path)

            return rel_path

        except ValidationException:
            raise
        except Exception as e:
            logger.error("图片上传失败: %s", str(e), exc_info=True)
            raise ValidationException(_("图片上传失败")) from e

    def delete_image(self, image_path: str) -> None:
        """
        删除图片文件

        Args:
            image_path: 图片相对路径
        """
        if not image_path:
            return

        try:
            success = storage.delete_media_file(image_path)
            if success:
                logger.info("删除回款凭证: path=%s", image_path)
            else:
                logger.warning("删除回款凭证失败（文件可能不存在）: path=%s", image_path)
        except Exception as e:
            logger.error("删除回款凭证异常: path=%s, error=%s", image_path, str(e), exc_info=True)

    def get_image_url(self, image_path: str) -> str:
        """
        获取图片访问 URL

        Args:
            image_path: 图片相对路径

        Returns:
            图片访问 URL
        """
        if not image_path:
            return ""

        media_url = getattr(settings, "MEDIA_URL", "/media/")
        return f"{media_url}{image_path}"
