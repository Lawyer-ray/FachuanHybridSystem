"""
对方当事人占位符服务

提供对方当事人信息格式化功能.
"""

import logging
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class OpposingPartyService(BasePlaceholderService):
    """对方当事人服务"""

    name: str = "opposing_party_service"
    display_name: str = "对方当事人服务"
    description: str = "格式化对方当事人名称"
    category: str = "party"
    placeholder_keys: ClassVar = ["对方当事人名称"]

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        生成对方当事人占位符

        Args:
            context_data: 包含 contract 等数据的上下文

        Returns:
            包含对方当事人占位符的字典
        """
        result: dict[str, Any] = {}
        contract = context_data.get("contract")

        if contract:
            # {{对方当事人名称}} - 对方当事人名称,顿号分隔
            opposing_parties = self._get_opposing_parties(contract)
            result["对方当事人名称"] = self.format_opposing_party_names(opposing_parties)

        return result

    def _get_opposing_parties(self, contract: Any) -> list[Any]:
        """
        获取合同中的对方当事人列表

        Args:
            contract: Contract 实例

        Returns:
            对方当事人 Client 实例列表
        """
        try:
            # 使用字符串常量代替直接导入 PartyRole 枚举
            # Requirements: 3.2
            opposing_parties: list[Any] = []
            for cp in contract.contract_parties.all():
                if cp.role == "OPPOSING":
                    opposing_parties.append(cp.client)
            return opposing_parties
        except Exception:
            logger.exception("get_opposing_parties_failed", extra={"contract_id": getattr(contract, "id", None)})
            raise

    def format_opposing_party_names(self, opposing_parties: list[Any]) -> str:
        """
        格式化对方当事人名称(顿号分隔)

        Args:
            opposing_parties: 对方当事人列表

        Returns:
            顿号分隔的对方当事人名称字符串
        """
        if not opposing_parties:
            return ""

        names: list[Any] = []
        for client in opposing_parties:
            if hasattr(client, "name") and client.name:
                names.append(client.name)

        return "、".join(names)
