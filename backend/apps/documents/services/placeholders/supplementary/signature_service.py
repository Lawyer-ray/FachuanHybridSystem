"""
补充协议签名盖章信息占位符服务

提供补充协议中委托人签名盖章信息的格式化功能.
"""

import logging
from datetime import date
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry
from apps.documents.utils.formatters import format_date_chinese

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class SupplementaryAgreementSignatureService(BasePlaceholderService):
    """补充协议签名盖章信息服务"""

    name: str = "supplementary_agreement_signature_service"
    display_name: str = "补充协议签名盖章信息服务"
    description: str = "生成补充协议中的委托人签名盖章信息"
    category: str = "supplementary_agreement"
    placeholder_keys: ClassVar = [
        "补充协议委托人签名盖章信息",  # 补充协议中的签名区域
    ]

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        生成签名盖章相关占位符

        注意:只有在存在 supplementary_agreement 时才生成占位符,
        避免覆盖合同生成时 PrincipalSignatureService 的结果.

        Args:
            context_data: 包含 contract, supplementary_agreement 等数据的上下文

        Returns:
            包含签名盖章占位符的字典
        """
        result: dict[str, Any] = {}

        contract = context_data.get("contract")
        supplementary_agreement = context_data.get("supplementary_agreement")

        # 只有在存在补充协议时才生成,避免覆盖合同的签名信息
        if contract and supplementary_agreement:
            # 获取委托人列表
            principals = self._get_agreement_principals(supplementary_agreement)

            # 获取指定日期
            specified_date = getattr(contract, "specified_date", None) or date.today()

            # 生成签名盖章信息
            result["补充协议委托人签名盖章信息"] = self.format_signature_info(principals, specified_date)

        return result

    def _get_agreement_principals(self, supplementary_agreement: Any) -> list[Any]:
        """
        获取补充协议中的委托人列表

        Args:
            supplementary_agreement: SupplementaryAgreement 实例

        Returns:
            委托人 Client 实例列表
        """
        try:
            # 使用字符串常量代替直接导入 PartyRole 枚举
            # Requirements: 3.2
            principals: list[Any] = []
            for party in supplementary_agreement.parties.all():
                if party.role == "PRINCIPAL":
                    principals.append(party.client)
            return principals
        except Exception:
            logger.exception(
                "get_supplementary_agreement_principals_failed",
                extra={"supplementary_agreement_id": getattr(supplementary_agreement, "id", None)},
            )
            raise

    def format_signature_info(self, principals: list[Any], specified_date: date) -> str:
        """
        格式化签名盖章信息

        根据委托人数量和类型生成不同格式:
        - 单个自然人:甲方(签名+指模):name\n指定日期
        - 单个法人/非法人组织:甲方(盖章):name\n代表:\n指定日期
        - 多个委托人:甲方一(签名+指模):name\n指定日期\n\n甲方二(盖章):name\n代表:\n指定日期

        Args:
            principals: 委托人列表
            specified_date: 指定日期

        Returns:
            格式化的签名盖章信息字符串
        """
        if not principals:
            return ""

        lines: list[Any] = []
        chinese_numbers = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]

        # 格式化日期
        formatted_date = self._format_date(specified_date)

        if len(principals) == 1:
            # 单个委托人
            client = principals[0]
            signature_format = self._get_signature_format(client)
            lines.append(f"甲方{signature_format}:{client.name}")

            # 根据客户类型决定是否添加"代表:"
            if not self._is_natural_person(client):
                lines.append("代表:")

            lines.append(formatted_date)
        else:
            # 多个委托人
            for i, client in enumerate(principals):
                if i > 0:
                    lines.append("")  # 空行分隔

                number = chinese_numbers[i] if i < len(chinese_numbers) else str(i + 1)
                signature_format = self._get_signature_format(client)
                lines.append(f"甲方{number}{signature_format}:{client.name}")

                # 根据客户类型决定是否添加"代表:"
                if not self._is_natural_person(client):
                    lines.append("代表:")

                lines.append(formatted_date)

        return "\n".join(lines)

    def _is_natural_person(self, client: Any) -> Any:
        """
        判断客户是否为自然人

        通过 wiring 获取 client_service,避免跨模块直接导入 Model

        Args:
            client: Client 实例

        Returns:
            是否为自然人

        Requirements: 1.6
        """
        try:
            from apps.documents.services.wiring import get_client_service

            client_service = get_client_service()
            return client_service.is_natural_person_internal(client.id)
        except Exception as e:
            logger.warning("判断客户类型失败: %s", e, extra={"client_id": getattr(client, "id", None)})
            # 默认认为是法人(更安全的选择,会包含"代表:")
            return False

    def _format_date(self, date_obj: date) -> str:
        """
        格式化日期为"YYYY年MM月DD日"格式(月和日补零)

        Args:
            date_obj: 日期对象

        Returns:
            格式化的日期字符串,如 2026年01月01日
        """
        return format_date_chinese(date_obj)

    def _get_signature_format(self, client: Any) -> str:
        """
        根据客户类型获取签名格式

        Args:
            client: Client 实例

        Returns:
            签名格式字符串:自然人返回"(签名+指模)",非自然人返回"(盖章)"
        """
        if self._is_natural_person(client):
            return "(签名+指模)"
        else:
            return "(盖章)"
