"""client app 信号处理器 - 删除记录时自动清理物理文件"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db.models.signals import post_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _delete_file_by_path(file_path_str: str | None) -> None:
    """通过路径字符串删除物理文件 (CharField 存储的场景)"""
    if not file_path_str:
        return
    file_path = Path(file_path_str)
    if not file_path.is_absolute():
        file_path = Path(settings.MEDIA_ROOT) / file_path_str
    if file_path.exists():
        try:
            file_path.unlink()
            logger.info("已清理物理文件", extra={"file_path": str(file_path)})
        except OSError as exc:
            logger.error("清理物理文件失败", extra={"file_path": str(file_path), "error": str(exc)})


def _delete_field_file(field_file: Any) -> None:
    """删除 FileField 对应的物理文件"""
    if field_file:
        try:
            field_file.delete(save=False)
            logger.info("已清理 FileField 物理文件", extra={"file_path": str(field_file)})
        except Exception:
            logger.exception("清理 FileField 物理文件失败")


@receiver(post_delete, dispatch_uid="cleanup_client_identity_doc_files")
def cleanup_client_identity_doc_files(sender: type, **kwargs: Any) -> None:
    """ClientIdentityDoc 使用 CharField(file_path) 存储证件扫描件，需手动清理"""
    from .models import ClientIdentityDoc  # 防止循环导入

    if sender is ClientIdentityDoc:
        instance = kwargs["instance"]
        _delete_file_by_path(instance.file_path)


@receiver(post_delete, dispatch_uid="cleanup_property_clue_attachment_files")
def cleanup_property_clue_attachment_files(sender: type, **kwargs: Any) -> None:
    """PropertyClueAttachment 使用 CharField(file_path) 存储附件，需手动清理"""
    from .models import PropertyClueAttachment  # 防止循环导入

    if sender is PropertyClueAttachment:
        instance = kwargs["instance"]
        _delete_file_by_path(instance.file_path)
