"""
客户 Admin 服务层
封装 Admin 层的复杂业务逻辑
"""

from django.utils.translation import gettext_lazy as _
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.core.exceptions import ValidationException

from apps.client.models import Client, ClientIdentityDoc
from apps.client.services.client_admin_file_mixin import ClientAdminFileMixin

if TYPE_CHECKING:
    from .client_service import ClientService
    from .clientidentitydoc_service import ClientIdentityDocService

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
        client_service: Optional["ClientService"] = None,
        identity_doc_service: Optional["ClientIdentityDocService"] = None,
    ):
        """
        初始化服务

        Args:
            client_service: ClientService 实例，支持依赖注入
            identity_doc_service: ClientIdentityDocService 实例，支持依赖注入
        """
        self._client_service = client_service
        self._identity_doc_service = identity_doc_service

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

    @transaction.atomic
    def import_from_json(self, json_data: dict[str, Any], admin_user: str) -> ImportResult:
        """
        从 JSON 导入客户

        Args:
            json_data: JSON 数据字典
            admin_user: 管理员用户名

        Returns:
            ImportResult: 导入结果

        Raises:
            ValidationException: 数据验证失败
        """
        try:
            # 1. 验证 JSON 数据完整性
            self._validate_json_data(json_data)

            # 2. 提取客户基本信息
            client_data = self._extract_client_data(json_data)

            # 3. 创建客户
            client = Client.objects.create(**client_data)

            # 4. 创建关联的证件文档
            if "identity_docs" in json_data:
                self._create_identity_docs(client, json_data["identity_docs"], admin_user)

            # 5. 记录操作日志
            logger.info(
                "JSON 导入客户成功",
                extra={
                    "client_id": client.id,
                    "client_name": client.name,
                    "admin_user": admin_user,
                    "action": "import_from_json",
                },
            )

            return ImportResult(success=True, client=client)

        except ValidationException:
            # 重新抛出验证异常
            raise
        except Exception as e:
            # 记录错误日志
            logger.error(
                "JSON 导入客户失败: %s",
                e,
                extra={"admin_user": admin_user, "action": "import_from_json", "error": str(e)},
            )
            return ImportResult(success=False, error_message=f"导入失败: {e!s}")

    def _validate_json_data(self, json_data: dict[str, Any]) -> None:
        """
        验证 JSON 数据完整性

        Args:
            json_data: JSON 数据字典

        Raises:
            ValidationException: 数据验证失败
        """
        errors = {}

        # 验证必填字段
        if not json_data.get("name"):
            errors["name"] = "客户名称不能为空"

        # 验证客户类型
        client_type = json_data.get("client_type")
        valid_types = [Client.NATURAL, Client.LEGAL, Client.NON_LEGAL_ORG]
        if not client_type or client_type not in valid_types:
            errors["client_type"] = f"客户类型必须是: {', '.join(valid_types)}"

        # 验证法人必须有法定代表人
        if client_type == Client.LEGAL and not json_data.get("legal_representative"):
            errors["legal_representative"] = "法人客户必须填写法定代表人"

        # 验证证件文档数据
        if "identity_docs" in json_data:
            self._validate_identity_docs_data(json_data["identity_docs"], errors)

        if errors:
            raise ValidationException(message=_("JSON 数据验证失败"), code="INVALID_JSON", errors=errors)

    def _validate_identity_docs_data(self, docs_data: list[dict[str, Any]], errors: dict[str, Any]) -> None:
        """
        验证证件文档数据

        Args:
            docs_data: 证件文档数据列表
            errors: 错误字典
        """
        if not isinstance(docs_data, list):
            errors["identity_docs"] = "证件文档数据必须是数组"
            return

        valid_doc_types = [choice[0] for choice in ClientIdentityDoc.DOC_TYPE_CHOICES]

        for i, doc_data in enumerate(docs_data):
            doc_errors = {}

            if not doc_data.get("doc_type"):
                doc_errors["doc_type"] = "证件类型不能为空"
            elif doc_data["doc_type"] not in valid_doc_types:
                doc_errors["doc_type"] = f"证件类型必须是: {', '.join(valid_doc_types)}"

            if not doc_data.get("file_path"):
                doc_errors["file_path"] = "文件路径不能为空"

            if doc_errors:
                errors[f"identity_docs[{i}]"] = doc_errors

    def _extract_client_data(self, json_data: dict[str, Any]) -> dict[str, Any]:
        """
        提取客户基本信息

        Args:
            json_data: JSON 数据字典

        Returns:
            客户数据字典
        """
        client_fields = [
            "name",
            "phone",
            "address",
            "client_type",
            "id_number",
            "legal_representative",
            "is_our_client",
        ]

        client_data = {}
        for field in client_fields:
            if field in json_data:
                client_data[field] = json_data[field]

        # 设置默认值
        if "is_our_client" not in client_data:
            client_data["is_our_client"] = False

        return client_data

    def _create_identity_docs(self, client: Client, docs_data: list[dict[str, Any]], admin_user: str) -> None:
        """
        创建关联的证件文档

        Args:
            client: 客户对象
            docs_data: 证件文档数据列表
            admin_user: 管理员用户名
        """
        for doc_data in docs_data:
            self.identity_doc_service.add_identity_doc(
                client_id=client.id,
                doc_type=doc_data["doc_type"],
                file_path=doc_data["file_path"],
                user=None,  # Admin 操作，用户信息在日志中记录
            )

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
        try:
            # 1. 验证客户存在
            client = Client.objects.filter(id=client_id).first()
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

        except Exception as e:
            # 记录错误日志
            logger.error(
                "表单集文件处理失败: %s",
                e,
                extra={
                    "client_id": client_id,
                    "admin_user": admin_user,
                    "action": "process_formset_files",
                    "error": str(e),
                },
            )
            raise

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
        client = Client.objects.filter(id=client_id).first()
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
            # 创建新记录（直接创建，不调用 add_identity_doc 避免重复重命名）
            ClientIdentityDoc.objects.create(client_id=client_id, doc_type=doc_type, file_path=file_path)

        return {"doc_type": doc_type, "file_path": file_path, "doc_id": doc_id}

    def parse_client_text(self, text: str) -> dict[str, Any]:
        """
        解析客户文本信息

        Args:
            text: 待解析的文本

        Returns:
            解析后的客户数据字典
        """
        from .text_parser import parse_client_text

        return parse_client_text(text)

    def parse_multiple_clients_text(self, text: str) -> list[dict[str, Any]]:
        """
        解析包含多个客户的文本信息

        Args:
            text: 待解析的文本

        Returns:
            解析后的客户数据列表
        """
        from .text_parser import parse_multiple_clients_text

        return parse_multiple_clients_text(text)
