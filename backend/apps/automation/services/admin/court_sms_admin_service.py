"""
法院短信 Admin Service
负责处理法院短信的复杂管理逻辑
"""

import logging
from typing import Any, Optional

from django.utils import timezone

from apps.automation.models import CourtSMS
from apps.core.exceptions import NotFoundError


class CourtSMSAdminService:
    """
    法院短信管理服务

    负责处理Admin层的复杂业务逻辑:
    - 获取短信记录
    - 提交短信
    - 指定案件
    - 重试处理
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def get_sms_by_id(self, sms_id: int) -> CourtSMS:
        """
        根据ID获取短信记录

        Args:
            sms_id: 短信ID

        Returns:
            CourtSMS: 短信记录

        Raises:
            NotFoundError: 短信不存在
        """
        try:
            return CourtSMS.objects.get(id=sms_id)
        except CourtSMS.DoesNotExist:
            raise NotFoundError(
                message=f"短信记录不存在: ID={sms_id}", code="SMS_NOT_FOUND", errors={"sms_id": sms_id}
            ) from None

    def get_recent_sms(self, limit: int = 5) -> list[Any]:
        """
        获取最近的短信记录

        Args:
            limit: 返回数量限制

        Returns:
            list: 短信记录列表
        """
        return list(CourtSMS.objects.order_by("-created_at")[:limit])

    def submit_sms(self, content: str, received_at: Any | None = None) -> Any:
        """
        提交短信

        Args:
            content: 短信内容
            received_at: 收到时间(可选)

        Returns:
            CourtSMS: 创建的短信记录
        """
        from apps.automation.services.wiring import get_court_sms_service

        service = get_court_sms_service()
        if received_at is None:
            received_at = timezone.now()
        return service.submit_sms(content, received_at)

    def assign_case(self, sms_id: int, case_id: int) -> None:
        """
        为短信指定案件

        Args:
            sms_id: 短信ID
            case_id: 案件ID
        """
        from apps.automation.services.wiring import get_court_sms_service

        service = get_court_sms_service()
        service.assign_case(sms_id, case_id)

    def retry_processing(self, sms_id: int) -> None:
        """
        重试处理短信

        Args:
            sms_id: 短信ID
        """
        from apps.automation.services.wiring import get_court_sms_service

        service = get_court_sms_service()
        service.retry_processing(sms_id)
