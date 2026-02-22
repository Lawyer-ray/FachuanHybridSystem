"""Module for client formset file workflow."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.client.models import Client
from apps.client.models import ClientIdentityDoc
from apps.core.exceptions import ValidationException

logger = logging.getLogger("apps.client")


class ClientFormsetFileWorkflow:
    def __init__(
        self,
        *,
        handle_file_storage: Callable[[dict[str, Any], str, str], str | None],
        update_identity_doc: Callable[[int, str, str], None],
        create_identity_doc: Callable[[int, str, str], None],
    ) -> None:
        self.handle_file_storage = handle_file_storage
        self.update_identity_doc = update_identity_doc
        self.create_identity_doc = create_identity_doc

    def run(self, *, client_id: int, formset_data: list[dict[str, Any]], admin_user: str) -> None:
        client = Client.objects.filter(id=client_id).first()
        if not client:
            raise ValidationException(
                message=_("客户不存在"),
                code="CLIENT_NOT_FOUND",
                errors={"client_id": f"ID 为 {client_id} 的客户不存在"},
            )

        processed_files = []
        for form_data in formset_data:
            if not self._should_process_form(form_data):
                continue

            file_info = self._process_single_form(client=client, form_data=form_data, admin_user=admin_user)
            if file_info:
                processed_files.append(file_info)

        logger.info(
            "表单集文件处理完成",
            extra={
                "client_id": client_id,
                "processed_count": len(processed_files),
                "admin_user": admin_user,
                "action": "process_formset_files",
            },
        )

    def _should_process_form(self, form_data: dict[str, Any]) -> bool:
        if form_data.get("DELETE"):
            return False
        return bool(form_data.get("file_path") or form_data.get("uploaded_file"))

    def _process_single_form(
        self,
        *,
        client: Client,
        form_data: dict[str, Any],
        admin_user: str,
    ) -> dict[str, Any] | None:
        doc_type = form_data.get("doc_type")
        if not doc_type:
            logger.warning(
                "表单项缺少证件类型",
                extra={"client_id": client.id, "admin_user": admin_user, "action": "process_single_form"},
            )
            return None

        doc_type_display = dict(ClientIdentityDoc.DOC_TYPE_CHOICES).get(doc_type, doc_type)

        file_path = self.handle_file_storage(form_data, client.name or "", doc_type_display)
        if not file_path:
            return None

        doc_id = form_data.get("id")
        if doc_id:
            self.update_identity_doc(int(doc_id), file_path, admin_user)
        else:
            self.create_identity_doc(client.id, doc_type, file_path)

        return {"doc_type": doc_type, "file_path": file_path, "doc_id": doc_id}
