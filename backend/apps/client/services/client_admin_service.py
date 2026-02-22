"""当事人 Admin 服务层。"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from apps.core.exceptions import ValidationException

from apps.client.services.client_admin_file_mixin import ClientAdminFileMixin

if TYPE_CHECKING:
    from apps.client.models import Client
    from .client_identity_doc_service import ClientIdentityDocService
    from .client_internal_query_service import ClientInternalQueryService

logger = logging.getLogger("apps.client")


@dataclass
class ImportResult:
    """JSON 导入结果"""

    success: bool
    client: Client | None = None
    error_message: str | None = None


class ClientAdminService(ClientAdminFileMixin):
    """客户 Admin 服务：JSON 导入、表单集文件上传、事务管理。"""

    def __init__(
        self,
        identity_doc_service: "ClientIdentityDocService | None" = None,
        internal_query_service: "ClientInternalQueryService | None" = None,
    ) -> None:
        self._identity_doc_service = identity_doc_service
        self._internal_query_service = internal_query_service

    @property
    def identity_doc_service(self) -> "ClientIdentityDocService":
        """延迟获取 ClientIdentityDocService"""
        if self._identity_doc_service is None:
            from .client_identity_doc_service import ClientIdentityDocService

            self._identity_doc_service = ClientIdentityDocService()
        return self._identity_doc_service

    @property
    def internal_query_service(self) -> "ClientInternalQueryService":
        """延迟获取 ClientInternalQueryService"""
        if self._internal_query_service is None:
            from .client_internal_query_service import ClientInternalQueryService

            self._internal_query_service = ClientInternalQueryService()
        return self._internal_query_service

    def import_from_json(self, json_data: dict[str, Any], admin_user: str) -> ImportResult:
        """从 JSON 导入客户，委托给 ClientJsonImporter。"""
        from .importer import ClientJsonImporter

        importer = ClientJsonImporter()
        result = importer.import_from_json(json_data, admin_user=admin_user)
        if result.success and result.client_id is not None:
            client = self.internal_query_service.get_client(client_id=result.client_id)
            return ImportResult(success=True, client=client)
        return ImportResult(success=False, error_message=result.error_message)

    def process_formset_files(self, client_id: int, formset_data: list[dict[str, Any]], admin_user: str) -> None:
        """处理表单集文件上传。"""
        client = self.internal_query_service.get_client(client_id=client_id)
        if not client:
            raise ValidationException(
                message=_("客户不存在"),
                code="CLIENT_NOT_FOUND",
                errors={"client_id": str(_("ID 为 %(id)s 的客户不存在") % {"id": client_id})},
            )

        processed_files = []
        for form_data in formset_data:
            if self._should_process_form(form_data):
                file_info = self._process_single_form(client, form_data, admin_user)
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
        """判断是否应该处理该表单项。"""
        if form_data.get("DELETE"):
            return False
        return bool(form_data.get("file_path") or form_data.get("uploaded_file"))

    def _process_single_form(self, client: "Client", form_data: dict[str, Any], admin_user: str) -> dict[str, Any] | None:
        """处理单个表单项。"""
        doc_type = form_data.get("doc_type")
        if not doc_type:
            logger.warning(
                "表单项缺少证件类型",
                extra={"client_id": client.pk, "admin_user": admin_user, "action": "process_single_form"},
            )
            return None

        from apps.client.models import ClientIdentityDoc  # noqa: PLC0415

        doc_type_display = dict(ClientIdentityDoc.DOC_TYPE_CHOICES).get(doc_type, doc_type)

        file_path = self._handle_file_storage(form_data, client.name, doc_type_display)
        if not file_path:
            return None

        doc_id = form_data.get("id")
        if doc_id:
            self._update_identity_doc(doc_id, file_path, admin_user)
        else:
            self.identity_doc_service.add_identity_doc(
                client_id=client.pk,
                doc_type=doc_type,
                file_path=file_path,
            )

        return {"doc_type": doc_type, "file_path": file_path, "doc_id": doc_id}
