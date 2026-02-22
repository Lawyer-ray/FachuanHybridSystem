"""
日期占位符服务

提供日期格式化功能,将日期转换为中文格式.
"""

import logging
from datetime import date
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class DatePlaceholderService(BasePlaceholderService):
    """日期格式化服务"""

    name: str = "date_service"
    display_name: str = "日期格式化服务"
    description: str = "将日期转换为中文格式(YYYY年MM月DD日)"
    category: str = "basic"
    placeholder_keys: ClassVar = ["指定日期", "签约日期", "开始日期", "结束日期"]

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        生成日期占位符

        Args:
            context_data: 包含 contract 等数据的上下文

        Returns:
            包含日期占位符的字典
        """
        result: dict[str, Any] = {}
        case = context_data.get("case")
        contract = context_data.get("contract")

        if case:
            if hasattr(case, "specified_date") and case.specified_date:
                result["指定日期"] = self.format_chinese_date(case.specified_date)
            else:
                result["指定日期"] = ""
            return result

        if contract:
            # {{指定日期}} - 格式化为中文日期格式
            if hasattr(contract, "specified_date") and contract.specified_date:
                result["指定日期"] = self.format_chinese_date(contract.specified_date)
            else:
                result["指定日期"] = ""

            # {{开始日期}} - 合同开始日期
            if hasattr(contract, "start_date") and contract.start_date:
                result["开始日期"] = self.format_chinese_date(contract.start_date)
            else:
                result["开始日期"] = ""

            # {{结束日期}} - 合同结束日期
            if hasattr(contract, "end_date") and contract.end_date:
                result["结束日期"] = self.format_chinese_date(contract.end_date)
            else:
                result["结束日期"] = ""

        return result

    def format_chinese_date(self, d: date) -> str:
        """
        格式化为中文日期

        Args:
            d: 日期对象

        Returns:
            中文格式的日期字符串,如 "2026年01月01日"
        """
        if not d:
            return ""

        try:
            return f"{d.year}年{d.month:02d}月{d.day:02d}日"
        except (AttributeError, ValueError) as e:
            logger.warning("日期格式化失败: %s", e, extra={"date": d})
            return ""
