"""
财产保全申请书保全金额服务

从案件的 preservation_amount 字段获取财产保全金额.

Requirements: 5.1, 5.2
"""

import logging
from typing import Any, ClassVar

from apps.documents.services.placeholders import BasePlaceholderService, PlaceholderRegistry

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class PreservationAmountService(BasePlaceholderService):
    """财产保全申请书保全金额服务"""

    name: str = "preservation_amount_service"
    display_name: str = "财产保全申请书保全金额服务"
    description: str = "获取案件的财产保全金额"
    category: str = "litigation"
    placeholder_keys: ClassVar = ["财产保全申请书保全金额"]
    placeholder_metadata: ClassVar = {
        "财产保全申请书保全金额": {
            "display_name": "财产保全申请书保全金额",
            "description": "案件的财产保全金额",
            "example_value": "100000.00",
        }
    }

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        生成占位符值

        Args:
            context_data: 包含 case 对象的上下文

        Returns:
            包含占位符键值对的字典
        """
        case = context_data.get("case")
        if not case:
            return {"财产保全申请书保全金额": ""}

        amount = getattr(case, "preservation_amount", None)
        if amount is not None:
            # 格式化金额,去除尾部的零
            amount_str = str(amount)
            if "." in amount_str:
                amount_str = amount_str.rstrip("0").rstrip(".")
            return {"财产保全申请书保全金额": amount_str}

        return {"财产保全申请书保全金额": ""}
