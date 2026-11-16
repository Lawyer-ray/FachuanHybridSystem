"""当事人 Admin 服务层。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.core.files.storage import default_storage

from apps.client.models import Client, ClientIdentityDoc
from apps.client.services.client_admin_file_mixin import _DOC_TYPE_DISPLAY, ClientAdminFileMixin
from apps.client.services.wiring import get_gsxt_report_port
from apps.core.exceptions import ValidationException
from apps.core.filesystem.upload_paths import MediaEntity
from apps.core.services.storage_service import sanitize_upload_filename, to_media_abs

if TYPE_CHECKING:
    from .client_identity_doc_service import ClientIdentityDocService
    from .client_internal_query_service import ClientInternalQueryService

logger = logging.getLogger("apps.client")


def _build_gsxt_report_rel_path(*, client: Client) -> str:
    """构造企业信用报告的 media 相对路径（client.name 经清洗，防目录逃逸）。"""
    report_name = sanitize_upload_filename(f"{client.name[:20]}_企业信用报告.pdf") or "企业信用报告.pdf"
    return f"{MediaEntity.CLIENT_DOCS}/{client.pk}/{report_name}"


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
        identity_doc_service: ClientIdentityDocService | None = None,
        internal_query_service: ClientInternalQueryService | None = None,
    ) -> None:
        self._identity_doc_service = identity_doc_service
        self._internal_query_service = internal_query_service

    @property
    def identity_doc_service(self) -> ClientIdentityDocService:  # type: ignore[override]
        """延迟获取 ClientIdentityDocService"""
        if self._identity_doc_service is None:
            from .client_identity_doc_service import ClientIdentityDocService

            self._identity_doc_service = ClientIdentityDocService()
        return self._identity_doc_service

    @property
    def internal_query_service(self) -> ClientInternalQueryService:
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
                message="客户不存在",
                code="CLIENT_NOT_FOUND",
                errors={"client_id": "ID 为 %(id)s 的客户不存在" % {"id": client_id}},
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

    def _process_single_form(self, client: Client, form_data: dict[str, Any], admin_user: str) -> dict[str, Any] | None:
        """处理单个表单项。"""
        doc_type = form_data.get("doc_type")
        if not doc_type:
            logger.warning(
                "表单项缺少证件类型",
                extra={"client_id": client.pk, "admin_user": admin_user, "action": "process_single_form"},
            )
            return None

        doc_type_display = _DOC_TYPE_DISPLAY.get(doc_type, doc_type)

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

    def save_gsxt_report(self, *, client: Client, uploaded_file: Any, task_id: int, include_content: bool) -> str:
        """保存企业信用报告 PDF 并挂为营业执照附件，标记报告任务成功。

        include_content=True 时读取文件内容回传任务（admin 上传视图）；
        False 时文件已落盘、任务侧不重复存内容（inline 表单集路径）。
        """
        rel_path = _build_gsxt_report_rel_path(client=client)
        saved_name = default_storage.save(rel_path, uploaded_file)

        doc, _ = ClientIdentityDoc.objects.get_or_create(
            client=client,
            doc_type=ClientIdentityDoc.BUSINESS_LICENSE,
        )
        doc.file_path = str(saved_name)
        doc.save(update_fields=["file_path"])

        file_content = to_media_abs(saved_name).read_bytes() if include_content else b""
        get_gsxt_report_port().upload_report(task_id=task_id, file_content=file_content, file_name=saved_name)
        return saved_name

    def import_json_items(self, data_list: list[dict[str, Any]]) -> tuple[int, int, list[str]]:
        """批量导入当事人（含附件），返回 (成功数, 跳过数, 错误列表)。"""
        from .client_resolve_service import ClientResolveService

        svc = ClientResolveService()
        success = skipped = 0
        errors: list[str] = []
        for i, item in enumerate(data_list, 1):
            try:
                id_number = item.get("id_number")
                before = Client.objects.filter(id_number=id_number).exists() if id_number else False
                svc.resolve_with_attachments(item)
                if not before:
                    success += 1
                else:
                    skipped += 1
            except Exception as exc:
                logger.exception("导入客户失败", extra={"index": i, "client_name": item.get("name", "?")})
                errors.append(f"[{i}] {item.get('name', '?')} ({type(exc).__name__}): {exc}")
        return success, skipped, errors
