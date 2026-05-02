"""Module for client deletion workflow."""

from __future__ import annotations

import logging
from collections.abc import Callable

from django.db import transaction

from apps.client.models import ClientIdentityDoc, PropertyClueAttachment
from apps.core.services.storage_service import delete_media_file

logger = logging.getLogger("apps.client")


class ClientDeletionWorkflow:
    def __init__(self, *, file_deleter: Callable[[str], None] | None = None) -> None:
        self._file_deleter = file_deleter or delete_media_file

    def collect_client_file_paths(self, *, client_id: int) -> list[str]:
        doc_paths = list(ClientIdentityDoc.objects.filter(client_id=client_id).values_list("file_path", flat=True))
        attachment_paths = list(
            PropertyClueAttachment.objects.filter(property_clue__client_id=client_id).values_list(
                "file_path", flat=True
            )
        )
        return [p for p in (doc_paths + attachment_paths) if p]

    def cleanup_files_on_commit(self, *, file_paths: list[str]) -> None:
        if not file_paths:
            return
        file_paths_copy = list(file_paths)

        def _cleanup() -> None:
            for p in file_paths_copy:
                try:
                    self._file_deleter(p)
                except Exception:
                    logger.exception("删除媒体文件失败", extra={"file_path": p})

        transaction.on_commit(_cleanup)
