"""
财产线索服务层
处理财产线索相关的业务逻辑
"""
from typing import List, Optional, Dict, Any
from django.db.models import QuerySet
from django.db import transaction
from django.contrib.auth import get_user_model

from apps.core.exceptions import NotFoundError, ValidationException
from ..models import PropertyClue, PropertyClueAttachment
import logging

User = get_user_model()
logger = logging.getLogger("apps.client")


class PropertyClueService:
    """
    财产线索服务

    职责：
    1. 封装财产线索相关的所有业务逻辑
    2. 管理数据库事务
    3. 优化数据库查询
    4. 提供内容模板功能
    """

    def __init__(self, client_service: Optional["ClientService"] = None):
        """
        初始化服务
        
        Args:
            client_service: ClientService 实例，支持依赖注入
        """
        self._client_service = client_service

    @property
    def client_service(self) -> "ClientService":
        """延迟获取 ClientService"""
        if self._client_service is None:
            from .client_service import ClientService
            self._client_service = ClientService()
        return self._client_service

    @transaction.atomic
    def create_clue(
        self,
        client_id: int,
        data: Dict[str, Any],
        user: Optional[User] = None
    ) -> PropertyClue:
        """
        创建财产线索

        Args:
            client_id: 当事人 ID
            data: 线索数据（包含 clue_type, content）
            user: 当前用户

        Returns:
            创建的财产线索对象

        Raises:
            NotFoundError: 当事人不存在
            ValidationException: 数据验证失败

        Requirements: 1.1
        """
        # 1. 验证当事人是否存在
        client = self.client_service._get_client_internal(client_id)
        if not client:
            raise NotFoundError(
                message=f"当事人不存在",
                code="CLIENT_NOT_FOUND",
                errors={"client_id": f"ID 为 {client_id} 的当事人不存在"}
            )

        # 2. 验证线索类型
        clue_type = data.get("clue_type", PropertyClue.BANK)
        if clue_type not in dict(PropertyClue.CLUE_TYPE_CHOICES).keys():
            raise ValidationException(
                message="无效的线索类型",
                code="INVALID_CLUE_TYPE",
                errors={"clue_type": f"线索类型必须是: {', '.join(dict(PropertyClue.CLUE_TYPE_CHOICES).keys())}"}
            )

        # 3. 创建财产线索
        clue = PropertyClue.objects.create(
            client=client,
            clue_type=clue_type,
            content=data.get("content", "")
        )

        # 4. 记录日志
        logger.info(
            f"财产线索创建成功",
            extra={
                "clue_id": clue.id,
                "client_id": client_id,
                "clue_type": clue_type,
                "user_id": user.id if user else None,
                "action": "create_clue"
            }
        )

        return clue

    def get_clue(self, clue_id: int, user: Optional[User] = None) -> PropertyClue:
        """
        获取单个财产线索

        Args:
            clue_id: 线索 ID
            user: 当前用户

        Returns:
            财产线索对象

        Raises:
            NotFoundError: 线索不存在

        Requirements: 1.1
        """
        # 使用 prefetch_related 优化附件查询
        clue = PropertyClue.objects.prefetch_related("attachments").filter(
            id=clue_id
        ).first()

        if not clue:
            raise NotFoundError(
                message=f"财产线索不存在",
                code="CLUE_NOT_FOUND",
                errors={"clue_id": f"ID 为 {clue_id} 的财产线索不存在"}
            )

        return clue

    def list_clues_by_client(
        self,
        client_id: int,
        user: Optional[User] = None
    ) -> List[PropertyClue]:
        """
        获取当事人的所有财产线索

        Args:
            client_id: 当事人 ID
            user: 当前用户

        Returns:
            财产线索列表

        Requirements: 4.1
        """
        # 验证当事人是否存在
        client = self.client_service._get_client_internal(client_id)
        if not client:
            raise NotFoundError(
                message=f"当事人不存在",
                code="CLIENT_NOT_FOUND",
                errors={"client_id": f"ID 为 {client_id} 的当事人不存在"}
            )

        # 使用 prefetch_related 优化附件查询
        clues = PropertyClue.objects.prefetch_related("attachments").filter(
            client_id=client_id
        ).order_by("-created_at")

        return list(clues)

    @transaction.atomic
    def update_clue(
        self,
        clue_id: int,
        data: Dict[str, Any],
        user: Optional[User] = None
    ) -> PropertyClue:
        """
        更新财产线索

        Args:
            clue_id: 线索 ID
            data: 更新数据（可包含 clue_type, content）
            user: 当前用户

        Returns:
            更新后的财产线索对象

        Raises:
            NotFoundError: 线索不存在
            ValidationException: 数据验证失败

        Requirements: 5.1
        """
        # 1. 获取线索
        clue = self.get_clue(clue_id, user)

        # 2. 验证线索类型（如果提供）
        if "clue_type" in data:
            clue_type = data["clue_type"]
            if clue_type not in dict(PropertyClue.CLUE_TYPE_CHOICES).keys():
                raise ValidationException(
                    message="无效的线索类型",
                    code="INVALID_CLUE_TYPE",
                    errors={"clue_type": f"线索类型必须是: {', '.join(dict(PropertyClue.CLUE_TYPE_CHOICES).keys())}"}
                )
            clue.clue_type = clue_type

        # 3. 更新内容（如果提供）
        if "content" in data:
            clue.content = data["content"]

        # 4. 保存更新
        clue.save()

        # 5. 记录日志
        logger.info(
            f"财产线索更新成功",
            extra={
                "clue_id": clue.id,
                "user_id": user.id if user else None,
                "action": "update_clue"
            }
        )

        return clue

    @transaction.atomic
    def delete_clue(self, clue_id: int, user: Optional[User] = None) -> None:
        """
        删除财产线索及其所有附件

        Args:
            clue_id: 线索 ID
            user: 当前用户

        Raises:
            NotFoundError: 线索不存在

        Requirements: 5.2, 7.2
        """
        # 1. 获取线索
        clue = self.get_clue(clue_id, user)

        # 2. 删除线索（级联删除附件）
        clue.delete()

        # 3. 记录日志
        logger.info(
            f"财产线索删除成功",
            extra={
                "clue_id": clue_id,
                "user_id": user.id if user else None,
                "action": "delete_clue"
            }
        )

    @transaction.atomic
    def add_attachment(
        self,
        clue_id: int,
        file_path: str,
        file_name: str,
        user: Optional[User] = None
    ) -> PropertyClueAttachment:
        """
        为财产线索添加附件

        Args:
            clue_id: 线索 ID
            file_path: 文件路径
            file_name: 文件名
            user: 当前用户

        Returns:
            创建的附件对象

        Raises:
            NotFoundError: 线索不存在
            ValidationException: 数据验证失败

        Requirements: 3.1
        """
        # 1. 验证线索是否存在
        clue = self.get_clue(clue_id, user)

        # 2. 验证文件信息
        if not file_path or not file_name:
            raise ValidationException(
                message="文件路径和文件名不能为空",
                code="INVALID_FILE_INFO",
                errors={
                    "file_path": "文件路径不能为空" if not file_path else None,
                    "file_name": "文件名不能为空" if not file_name else None
                }
            )

        # 3. 创建附件
        attachment = PropertyClueAttachment.objects.create(
            property_clue=clue,
            file_path=file_path,
            file_name=file_name
        )

        # 4. 记录日志
        logger.info(
            f"财产线索附件添加成功",
            extra={
                "attachment_id": attachment.id,
                "clue_id": clue_id,
                "file_name": file_name,
                "user_id": user.id if user else None,
                "action": "add_attachment"
            }
        )

        return attachment

    @transaction.atomic
    def delete_attachment(
        self,
        attachment_id: int,
        user: Optional[User] = None
    ) -> None:
        """
        删除财产线索附件

        Args:
            attachment_id: 附件 ID
            user: 当前用户

        Raises:
            NotFoundError: 附件不存在

        Requirements: 5.3
        """
        # 1. 获取附件
        try:
            attachment = PropertyClueAttachment.objects.get(id=attachment_id)
        except PropertyClueAttachment.DoesNotExist:
            raise NotFoundError(
                message=f"附件不存在",
                code="ATTACHMENT_NOT_FOUND",
                errors={"attachment_id": f"ID 为 {attachment_id} 的附件不存在"}
            )

        # 2. 删除附件
        attachment.delete()

        # 3. 记录日志
        logger.info(
            f"财产线索附件删除成功",
            extra={
                "attachment_id": attachment_id,
                "user_id": user.id if user else None,
                "action": "delete_attachment"
            }
        )

    @staticmethod
    def get_content_template(clue_type: str) -> str:
        """
        获取指定线索类型的内容模板

        Args:
            clue_type: 线索类型

        Returns:
            内容模板字符串

        Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
        """
        return PropertyClue.CONTENT_TEMPLATES.get(clue_type, "")
