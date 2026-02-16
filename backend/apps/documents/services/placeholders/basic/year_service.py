"""
年份占位符服务

提供当前系统年份.
"""

import logging
from datetime import date
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class YearPlaceholderService(BasePlaceholderService):
    """年份服务"""

    name: str = "year_service"
    display_name: str = "年份服务"
    description: str = "返回当前系统年份"
    category: str = "basic"
    placeholder_keys: ClassVar = ["年份"]

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        生成年份占位符

        Args:
            context_data: 上下文数据(此服务不依赖具体数据)

        Returns:
            包含年份占位符的字典
        """
        result: dict[str, Any] = {}

        # {{年份}} - 当前系统年份
        result["年份"] = str(date.today().year)

        return result
