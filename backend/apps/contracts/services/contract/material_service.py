"""定稿材料服务层。"""

from __future__ import annotations

import logging
from pathlib import Path  # noqa: F401
from typing import Any

from apps.client.services import storage

logger = logging.getLogger(__name__)


class MaterialService:
    def save_material_file(self, uploaded_file: Any, contract_id: int) -> tuple[str, str]:
        """
        保存定稿材料文件。
        Returns: (rel_path, original_filename)
        """
        return storage.save_uploaded_file(
            uploaded_file=uploaded_file,
            rel_dir=f"contracts/finalized/{contract_id}",
            allowed_extensions=[".pdf"],
            max_size_bytes=20 * 1024 * 1024,
        )

    def delete_material_file(self, file_path: str) -> bool:
        """
        删除定稿材料文件。失败时记录日志但不抛异常。
        """
        try:
            return storage.delete_media_file(file_path)
        except Exception:
            logger.error("删除定稿材料文件失败: %s", file_path, exc_info=True)
            return False
