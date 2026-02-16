"""
合同份数占位符服务

计算合同份数(委托人数量+2).
"""

import logging
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class ContractCopiesService(BasePlaceholderService):
    """合同份数服务"""

    name: str = "contract_copies_service"
    display_name: str = "合同份数服务"
    description: str = "计算合同份数(委托人数量+2)"
    category: str = "contract"
    placeholder_keys: ClassVar = ["合同份数"]

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        生成合同份数占位符

        Args:
            context_data: 包含 contract 等数据的上下文

        Returns:
            包含合同份数占位符的字典
        """
        result: dict[str, Any] = {}
        contract = context_data.get("contract")

        if contract:
            # {{合同份数}} - 合同份数(委托人数量+2)
            result["合同份数"] = self.calculate_contract_copies(contract)

        return result

    def calculate_contract_copies(self, contract: Any) -> int:
        """
        计算合同份数

        Args:
            contract: Contract 实例

        Returns:
            合同份数(委托人数量+2)
        """
        try:
            principal_count = self._get_principal_count(contract)
            return principal_count + 2
        except Exception as e:
            logger.warning(f"计算合同份数失败: {e}", extra={"contract_id": getattr(contract, "id", None)})
            return 2  # 默认返回2份

    def _get_principal_count(self, contract: Any) -> int:
        """
        获取委托人数量

        Args:
            contract: Contract 实例

        Returns:
            委托人数量
        """
        try:
            # 使用字符串常量代替直接导入 PartyRole 枚举
            # Requirements: 3.2
            count = 0
            for cp in contract.contract_parties.all():
                if cp.role == "PRINCIPAL":
                    count += 1
            return count
        except Exception as e:
            logger.warning(f"获取委托人数量失败: {e}", extra={"contract_id": getattr(contract, "id", None)})
            return 0
