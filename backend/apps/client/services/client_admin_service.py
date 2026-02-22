"""当事人 Admin 服务层。"""

from django.utils.translation import gettext_lazy as _
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.core.exceptions import ValidationException

from apps.client.models import Client, ClientIdentityDoc
from apps.client.services.client_admin_file_mixin import ClientAdminFileMixin

if TYPE_CHECKING:
    from .client_service import ClientService
    from .client_identity_doc_service import ClientIdentityDocService
    from .client_internal_query_service import ClientInternalQueryService
    from .client_mutation_service import ClientMutationService

User = get_user_model()
logger = logging.getLogger("apps.client")


@dataclass
class ImportResult:
    """JSON 导入结果"""

    success: bool
    client: Client | None = None
    error_message: str | None = None


class ClientAdminService(ClientAdminFileMixin):
    """
    客户 Admin 服务

    封装 Admin 层的复杂业务逻辑，确保 Admin 层方法保持在 20 行以内

    职责：
    1. 处理 JSON 数据导入
    2. 处理表单集文件上传
    3. 管理数据库事务
    4. 记录操作日志
    """

    def __init__(
        self,
        client_service: "ClientService | None" = None,
        identity_doc_service: "ClientIdentityDocService | None" = None,
        internal_query_service: "ClientInternalQueryService | None" = None,
        mutation_service: "ClientMutationService | None" = None,
    ) -> None:
        self._client_service = client_service
        self._identity_doc_service = identity_doc_service
        self._internal_query_service = internal_query_service
        self._mutation_service = mutation_service

    @property
    def client_service(self) -> "ClientService":
        """延迟获取 ClientService"""
        if self._client_service is None:
            from .client_service import ClientService

            self._client_service = ClientService()
        return self._client_service

    @property
    def identity_doc_service(self) -> "ClientIdentityDocService":
        """延迟获取 ClientIdentityDocService"""
        if self._identity_doc_service is None:
            from .client_identity_doc_service import ClientIdentityDocService

            self._identity_doc_service = ClientIdentityDocService()
        return self._identity_doc_service

    @property
    def mutation_service(self) -> "ClientMutationService":
        """延迟获取 ClientMutationService"""
        if self._mutation_service is None:
            from .client_mutation_service import ClientMutationService

            self._mutation_service = ClientMutationService()
        return self._mutation_service

    @property
    def internal_query_service(self) -> "ClientInternalQueryService":
        """延迟获取 ClientInternalQueryService"""
        if self._internal_query_service is None:
            from .client_internal_query_service import ClientInternalQueryService

            self._internal_query_service = ClientInternalQueryService()
        return self._internal_query_service

    @transaction.atomic
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
        """
        处理表单集文件上传

        Args:
            client_id: 客户 ID
            formset_data: 表单集数据列表
            admin_user: 管理员用户名

        Raises:
            ValidationException: 数据验证失败
        """
        # 1. 验证客户存在
        client = self.internal_query_service.get_client(client_id=client_id)
        if not client:
            raise ValidationException(
                message=_("客户不存在"),
                code="CLIENT_NOT_FOUND",
                errors={"client_id": f"ID 为 {client_id} 的客户不存在"},
            )

        # 2. 处理每个表单项
        processed_files = []
        for form_data in formset_data:
            if self._should_process_form(form_data):
                file_info = self._process_single_form(client_id, form_data, admin_user)
                if file_info:
                    processed_files.append(file_info)

        # 3. 记录操作日志
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
        """
        判断是否应该处理该表单项

        Args:
            form_data: 表单数据

        Returns:
            是否应该处理
        """
        # 跳过标记为删除的项
        if form_data.get("DELETE"):
            return False

        # 必须有文件路径或上传的文件
        return bool(form_data.get("file_path") or form_data.get("uploaded_file"))

    def _process_single_form(self, client_id: int, form_data: dict[str, Any], admin_user: str) -> dict[str, Any] | None:
        """
        处理单个表单项

        Args:
            client_id: 客户 ID
            form_data: 表单数据
            admin_user: 管理员用户名

        Returns:
            处理后的文件信息，如果没有处理则返回 None
        """
        # 1. 获取证件类型
        doc_type = form_data.get("doc_type")
        if not doc_type:
            logger.warning(
                "表单项缺少证件类型",
                extra={"client_id": client_id, "admin_user": admin_user, "action": "process_single_form"},
            )
            return None

        # 2. 获取当事人名称和证件类型显示名
        client = self.internal_query_service.get_client(client_id=client_id)
        client_name = client.name if client else ""
        doc_type_display = dict(ClientIdentityDoc.DOC_TYPE_CHOICES).get(doc_type, doc_type)

        # 3. 处理文件存储（传递当事人名称和证件类型用于重命名）
        file_path = self._handle_file_storage(form_data, client_name, doc_type_display)
        if not file_path:
            return None

        # 4. 更新或创建 ClientIdentityDoc 记录
        doc_id = form_data.get("id")
        if doc_id:
            # 更新现有记录
            self._update_identity_doc(doc_id, file_path, admin_user)
        else:
            # 创建新记录，通过 identity_doc_service 委托
            self.identity_doc_service.add_identity_doc(
                client_id=client_id,
                doc_type=doc_type,
                file_path=file_path,
            )

        return {"doc_type": doc_type, "file_path": file_path, "doc_id": doc_id}
