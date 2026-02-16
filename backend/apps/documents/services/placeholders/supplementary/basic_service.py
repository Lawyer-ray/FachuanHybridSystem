"""
补充协议基础信息占位符服务

提供补充协议的基础信息占位符,包括补充协议名称和年份.
"""

import logging
from datetime import date
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class SupplementaryAgreementBasicService(BasePlaceholderService):
    """补充协议基础信息服务"""

    name: str = "supplementary_agreement_basic_service"
    display_name: str = "补充协议基础信息服务"
    description: str = "生成补充协议中的基础信息占位符"
    category: str = "supplementary_agreement"
    placeholder_keys: ClassVar = ["补充协议名称", "年份", "补充协议份数"]

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        生成基础信息占位符

        Args:
            context_data: 包含 supplementary_agreement 等数据的上下文

        Returns:
            包含基础信息占位符的字典
        """
        result: dict[str, Any] = {}

        # 获取补充协议实例
        supplementary_agreement = context_data.get("supplementary_agreement")

        if supplementary_agreement:
            # {{补充协议名称}} - 使用补充协议的名称
            if hasattr(supplementary_agreement, "name") and supplementary_agreement.name:
                result["补充协议名称"] = supplementary_agreement.name
            else:
                result["补充协议名称"] = ""
        else:
            result["补充协议名称"] = ""

        # {{年份}} - 获取当前年份
        result["年份"] = self.get_current_year()

        # {{补充协议份数}} - 补充协议份数(委托人数量+2)
        if supplementary_agreement:
            result["补充协议份数"] = self.calculate_copies(supplementary_agreement)
        else:
            result["补充协议份数"] = 2

        return result

    def calculate_copies(self, supplementary_agreement: Any) -> int:
        """
        计算补充协议份数(委托人数量+2)

        Args:
            supplementary_agreement: SupplementaryAgreement 实例

        Returns:
            补充协议份数
        """
        try:
            # 使用字符串常量代替直接导入 PartyRole 枚举
            # Requirements: 3.2
            principal_count = 0
            for party in supplementary_agreement.parties.all():
                if party.role == "PRINCIPAL":
                    principal_count += 1
            return principal_count + 2
        except Exception as e:
            logger.warning(f"计算补充协议份数失败: {e}")
            return 2

    def get_current_year(self) -> str:
        """
        获取当前年份

        Returns:
            当前年份的字符串表示
        """
        try:
            current_date = date.today()
            return str(current_date.year)
        except Exception as e:
            logger.warning(f"获取当前年份失败: {e}")
            return ""
