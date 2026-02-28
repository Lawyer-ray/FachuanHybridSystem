"""
文件名生成服务

Requirements: 1.1, 1.2, 1.3, 1.4
"""

from django.utils.translation import gettext_lazy as _
from django.utils import timezone
import logging

from apps.documents.services.infrastructure.wiring import get_case_service

logger = logging.getLogger(__name__)


class FilenameService:
    """文件名生成服务"""

    def _format_date(self) -> str:
        """
        格式化日期为 YYYYMMDD

        Returns:
            str: 格式化后的日期字符串

        Requirements: 1.4
        """
        return timezone.now().strftime("%Y%m%d")

    def generate_complaint_filename(self, case_id: int) -> str:
        """
        生成起诉状文件名

        Args:
            case_id: 案件 ID

        Returns:
            str: 起诉状文件名

        Requirements: 1.1, 1.3, 8.3
        """

        # 获取案件服务
        case_service = get_case_service()
        case = case_service.get_case_by_id_internal(case_id)

        if not case:
            logger.error("案件不存在: case_id=%s", case_id)
            raise NotFoundError(message=_("案件不存在"), code="CASE_NOT_FOUND", errors={"case_id": case_id})

        # 获取案件名称(直接使用 case.name)
        case_name = case.name if case.name else "未命名案件"

        # 获取日期
        date_str = self._format_date()

        # 生成文件名:起诉状(案件名称)V1_日期.docx
        filename = f"起诉状（{case_name}）V1_{date_str}.docx"

        logger.info("生成起诉状文件名: %s", filename)

        return filename

    def generate_defense_filename(self, case_id: int) -> str:
        """
        生成答辩状文件名

        Args:
            case_id: 案件 ID

        Returns:
            str: 答辩状文件名

        Requirements: 1.2, 1.3, 8.3
        """

        # 获取案件服务
        case_service = get_case_service()
        case = case_service.get_case_by_id_internal(case_id)

        if not case:
            logger.error("案件不存在: case_id=%s", case_id)
            raise NotFoundError(message=_("案件不存在"), code="CASE_NOT_FOUND", errors={"case_id": case_id})

        # 获取案件名称(直接使用 case.name)
        case_name = case.name if case.name else "未命名案件"

        # 获取日期
        date_str = self._format_date()

        # 生成文件名:答辩状(案件名称)V1_日期.docx
        filename = f"答辩状（{case_name}）V1_{date_str}.docx"

        logger.info("生成答辩状文件名: %s", filename)

        return filename
