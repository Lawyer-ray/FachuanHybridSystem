"""归档材料服务层。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from apps.core.services import storage_service as storage

logger = logging.getLogger(__name__)


class MaterialService:
    def save_material_file(self, uploaded_file: Any, contract_id: int) -> tuple[str, str]:
        """
        保存归档材料文件。
        Returns: (rel_path, original_filename)
        """
        result: tuple[str, str] = storage.save_uploaded_file(
            uploaded_file=uploaded_file,
            rel_dir=f"contracts/finalized/{contract_id}",
            allowed_extensions=[".pdf"],
            max_size_bytes=100 * 1024 * 1024,
        )
        return result

    def delete_material_file(self, file_path: str) -> bool:
        """
        删除归档材料文件。失败时记录日志但不抛异常。
        """
        try:
            result: bool = storage.delete_media_file(file_path)
            return result
        except Exception:
            logger.error("删除归档材料文件失败: %s", file_path, exc_info=True)
            return False
