"""Admin 文件处理 Mixin。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from apps.client.models import ClientIdentityDoc
from apps.core.services.storage_service import sanitize_upload_filename, save_uploaded_file

_DOC_TYPE_DISPLAY: dict[str, str] = dict(ClientIdentityDoc.DOC_TYPE_CHOICES)

if TYPE_CHECKING:
    from apps.client.services.client_identity_doc_service import ClientIdentityDocService

logger = logging.getLogger("apps.client")


class ClientAdminFileMixin:
    identity_doc_service: ClientIdentityDocService

    def _handle_file_storage(
        self, form_data: dict[str, Any], client_name: str = "", doc_type_display: str = ""
    ) -> str | None:
        if form_data.get("file_path"):
            return form_data["file_path"]  # type: ignore[no-any-return]
        uploaded_file = form_data.get("uploaded_file")
        if uploaded_file:
            return self._save_uploaded_file(uploaded_file, client_name, doc_type_display)
        return None

    def _save_uploaded_file(self, uploaded_file: Any, client_name: str = "", doc_type: str = "") -> str:
        if not hasattr(uploaded_file, "name"):
            return ""
        preferred: str | None = None
        if client_name and doc_type:
            preferred = f"{sanitize_upload_filename(client_name)}_{sanitize_upload_filename(doc_type)}"
        rel_path, _ = save_uploaded_file(uploaded_file, rel_dir="client_docs", preferred_filename=preferred)
        return rel_path

    def _update_identity_doc(self, doc_id: int, file_path: str, admin_user: str) -> None:
        doc = self.identity_doc_service.get_identity_doc(doc_id)
        old_path = doc.file_path
        doc.file_path = file_path
        doc.save(update_fields=["file_path"])
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

    def save_and_rename_file(
        self, client_id: int, client_name: str, doc_id: int, doc_type: str, uploaded_file: Any
    ) -> str:
        doc_type_display: str = _DOC_TYPE_DISPLAY.get(doc_type, doc_type)
        file_path = self._save_uploaded_file(uploaded_file, client_name, doc_type_display)
        if file_path:
            doc = self.identity_doc_service.get_identity_doc(doc_id)
            doc.file_path = file_path
            doc.save(update_fields=["file_path"])
            self.identity_doc_service.rename_uploaded_file(doc)
            logger.info(
                "证件文件保存成功",
                extra={
                    "client_id": client_id,
                    "doc_id": doc_id,
                    "file_path": file_path,
                    "action": "save_and_rename_file",
                },
            )
            self._submit_expiry_recognition(doc.pk)
        return file_path

    def _submit_expiry_recognition(self, doc_id: int) -> None:
        """上传后异步识别到期日期。

        上传是证件信息进入系统的唯一时刻，也只有在此时才有文件可识别，因此
        到期日必须在这里采集（而不是靠定时任务扫库：历史数据 30 份身份证中仅 1 份
        有文件，扫也扫不出东西）。识别失败/无平台配置只记日志，绝不阻断上传。
        """
        try:
            from apps.client.adapters.task_service_adapter import TaskServiceAdapter

            TaskServiceAdapter().submit_task(
                "apps.client.tasks.recognize_expiry_date_task",
                doc_id,
            )
        except Exception:
            logger.warning("提交证件到期日识别任务失败，跳过", extra={"doc_id": doc_id}, exc_info=True)
