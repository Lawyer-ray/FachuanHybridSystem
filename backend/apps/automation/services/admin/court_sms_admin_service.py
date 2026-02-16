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


# 样式配置:定义每个样式的模板和标题
SMS_STYLE_CONFIG: dict[int, dict[str, str]] = {
    2: {"template": "admin/automation/courtsms/add2.html", "title": "📱 添加法院短信"},
    3: {"template": "admin/automation/courtsms/add3.html", "title": "添加法院短信"},
    4: {"template": "admin/automation/courtsms/add4.html", "title": "法院短信终端"},
    5: {"template": "admin/automation/courtsms/add5.html", "title": "法院短信"},
    6: {"template": "admin/automation/courtsms/add6.html", "title": "THE COURT SMS GAZETTE"},
    7: {"template": "admin/automation/courtsms/add7.html", "title": "NEON SMS"},
    8: {"template": "admin/automation/courtsms/add8.html", "title": "添加短信"},
    9: {"template": "admin/automation/courtsms/add9.html", "title": "新建短信"},
    10: {"template": "admin/automation/courtsms/add10.html", "title": "PIXEL SMS"},
    11: {"template": "admin/automation/courtsms/add11.html", "title": "STEAMWORK TELEGRAPH"},
    12: {"template": "admin/automation/courtsms/add12.html", "title": "SPACE COMMAND"},
    13: {"template": "admin/automation/courtsms/add13.html", "title": "法院来函"},
    14: {"template": "admin/automation/courtsms/add14.html", "title": "新建短信"},
    15: {"template": "admin/automation/courtsms/add15.html", "title": "添加短信"},
    16: {"template": "admin/automation/courtsms/add16.html", "title": "MEMPHIS SMS"},
    17: {"template": "admin/automation/courtsms/add17.html", "title": "添加短信"},
    18: {"template": "admin/automation/courtsms/add18.html", "title": "POW! SMS!"},
    19: {"template": "admin/automation/courtsms/add19.html", "title": "🎄 Holiday SMS"},
    20: {"template": "admin/automation/courtsms/add20.html", "title": "OCEAN SMS"},
    21: {"template": "admin/automation/courtsms/add21.html", "title": "森林信笺"},
    22: {"template": "admin/automation/courtsms/add22.html", "title": "ART DECO SMS"},
    23: {"template": "admin/automation/courtsms/add23.html", "title": "BRUTAL SMS"},
    24: {"template": "admin/automation/courtsms/add24.html", "title": "ＳＭＳ　ＷＡＶＥ"},
    25: {"template": "admin/automation/courtsms/add25.html", "title": "BAUHAUS SMS"},
    26: {"template": "admin/automation/courtsms/add26.html", "title": "GOTHIC SMS"},
    27: {"template": "admin/automation/courtsms/add27.html", "title": "✿ 可爱短信 ✿"},
    28: {"template": "admin/automation/courtsms/add28.html", "title": "GRUNGE SMS"},
    29: {"template": "admin/automation/courtsms/add29.html", "title": "SYNTHWAVE SMS"},
    30: {"template": "admin/automation/courtsms/add30.html", "title": "折纸信笺"},
    31: {"template": "admin/automation/courtsms/add31.html", "title": "黑板短信"},
    32: {"template": "admin/automation/courtsms/add32.html", "title": "青花函笺"},
    33: {"template": "admin/automation/courtsms/add33.html", "title": "竹简函牍"},
    34: {"template": "admin/automation/courtsms/add34.html", "title": "御用函笺"},
    35: {"template": "admin/automation/courtsms/add35.html", "title": "山水函笺"},
    36: {"template": "admin/automation/courtsms/add36.html", "title": "书房函笺"},
    37: {"template": "admin/automation/courtsms/add37.html", "title": "敦煌函笺"},
    38: {"template": "admin/automation/courtsms/add38.html", "title": "茶禅函笺"},
    39: {"template": "admin/automation/courtsms/add39.html", "title": "四君子函笺"},
    40: {"template": "admin/automation/courtsms/add40.html", "title": "园林函笺"},
    41: {"template": "admin/automation/courtsms/add41.html", "title": "金石函笺"},
}

# 默认样式ID
DEFAULT_STYLE_ID = 13
