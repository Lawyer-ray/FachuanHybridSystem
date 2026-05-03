"""当事人写操作服务。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.client.models import Client
from apps.core.exceptions import ForbiddenError, ValidationException

if TYPE_CHECKING:
    from ninja.files import UploadedFile

    from apps.client.workflows import ClientDeletionWorkflow

    from .client_access_policy import ClientAccessPolicy
    from .client_identity_doc_service import ClientIdentityDocService
    from .client_query_service import ClientQueryService

logger = logging.getLogger("apps.client")


class ClientMutationService:
    _VALID_CLIENT_TYPES: list[str] = [Client.NATURAL, Client.LEGAL, Client.NON_LEGAL_ORG]
    _UPDATABLE_FIELDS: set[str] = {
        "name",
        "phone",
        "address",
        "client_type",
        "id_number",
        "legal_representative",
        "legal_representative_id_number",
        "is_our_client",
    }

    def __init__(
        self,
        access_policy: ClientAccessPolicy | None = None,
        query_service: ClientQueryService | None = None,
        deletion_workflow: ClientDeletionWorkflow | None = None,
        identity_doc_service: ClientIdentityDocService | None = None,
    ) -> None:
        self._access_policy = access_policy
        self._query_service = query_service
        self._deletion_workflow = deletion_workflow
        self._identity_doc_service = identity_doc_service

    @property
    def access_policy(self) -> ClientAccessPolicy:
        if self._access_policy is None:
            from .client_access_policy import ClientAccessPolicy

            self._access_policy = ClientAccessPolicy()
        return self._access_policy

    @property
    def query_service(self) -> ClientQueryService:
        if self._query_service is None:
            from .client_query_service import ClientQueryService

            self._query_service = ClientQueryService()
        return self._query_service

    @property
    def identity_doc_service(self) -> ClientIdentityDocService:
        if self._identity_doc_service is None:
            from .client_identity_doc_service import ClientIdentityDocService

            self._identity_doc_service = ClientIdentityDocService()
        return self._identity_doc_service

    @property
    def deletion_workflow(self) -> ClientDeletionWorkflow:
        if self._deletion_workflow is None:
            from apps.client.workflows import ClientDeletionWorkflow

            self._deletion_workflow = ClientDeletionWorkflow()
        return self._deletion_workflow

    @transaction.atomic
    def create_client(self, *, data: dict[str, Any], user: Any | None = None) -> Client:
        try:
            self.access_policy.ensure_can_create_client(user)
        except ForbiddenError:
            logger.warning(
                "用户尝试创建客户但权限不足",
                extra={"user_id": getattr(user, "id", None), "action": "create_client"},
            )
            raise

        self._validate_create_data(data)

        client = Client(**data)
        try:
            client.full_clean()
        except ValidationError as e:
            raise ValidationException(
                message=_("验证失败"),
                code="VALIDATION_ERROR",
                errors=e.message_dict,
            ) from e
        client.save()
        logger.info(
            "客户创建成功",
            extra={"client_id": client.pk, "user_id": getattr(user, "id", None), "action": "create_client"},
        )
        return client

    @transaction.atomic
    def update_client(self, *, client_id: int, data: dict[str, Any], user: Any | None = None) -> Client:
        try:
            self.access_policy.ensure_can_update_client(user)
        except ForbiddenError:
            logger.warning(
                "用户尝试更新客户但权限不足",
                extra={"user_id": getattr(user, "id", None), "client_id": client_id, "action": "update_client"},
            )
            raise

        client = self.query_service.get_client(client_id=client_id, user=user)

        self._validate_update_data(client, data)

        updated_fields = []
        for key, value in data.items():
            if key in self._UPDATABLE_FIELDS:
                setattr(client, key, value)
                updated_fields.append(key)

        if updated_fields:
            client.save(update_fields=updated_fields)
        logger.info(
            "客户更新成功",
            extra={"client_id": client.pk, "user_id": getattr(user, "id", None), "action": "update_client"},
        )
        return client

    @transaction.atomic
    def delete_client(self, *, client_id: int, user: Any | None = None) -> None:
        try:
            self.access_policy.ensure_can_delete_client(user)
        except ForbiddenError:
            logger.warning(
                "用户尝试删除客户但权限不足",
                extra={"user_id": getattr(user, "id", None), "client_id": client_id, "action": "delete_client"},
            )
            raise

        client = self.query_service.get_client(client_id=client_id, user=user)
        file_paths = self.deletion_workflow.collect_client_file_paths(client_id=client.pk)
        client.delete()
        self.deletion_workflow.cleanup_files_on_commit(file_paths=file_paths)

        logger.info(
            "客户删除成功",
            extra={"client_id": client_id, "user_id": getattr(user, "id", None), "action": "delete_client"},
        )

    @transaction.atomic
    def create_client_with_docs(
        self,
        *,
        data: dict[str, Any],
        doc_types: list[str],
        files: list[UploadedFile],
        user: Any | None = None,
    ) -> Client:
        """创建客户并上传证件文档（事务内完成）。"""
        client = self.create_client(data=data, user=user)
        for doc_type, file in zip(doc_types, files, strict=True):
            self.identity_doc_service.add_identity_doc_from_upload(
                client_id=client.id,
                doc_type=doc_type,
                uploaded_file=file,
                user=user,
            )
        client.refresh_from_db()
        return client

    def _validate_create_data(self, data: dict[str, Any]) -> None:
        if not data.get("name"):
            raise ValidationException(
                message=_("客户名称不能为空"), code="INVALID_NAME", errors={"name": _("客户名称不能为空")}
            )

        if data.get("client_type") not in self._VALID_CLIENT_TYPES:
            raise ValidationException(
                message=_("无效的客户类型"),
                code="INVALID_CLIENT_TYPE",
                errors={"client_type": _("无效的客户类型")},
            )

        if data.get("client_type") == Client.LEGAL and not data.get("legal_representative"):
            raise ValidationException(
                message=_("法人客户必须填写法定代表人"),
                code="MISSING_LEGAL_REPRESENTATIVE",
                errors={"legal_representative": _("法人客户必须填写法定代表人")},
            )

    def _validate_update_data(self, client: Client, data: dict[str, Any]) -> None:
        if "name" in data and not data["name"]:
            raise ValidationException(
                message=_("客户名称不能为空"), code="INVALID_NAME", errors={"name": _("客户名称不能为空")}
            )

        if "client_type" in data and data["client_type"] not in self._VALID_CLIENT_TYPES:
            raise ValidationException(
                message=_("无效的客户类型"),
                code="INVALID_CLIENT_TYPE",
                errors={"client_type": _("无效的客户类型")},
            )

        client_type = data.get("client_type", client.client_type)
        legal_rep = data.get("legal_representative", client.legal_representative)
        if client_type == Client.LEGAL and not legal_rep:
            raise ValidationException(
                message=_("法人客户必须填写法定代表人"),
                code="MISSING_LEGAL_REPRESENTATIVE",
                errors={"legal_representative": _("法人客户必须填写法定代表人")},
            )
