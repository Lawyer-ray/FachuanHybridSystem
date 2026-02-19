"""
补充协议委托人信息占位符服务

提供补充协议中委托人信息格式化和主体信息条款生成功能.
"""

import logging
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class SupplementaryAgreementPrincipalService(BasePlaceholderService):
    """补充协议委托人信息服务"""

    name: str = "supplementary_agreement_principal_service"
    display_name: str = "补充协议委托人信息服务"
    description: str = "生成补充协议中的委托人信息和主体信息条款"
    category: str = "supplementary_agreement"
    placeholder_keys: ClassVar = [
        "补充协议委托人信息",  # 补充协议中的委托人详细信息
        "补充协议委托人主体信息条款",  # 新增委托人条款或空
        "补充协议委托人数量",  # 补充协议中的委托人数量
    ]

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        生成委托人相关占位符

        Args:
            context_data: 包含 contract, supplementary_agreement 等数据的上下文

        Returns:
            包含委托人占位符的字典
        """
        result: dict[str, Any] = {}

        contract = context_data.get("contract")
        supplementary_agreement = context_data.get("supplementary_agreement")

        if contract and supplementary_agreement:
            # 获取委托人列表
            agreement_principals = self._get_agreement_principals(supplementary_agreement)
            contract_principals = self._get_contract_principals(contract)

            # 生成委托人信息
            result["补充协议委托人信息"] = self.format_principal_info(agreement_principals)

            # 生成委托人数量
            result["补充协议委托人数量"] = len(agreement_principals)

            # 生成委托人主体信息条款
            existing_principals, new_principals = self._find_new_principals(agreement_principals, contract_principals)
            result["补充协议委托人主体信息条款"] = self.format_principal_clause(existing_principals, new_principals)

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

    def _get_contract_principals(self, contract: Any) -> list[Any]:
        """
        获取原合同中的委托人列表

        Args:
            contract: Contract 实例

        Returns:
            委托人 Client 实例列表
        """
        try:
            principals: list[Any] = []
            for cp in contract.contract_parties.all():
                if cp.role == "PRINCIPAL":
                    principals.append(cp.client)
            return principals
        except Exception:
            logger.exception("get_contract_principals_failed", extra={"contract_id": getattr(contract, "id", None)})
            raise

    def _find_new_principals(
        self, agreement_principals: list[Any], contract_principals: list[Any]
    ) -> tuple[list[Any], list[Any]]:
        """
        找出新增的委托人

        Args:
            agreement_principals: 补充协议中的委托人列表
            contract_principals: 原合同中的委托人列表

        Returns:
            Tuple[重复的委托人列表, 新增的委托人列表]
        """
        # 获取原合同委托人的 ID 集合
        contract_principal_ids = {client.id for client in contract_principals if hasattr(client, "id")}

        existing_principals: list[Any] = []
        new_principals: list[Any] = []

        for client in agreement_principals:
            if hasattr(client, "id") and client.id in contract_principal_ids:
                existing_principals.append(client)
            else:
                new_principals.append(client)

        return existing_principals, new_principals

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
            lines.append(f"甲方:{client.name}")
            lines.extend(self._format_client_details(client))
        else:
            # 多个委托人
            for i, client in enumerate(principals):
                number = chinese_numbers[i] if i < len(chinese_numbers) else str(i + 1)
                lines.append(f"甲方{number}:{client.name}")
                lines.extend(self._format_client_details(client))
                if i < len(principals) - 1:
                    lines.append("")  # 空行分隔

        return "\n".join(lines)

    def format_principal_clause(self, existing_principals: list[Any], new_principals: list[Any]) -> str:
        """
        生成委托人主体信息条款

        如果没有新增委托人,返回空字符串(删除整段)
        如果有新增委托人,生成动态条款

        Args:
            existing_principals: 重复的委托人列表
            new_principals: 新增的委托人列表

        Returns:
            委托人主体信息条款或空字符串
        """
        if not new_principals:
            # 没有新增委托人,返回空字符串(删除整段)
            return ""

        # 生成新增委托人条款
        chinese_numbers = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]

        # 构建新增委托人编号
        existing_count = len(existing_principals)
        new_principal_labels: list[Any] = []

        for i, _ in enumerate(new_principals):
            index = existing_count + i
            if index < len(chinese_numbers):
                number = chinese_numbers[index]
            else:
                number = str(index + 1)
            new_principal_labels.append(f"甲方{number}")

        # 构建原有委托人编号
        existing_labels: list[Any] = []
        for i in range(existing_count):
            if i < len(chinese_numbers):
                number = chinese_numbers[i]
            else:
                number = str(i + 1)
            existing_labels.append(f"甲方{number}")

        # 生成条款文本
        new_parties_text = "、".join(new_principal_labels)
        existing_parties_text = "、".join(existing_labels) if existing_labels else ""

        clause = (
            f"为保障合同履行的完整性与一致性,维护各方合法权益,"
            f"现新增{new_parties_text}作为本补充协议及原合同项下的共同甲方."
        )

        if existing_parties_text:
            clause += f"新增甲方与{existing_parties_text}共同享有原合同及本补充协议约定的全部权利,并承担相应的义务."
        else:
            clause += "新增甲方享有原合同及本补充协议约定的全部权利,并承担相应的义务."

        return clause

    def _format_client_details(self, client: Any) -> list[str]:
        """
        根据客户类型格式化详细信息

        Args:
            client: Client 实例

        Returns:
            格式化的详细信息行列表
        """
        lines: list[Any] = []

        try:
            # 使用 core.enums 中的枚举类型
            from apps.core.enums import ClientType  # type: ignore[attr-defined]

            if hasattr(client, "client_type"):
                if client.client_type == ClientType.NATURAL:
                    # 自然人格式
                    lines.append(f"身份证号码:{getattr(client, 'id_number', '') or ''}")
                else:
                    # 法人或非法人组织格式
                    lines.append(f"统一社会信用代码:{getattr(client, 'id_number', '') or ''}")
                    lines.append(f"法定代表人:{getattr(client, 'legal_representative', '') or ''}")

            lines.append(f"地址:{getattr(client, 'address', '') or ''}")
            lines.append(f"电话:{getattr(client, 'phone', '') or ''}")

        except Exception as e:
            logger.warning(f"格式化客户详情失败: {e}", extra={"client_id": getattr(client, "id", None)})
            # 提供基本格式
            lines.append(f"地址:{getattr(client, 'address', '') or ''}")
            lines.append(f"电话:{getattr(client, 'phone', '') or ''}")

        return lines
