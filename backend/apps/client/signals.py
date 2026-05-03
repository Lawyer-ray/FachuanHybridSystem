"""client app 信号处理器 - 删除记录时自动清理物理文件"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.core.services.storage_service import _get_media_root, delete_media_file

logger = logging.getLogger(__name__)


@receiver(post_delete, dispatch_uid="cleanup_client_identity_doc_files")
def cleanup_client_identity_doc_files(sender: type, **kwargs: Any) -> None:
    """ClientIdentityDoc 使用 CharField(file_path) 存储证件扫描件，需手动清理。

    注意：Client 删除时由 ClientDeletionWorkflow 统一处理文件清理（on_commit），
    此信号仅处理单独删除证件文档的场景（如 Admin inline 操作）。
    """
    from .models import ClientIdentityDoc

    if sender is ClientIdentityDoc:
        instance = kwargs["instance"]
        file_path = instance.file_path
        if file_path:
            transaction.on_commit(lambda fp=file_path: delete_media_file(fp))  # type: ignore[misc]


@receiver(post_delete, dispatch_uid="cleanup_property_clue_attachment_files")
def cleanup_property_clue_attachment_files(sender: type, **kwargs: Any) -> None:
    """PropertyClueAttachment 使用 CharField(file_path) 存储附件，需手动清理。

    注意：Client 删除时由 ClientDeletionWorkflow 统一处理文件清理（on_commit），
    此信号仅处理单独删除附件的场景。
    """
    from .models import PropertyClueAttachment

    if sender is PropertyClueAttachment:
        instance = kwargs["instance"]
        file_path = instance.file_path
        if file_path:
            transaction.on_commit(lambda fp=file_path: delete_media_file(fp))  # type: ignore[misc]
