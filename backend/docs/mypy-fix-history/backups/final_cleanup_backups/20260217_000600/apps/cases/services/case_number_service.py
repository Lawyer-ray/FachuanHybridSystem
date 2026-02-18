"""
案件案号服务层
处理案件案号相关的业务逻辑
"""
from typing import Optional, Dict, Any
from django.db import transaction
from django.db.models import QuerySet
import logging

from apps.core.exceptions import NotFoundError, ConflictError, ValidationException
from apps.core.interfaces import ICaseService, ServiceLocator
from ..models import CaseNumber, Case

logger = logging.getLogger("apps.cases")


class CaseNumberService:
    """
    案件案号服务

    职责：
    1. 封装案件案号相关的所有业务逻辑
    2. 管理数据库事务
    3. 执行权限检查
    4. 支持依赖注入
    5. 案号规范化处理
    """

    def __init__(self, case_service: Optional[ICaseService] = None):
        """
        初始化服务（依赖注入）

        Args:
            case_service: 案件服务接口（注入）
        """
        self._case_service = case_service

    @property
    def case_service(self) -> ICaseService:
        """延迟加载：优先使用注入实例"""
        if self._case_service is None:
            self._case_service = ServiceLocator.get_case_service()
        return self._case_service

    def list_numbers(
        self,
        case_id: Optional[int] = None,
        user: Optional[Any] = None,
    ) -> QuerySet:
        """
        获取案号列表

        Args:
            case_id: 案件 ID（可选，用于过滤）
            user: 当前用户

        Returns:
            案号查询集
        """
        qs = CaseNumber.objects.select_related("case").order_by("created_at")

        # 应用过滤条件
        if case_id:
            qs = qs.filter(case_id=case_id)

        logger.debug(
            f"获取案号列表",
            extra={
                "action": "list_numbers",
                "case_id": case_id,
                "user_id": getattr(user, "id", None) if user else None,
                "count": qs.count()
            }
        )

        return qs

    def get_number(
        self,
        number_id: int,
        user: Optional[Any] = None,
    ) -> CaseNumber:
        """
        获取单个案号

        Args:
            number_id: 案号 ID
            user: 当前用户

        Returns:
            案号对象

        Raises:
            NotFoundError: 案号不存在
        """
        try:
            case_number = CaseNumber.objects.select_related("case").get(id=number_id)

            logger.debug(
                f"获取案号成功",
                extra={
                    "action": "get_number",
                    "number_id": number_id,
                    "case_id": case_number.case_id,
                    "number": case_number.number,
                    "user_id": getattr(user, "id", None) if user else None
                }
            )

            return case_number
        except CaseNumber.DoesNotExist:
            logger.warning(
                f"案号不存在",
                extra={
                    "action": "get_number",
                    "number_id": number_id,
                    "user_id": getattr(user, "id", None) if user else None
                }
            )
            raise NotFoundError(
                message="案号不存在",
                code="CASE_NUMBER_NOT_FOUND",
                errors={"number_id": f"ID 为 {number_id} 的案号不存在"}
            )

    @transaction.atomic
    def create_number(
        self,
        case_id: int,
        number: str,
        remarks: Optional[str] = None,
        user: Optional[Any] = None,
    ) -> CaseNumber:
        """
        创建案号（自动规范化）

        Args:
            case_id: 案件 ID
            number: 案号
            remarks: 备注（可选）
            user: 当前用户

        Returns:
            创建的案号对象

        Raises:
            NotFoundError: 案件不存在
            ValidationException: 数据验证失败
        """
        # 验证案件是否存在
        try:
            case = Case.objects.get(id=case_id)
        except Case.DoesNotExist:
            logger.warning(
                f"创建案号失败：案件不存在",
                extra={
                    "action": "create_number",
                    "case_id": case_id,
                    "number": number,
                    "user_id": getattr(user, "id", None) if user else None
                }
            )
            raise NotFoundError(
                message="案件不存在",
                code="CASE_NOT_FOUND",
                errors={"case_id": f"ID 为 {case_id} 的案件不存在"}
            )

        # 验证案号不能为空
        if not number or not number.strip():
            raise ValidationException(
                message="案号不能为空",
                code="INVALID_CASE_NUMBER",
                errors={"number": "案号不能为空"}
            )

        # 规范化案号
        normalized_number = self.normalize_case_number(number)

        # 创建案号
        case_number = CaseNumber.objects.create(
            case=case,
            number=normalized_number,
            remarks=remarks
        )

        logger.info(
            f"创建案号成功",
            extra={
                "action": "create_number",
                "number_id": case_number.id,
                "case_id": case_id,
                "original_number": number,
                "normalized_number": normalized_number,
                "user_id": getattr(user, "id", None) if user else None
            }
        )

        return case_number

    @transaction.atomic
    def update_number(
        self,
        number_id: int,
        data: Dict[str, Any],
        user: Optional[Any] = None,
    ) -> CaseNumber:
        """
        更新案号

        Args:
            number_id: 案号 ID
            data: 更新数据
            user: 当前用户

        Returns:
            更新后的案号对象

        Raises:
            NotFoundError: 案号不存在
            ValidationException: 数据验证失败
        """
        try:
            case_number = CaseNumber.objects.select_related("case").get(id=number_id)
        except CaseNumber.DoesNotExist:
            logger.warning(
                f"更新案号失败：案号不存在",
                extra={
                    "action": "update_number",
                    "number_id": number_id,
                    "user_id": getattr(user, "id", None) if user else None
                }
            )
            raise NotFoundError(
                message="案号不存在",
                code="CASE_NUMBER_NOT_FOUND",
                errors={"number_id": f"ID 为 {number_id} 的案号不存在"}
            )

        # 验证案件是否存在（如果更新了 case_id）
        case_id = data.get("case_id")
        if case_id and case_id != case_number.case_id:
            try:
                Case.objects.get(id=case_id)
            except Case.DoesNotExist:
                raise NotFoundError(
                    message="案件不存在",
                    code="CASE_NOT_FOUND",
                    errors={"case_id": f"ID 为 {case_id} 的案件不存在"}
                )

        # 规范化案号（如果更新了 number）
        number = data.get("number")
        if number is not None:
            if not number or not number.strip():
                raise ValidationException(
                    message="案号不能为空",
                    code="INVALID_CASE_NUMBER",
                    errors={"number": "案号不能为空"}
                )
            data["number"] = self.normalize_case_number(number)

        # 更新案号
        original_number = case_number.number
        for key, value in data.items():
            if hasattr(case_number, key):
                setattr(case_number, key, value)

        case_number.save()

        logger.info(
            f"更新案号成功",
            extra={
                "action": "update_number",
                "number_id": number_id,
                "case_id": case_number.case_id,
                "original_number": original_number,
                "new_number": case_number.number,
                "user_id": getattr(user, "id", None) if user else None
            }
        )

        return case_number

    @transaction.atomic
    def delete_number(
        self,
        number_id: int,
        user: Optional[Any] = None,
    ) -> Dict[str, bool]:
        """
        删除案号

        Args:
            number_id: 案号 ID
            user: 当前用户

        Returns:
            {"success": True}

        Raises:
            NotFoundError: 案号不存在
        """
        try:
            case_number = CaseNumber.objects.get(id=number_id)
        except CaseNumber.DoesNotExist:
            logger.warning(
                f"删除案号失败：案号不存在",
                extra={
                    "action": "delete_number",
                    "number_id": number_id,
                    "user_id": getattr(user, "id", None) if user else None
                }
            )
            raise NotFoundError(
                message="案号不存在",
                code="CASE_NUMBER_NOT_FOUND",
                errors={"number_id": f"ID 为 {number_id} 的案号不存在"}
            )

        case_id = case_number.case_id
        number = case_number.number

        case_number.delete()

        logger.info(
            f"删除案号成功",
            extra={
                "action": "delete_number",
                "number_id": number_id,
                "case_id": case_id,
                "number": number,
                "user_id": getattr(user, "id", None) if user else None
            }
        )

        return {"success": True}

    @staticmethod
    def normalize_case_number(number: str) -> str:
        """
        规范化案号：统一括号、删除空格

        处理规则：
        1. 英文括号 () 转中文括号 （）
        2. 六角括号 〔〕 转中文括号 （）
        3. 中括号 [] 转中文括号 （）
        4. 删除所有空格（包括全角空格）

        Args:
            number: 原始案号

        Returns:
            规范化后的案号
        """
        if not number:
            return ""

        # 统一括号：英文、六角、中括号 -> 中文括号
        result = number.replace("(", "（").replace(")", "）")
        result = result.replace("〔", "（").replace("〕", "）")
        result = result.replace("[", "（").replace("]", "）")

        # 删除所有空格（包括全角空格）
        result = result.replace(" ", "").replace("\u3000", "")

        return result