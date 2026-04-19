"""
归档合同类型占位符服务

将合同类型映射为归档用的简化分类:
- 民商事/行政/劳动仲裁/商事仲裁 → 诉讼仲裁
- 刑事 → 刑事诉讼
- 专项服务 → 非诉
- 常法顾问 → 常年法律顾问
"""

import logging
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry

logger = logging.getLogger(__name__)

# 合同类型 → 归档合同类型 映射表
_ARCHIVE_TYPE_MAPPING: dict[str, str] = {
    "civil": "诉讼仲裁",
    "administrative": "诉讼仲裁",
    "labor": "诉讼仲裁",
    "intl": "诉讼仲裁",
    "criminal": "刑事诉讼",
    "special": "非诉",
    "advisor": "常年法律顾问",
}


@PlaceholderRegistry.register
class ArchiveContractTypeService(BasePlaceholderService):
    """归档合同类型服务"""

    name: str = "archive_contract_type_service"
    display_name: str = "归档合同类型服务"
    description: str = "根据合同类型映射为归档分类:诉讼仲裁/刑事诉讼/非诉/常年法律顾问"
    category: str = "contract"
    placeholder_keys: ClassVar = ["归档合同类型"]
    placeholder_metadata: ClassVar[dict[str, dict[str, Any]]] = {
        "归档合同类型": {
            "display_name": "归档合同类型",
            "description": "根据合同类型映射的归档分类",
            "example_value": "诉讼仲裁",
        }
    }

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        生成归档合同类型占位符

        Args:
            context_data: 包含 contract 等数据的上下文

        Returns:
            包含归档合同类型占位符的字典
        """
        result: dict[str, Any] = {}

        contract = context_data.get("contract")
        if contract:
            case_type = getattr(contract, "case_type", "")
            result["归档合同类型"] = self._map_archive_type(case_type)

        return result

    @staticmethod
    def _map_archive_type(case_type: str) -> str:
        """
        将合同类型映射为归档合同类型

        Args:
            case_type: 合同类型代码(如 civil, criminal 等)

        Returns:
            归档合同类型中文名称
        """
        return _ARCHIVE_TYPE_MAPPING.get(case_type, "")
