"""External service client."""

from __future__ import annotations

import logging
from typing import Any

from apps.client.models import ClientIdentityDoc

logger = logging.getLogger("apps.client")


class ClientAdminFileMixin:
    def _handle_file_storage(
        self, form_data: dict[str, Any], client_name: str = "", doc_type_display: str = ""
    ) -> str | None:
        if form_data.get("file_path"):
            return str(form_data["file_path"])
        uploaded_file = form_data.get("uploaded_file")
        if uploaded_file:
            return self._save_uploaded_file(uploaded_file, client_name, doc_type_display)
        return None

    def _save_uploaded_file(self, uploaded_file: Any, client_name: str = "", doc_type: str = "") -> str:
        from .storage import save_uploaded_file

        if not hasattr(uploaded_file, "name"):
            return ""
        preferred = ""
        if client_name and doc_type:
            preferred = f"{self._sanitize_filename(client_name)}_{self._sanitize_filename(doc_type)}"
        rel_path, _ = save_uploaded_file(uploaded_file, rel_dir="client_docs", preferred_filename=preferred or None)
        return rel_path

    def _sanitize_filename(self, filename: str) -> str:
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, "_")
        filename = filename.strip(" .")
        if len(filename) > 50:
            filename = filename[:50]
        return filename or "未命名"

    def _update_identity_doc(self, doc_id: int, file_path: str, admin_user: str) -> None:
        try:
            doc = ClientIdentityDoc.objects.get(id=doc_id)
            old_path = doc.file_path
            doc.file_path = file_path
            doc.save()
            logger.info(
                "证件文档文件路径更新成功",
                extra={
                    "doc_id": doc_id,
                    "old_path": old_path,
                    "new_path": file_path,
                    "admin_user": admin_user,
                    "action": "update_identity_doc",
                },
            )
        except ClientIdentityDoc.DoesNotExist:
            logger.warning(
                "尝试更新不存在的证件文档",
                extra={"doc_id": doc_id, "admin_user": admin_user, "action": "update_identity_doc"},
            )

    def save_and_rename_file(
        self, client_id: int, client_name: str, doc_id: int, doc_type: str, uploaded_file: Any
    ) -> str:
        doc_type_display = dict[str, Any](ClientIdentityDoc.DOC_TYPE_CHOICES).get(doc_type, doc_type)
        file_path = self._save_uploaded_file(uploaded_file, client_name, doc_type_display)
        if file_path:
            ClientIdentityDoc.objects.filter(id=doc_id).update(file_path=file_path)
            doc = ClientIdentityDoc.objects.select_related("client").filter(id=doc_id).first()
            if doc:
                from .client_identity_doc_service import ClientIdentityDocService

                ClientIdentityDocService().rename_uploaded_file(doc)  # type: ignore[no-untyped-call]
            logger.info(
                "证件文件保存成功",
                extra={
                    "client_id": client_id,
                    "doc_id": doc_id,
                    "file_path": file_path,
                    "action": "save_and_rename_file",
                },
            )
        return file_path
