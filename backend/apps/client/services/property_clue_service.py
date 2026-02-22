"""财产线索服务层。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import NotFoundError, ValidationException

if TYPE_CHECKING:
    from apps.client.models import PropertyClue, PropertyClueAttachment

    from .client_internal_query_service import ClientInternalQueryService

logger = logging.getLogger("apps.client")


class PropertyClueService:
    """财产线索服务。"""

    def __init__(self, internal_query_service: "ClientInternalQueryService | None" = None) -> None:
        self._internal_query_service = internal_query_service

    @property
    def internal_query_service(self) -> "ClientInternalQueryService":
        """延迟获取 ClientInternalQueryService"""
        if self._internal_query_service is None:
            from .client_internal_query_service import ClientInternalQueryService

            self._internal_query_service = ClientInternalQueryService()
        return self._internal_query_service

    def _validate_clue_type(self, clue_type: str) -> None:
        """验证线索类型是否有效。"""
        from apps.client.models import PropertyClue

        valid_types = dict(PropertyClue.CLUE_TYPE_CHOICES)
        if clue_type not in valid_types:
            raise ValidationException(
                message=_("无效的线索类型"),
                code="INVALID_CLUE_TYPE",
                errors={"clue_type": f"线索类型必须是: {', '.join(valid_types.keys())}"},
            )

    def _get_client_or_404(self, client_id: int) -> Any:
        """获取当事人，不存在则抛出 NotFoundError。"""
        client = self.internal_query_service.get_client(client_id=client_id)
        if not client:
            raise NotFoundError(
                message=_("当事人不存在"),
                code="CLIENT_NOT_FOUND",
                errors={"client_id": f"ID 为 {client_id} 的当事人不存在"},
            )
        return client

    @transaction.atomic
    def create_clue(
        self,
        client_id: int,
        data: dict[str, Any],
        user: Any = None,
    ) -> PropertyClue:
        """
        创建财产线索

        Requirements: 1.1
        """
        from apps.client.models import PropertyClue

        client = self._get_client_or_404(client_id)

        clue_type = data.get("clue_type", PropertyClue.BANK)
        self._validate_clue_type(clue_type)

        clue = PropertyClue.objects.create(client=client, clue_type=clue_type, content=data.get("content", ""))

        logger.info(
            "财产线索创建成功",
            extra={
                "clue_id": clue.id,
                "client_id": client_id,
                "clue_type": clue_type,
                "user_id": user.id if user else None,
                "action": "create_clue",
            },
        )

        return clue

    def get_clue(self, clue_id: int, user: Any = None) -> PropertyClue:
        """获取单个财产线索，不存在则抛出 NotFoundError。"""
        from apps.client.models import PropertyClue

        clue = PropertyClue.objects.prefetch_related("attachments").filter(id=clue_id).first()

        if not clue:
            raise NotFoundError(
                message=_("财产线索不存在"),
                code="CLUE_NOT_FOUND",
                errors={"clue_id": f"ID 为 {clue_id} 的财产线索不存在"},
            )

        assert isinstance(clue, PropertyClue)
        return clue

    def list_clues_by_client(
        self,
        client_id: int,
        user: Any = None,
    ) -> list[PropertyClue]:
        """
        获取当事人的所有财产线索

        Requirements: 4.1
        """
        from apps.client.models import PropertyClue

        self._get_client_or_404(client_id)

        clues = PropertyClue.objects.prefetch_related("attachments").filter(client_id=client_id).order_by("-created_at")

        return list(clues)

    @transaction.atomic
    def update_clue(
        self,
        clue_id: int,
        data: dict[str, Any],
        user: Any = None,
    ) -> PropertyClue:
        """
        更新财产线索

        Requirements: 5.1
        """
        # 1. 获取线索
        clue = self.get_clue(clue_id, user)

        # 2. 验证并更新线索类型
        if "clue_type" in data:
            self._validate_clue_type(data["clue_type"])
            clue.clue_type = data["clue_type"]

        # 3. 更新内容
        if "content" in data:
            clue.content = data["content"]

        clue.save()

        logger.info(
            "财产线索更新成功",
            extra={
                "clue_id": clue.id,
                "user_id": user.id if user else None,
                "action": "update_clue",
            },
        )

        return clue

    @transaction.atomic
    def delete_clue(self, clue_id: int, user: Any = None) -> None:
        """删除财产线索及其所有附件（含磁盘文件）。"""
        from apps.client.services.storage import delete_media_file

        clue = self.get_clue(clue_id, user)

        # 收集所有附件文件路径
        file_paths = [a.file_path for a in clue.attachments.all() if a.file_path]

        clue.delete()

        if file_paths:
            paths_snapshot = list(file_paths)
            transaction.on_commit(lambda paths=paths_snapshot: [delete_media_file(p) for p in paths])

        logger.info(
            "财产线索删除成功",
            extra={
                "clue_id": clue_id,
                "user_id": user.id if user else None,
                "action": "delete_clue",
            },
        )

    @transaction.atomic
    def add_attachment(
        self,
        clue_id: int,
        file_path: str,
        file_name: str,
        user: Any = None,
    ) -> PropertyClueAttachment:
        """为财产线索添加附件。"""
        from apps.client.models import PropertyClueAttachment

        clue = self.get_clue(clue_id, user)

        if not file_path or not file_name:
            raise ValidationException(
                message=_("文件路径和文件名不能为空"),
                code="INVALID_FILE_INFO",
                errors={
                    "file_path": "文件路径不能为空" if not file_path else None,
                    "file_name": "文件名不能为空" if not file_name else None,
                },
            )

        attachment = PropertyClueAttachment.objects.create(property_clue=clue, file_path=file_path, file_name=file_name)

        logger.info(
            "财产线索附件添加成功",
            extra={
                "attachment_id": attachment.id,
                "clue_id": clue_id,
                "file_name": file_name,
                "user_id": user.id if user else None,
                "action": "add_attachment",
            },
        )

        return attachment

    def save_uploaded_file_to_dir(self, uploaded_file: Any, rel_dir: str) -> tuple[str, str]:
        """保存上传文件到指定目录，返回 (rel_path, original_name)（供 Admin Form 使用）"""
        from apps.client.services.storage import save_uploaded_file

        return save_uploaded_file(uploaded_file, rel_dir=rel_dir)

    @transaction.atomic
    def add_attachment_from_upload(
        self,
        clue_id: int,
        uploaded_file: Any,
        user: Any = None,
    ) -> "PropertyClueAttachment":
        """从上传文件添加附件（文件 IO 在 Service 层处理）"""
        from apps.core.services.file_upload_service import FileUploadService

        upload_service = FileUploadService()
        saved_path = upload_service.save_file(
            uploaded_file,
            base_dir=f"property_clue_attachments/{clue_id}",
            preserve_name=True,
        )
        file_name: str = uploaded_file.name or saved_path.name
        return self.add_attachment(
            clue_id=clue_id,
            file_path=str(saved_path),
            file_name=file_name,
            user=user,
        )

    @transaction.atomic
    def delete_attachment(self, attachment_id: int, user: Any = None) -> None:
        """删除财产线索附件（含磁盘文件）。"""
        from apps.client.models import PropertyClueAttachment
        from apps.client.services.storage import delete_media_file

        try:
            attachment = PropertyClueAttachment.objects.get(id=attachment_id)
        except PropertyClueAttachment.DoesNotExist as e:
            raise NotFoundError(
                message=_("附件不存在"),
                code="ATTACHMENT_NOT_FOUND",
                errors={"attachment_id": f"ID 为 {attachment_id} 的附件不存在"},
            ) from e

        file_path = attachment.file_path
        attachment.delete()

        if file_path:
            transaction.on_commit(lambda fp=file_path: delete_media_file(fp))

        logger.info(
            "财产线索附件删除成功",
            extra={
                "attachment_id": attachment_id,
                "user_id": user.id if user else None,
                "action": "delete_attachment",
            },
        )

    def get_content_template(self, clue_type: str) -> str:
        """获取指定线索类型的内容模板。"""
        from apps.client.models import PropertyClue

        return str(PropertyClue.CONTENT_TEMPLATES.get(clue_type, ""))
