"""
委托人签名占位符服务

提供委托人签名盖章信息格式化功能.
"""

import logging
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class PrincipalSignatureService(BasePlaceholderService):
    """委托人签名服务"""

    name: str = "principal_signature_service"
    display_name: str = "委托人签名服务"
    description: str = "生成委托人签名盖章信息"
    category: str = "party"
    placeholder_keys: ClassVar = ["委托人签名盖章信息"]

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        生成委托人签名占位符

        Args:
            context_data: 包含 contract 等数据的上下文

        Returns:
            包含委托人签名占位符的字典
        """
        result: dict[str, Any] = {}
        contract = context_data.get("contract")

        if contract:
            # {{委托人签名盖章信息}} - 委托人签名盖章信息
            result["委托人签名盖章信息"] = self.format_principal_signature_info(contract)

        return result

    def format_principal_signature_info(self, contract: Any) -> str:
        """
        格式化委托人签名盖章信息

        根据委托人类型生成不同格式:
        - 自然人:甲方（签名+指模）:姓名
        - 非自然人:甲方（盖章）:公司名称

        Args:
            contract: Contract 实例

        Returns:
            格式化的委托人签名盖章信息字符串
        """
        try:
            # 使用字符串常量代替直接导入 PartyRole 枚举
            # Requirements: 3.2
            # 提取合同中的委托人信息
            principals: list[Any] = []
            for cp in contract.contract_parties.all():
                if cp.role == "PRINCIPAL":
                    principals.append(cp.client)

            if not principals:
                return ""

            lines: list[Any] = []
            specified_date = ""
            if hasattr(contract, "specified_date") and contract.specified_date:
                specified_date = (
                    f"{contract.specified_date.year}年"
                    f"{contract.specified_date.month:02d}月"
                    f"{contract.specified_date.day:02d}日"
                )

            if len(principals) == 1:
                # 单个委托人
                client = principals[0]
                signature_format = self._get_signature_format(client)
                lines.append(f"甲方{signature_format}：{client.name}")

                # 非自然人需要代表行
                if not self._is_natural_person(client):
                    lines.append("代表：")

                lines.append(specified_date)
            else:
                # 多个委托人
                chinese_numbers = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
                client_sections: list[Any] = []

                for i, client in enumerate(principals):
                    number = chinese_numbers[i] if i < len(chinese_numbers) else str(i + 1)
                    client_lines: list[Any] = []

                    signature_format = self._get_signature_format(client)
                    client_lines.append(f"甲方{number}{signature_format}：{client.name}")

                    # 非自然人需要代表行
                    if not self._is_natural_person(client):
                        client_lines.append("代表：")

                    client_lines.append(specified_date)
                    client_sections.append("\n".join(client_lines))

                # 多个委托人之间用两个硬换行分隔
                return "\n\n".join(client_sections)

            return "\n".join(lines)

        except Exception as e:
            logger.warning("格式化委托人签名信息失败: %s", e, extra={"contract_id": getattr(contract, "id", None)})
            return ""

    def _is_natural_person(self, client: Any) -> Any:
        """
        判断客户是否为自然人

        通过 wiring 获取 client_service,避免跨模块直接导入 Model

        Args:
            client: Client 实例

        Returns:
            是否为自然人

        Requirements: 3.3
        """
        try:
            from apps.documents.services.infrastructure.wiring import get_client_service

            client_service = get_client_service()
            return client_service.is_natural_person_internal(client.id)
        except Exception:
            logger.exception("操作失败")

            # 如果无法判断,默认为自然人
            return True

    def _get_signature_format(self, client: Any) -> str:
        """
        根据客户类型获取签名格式

        Args:
            client: Client 实例

        Returns:
            签名格式字符串:自然人返回"（签名+指模）",非自然人返回"（盖章）"
        """
        if self._is_natural_person(client):
            return "（签名+指模）"
        else:
            return "（盖章）"
