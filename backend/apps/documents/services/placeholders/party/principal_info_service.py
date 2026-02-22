"""
委托人信息占位符服务

提供委托人信息格式化功能.
"""

import logging
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class PrincipalInfoService(BasePlaceholderService):
    """委托人信息服务"""

    name: str = "principal_info_service"
    display_name: str = "委托人信息服务"
    description: str = "格式化委托人信息,区分自然人和法人"
    category: str = "party"
    placeholder_keys: ClassVar = ["委托人名称", "委托人信息", "委托人数量"]

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        生成委托人占位符

        Args:
            context_data: 包含 contract 等数据的上下文

        Returns:
            包含委托人占位符的字典
        """
        result: dict[str, Any] = {}
        contract = context_data.get("contract")

        if contract:
            principals = self._get_principals(contract)

            # {{委托人名称}} - 委托人名称,顿号分隔
            result["委托人名称"] = self.format_principal_names(principals)

            # {{委托人信息}} - 格式化的委托人信息
            result["委托人信息"] = self.format_principal_info(principals)

            # {{委托人数量}} - 委托人数量
            result["委托人数量"] = len(principals)

        return result

    def _get_principals(self, contract: Any) -> list[Any]:
        """
        获取合同中的委托人列表

        Args:
            contract: Contract 实例

        Returns:
            委托人 Client 实例列表
        """
        try:
            # 使用字符串常量代替直接导入 PartyRole 枚举
            # Requirements: 3.2
            principals: list[Any] = []
            for cp in contract.contract_parties.all():
                if cp.role == "PRINCIPAL":
                    principals.append(cp.client)
            return principals
        except Exception:
            logger.exception("get_principals_failed", extra={"contract_id": getattr(contract, "id", None)})
            raise

    def format_principal_names(self, principals: list[Any]) -> str:
        """
        格式化委托人名称(顿号分隔)

        Args:
            principals: 委托人列表

        Returns:
            顿号分隔的委托人名称字符串
        """
        if not principals:
            return ""

        names: list[Any] = []
        for client in principals:
            if hasattr(client, "name") and client.name:
                names.append(client.name)

        return "、".join(names)

    def format_principal_info(self, principals: list[Any]) -> str:
        """
        格式化委托人信息

        Args:
            principals: 委托人列表

        Returns:
            格式化的委托人信息字符串
        """
        if not principals:
            return ""

        lines: list[Any] = []
        chinese_numbers = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]

        if len(principals) == 1:
            # 单个委托人
            client = principals[0]
            lines.append(f"甲方：{client.name}")
            lines.extend(self._format_client_details(client))
        else:
            # 多个委托人
            for i, client in enumerate(principals):
                number = chinese_numbers[i] if i < len(chinese_numbers) else str(i + 1)
                lines.append(f"甲方{number}：{client.name}")
                lines.extend(self._format_client_details(client))
                if i < len(principals) - 1:
                    lines.append("")  # 空行分隔

        return "\n".join(lines)

    def _format_client_details(self, client: Any) -> list[str]:
        """
        根据客户类型格式化详细信息

        通过 wiring 获取 client_service,避免跨模块直接导入 Model

        Args:
            client: Client 实例

        Returns:
            格式化的详细信息行列表

        Requirements: 3.3
        """
        lines: list[Any] = []

        try:
            from apps.documents.services.wiring import get_client_service

            client_service = get_client_service()

            if hasattr(client, "id"):
                is_natural = client_service.is_natural_person_internal(client.id)
                if is_natural:
                    # 自然人格式
                    lines.append(f"身份证号码：{getattr(client, 'id_number', '') or ''}")
                else:
                    # 法人或非法人组织格式
                    lines.append(f"统一社会信用代码：{getattr(client, 'id_number', '') or ''}")
                    lines.append(f"法定代表人：{getattr(client, 'legal_representative', '') or ''}")

            lines.append(f"地址：{getattr(client, 'address', '') or ''}")
            lines.append(f"电话：{getattr(client, 'phone', '') or ''}")

        except Exception as e:
            logger.warning(f"格式化客户详情失败: {e}", extra={"client_id": getattr(client, "id", None)})
            # 提供基本格式
            lines.append(f"地址：{getattr(client, 'address', '') or ''}")
            lines.append(f"电话：{getattr(client, 'phone', '') or ''}")

        return lines
