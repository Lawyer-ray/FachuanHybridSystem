"""
受益人证件号码占位符服务

生成受益人(或委托人)的名称和证件号码信息.
"""

import logging
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class BeneficiaryIdService(BasePlaceholderService):
    """受益人证件号码服务"""

    name: str = "beneficiary_id_service"
    display_name: str = "受益人证件号码服务"
    description: str = "生成受益人(或委托人)的名称和证件号码信息"
    category: str = "contract"
    placeholder_keys: ClassVar = ["受益人_证件号码"]
    placeholder_metadata: ClassVar = {
        "受益人_证件号码": {
            "display_name": "受益人证件号码",
            "description": "受益人的名称和证件号码,格式:XXX（身份证号码：123352342）.如无受益人则使用委托人信息",
            "example_value": "张三（身份证号码：110101199001011234）、李四（身份证号码：110101199002022345）",
        }
    }

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        生成受益人证件号码占位符

        Args:
            context_data: 包含 contract 的上下文字典

        Returns:
            {"受益人_证件号码": "格式化的受益人信息字符串"}
        """
        try:
            contract = context_data.get("contract")
            if not contract:
                logger.warning("合同对象为空")
                return {"受益人_证件号码": ""}

            result = self._format_beneficiary_info(contract)
            return {"受益人_证件号码": result}

        except Exception as e:
            logger.warning(
                "生成受益人证件号码占位符失败: %s", e,
                extra={"contract_id": getattr(context_data.get("contract"), "id", None)},
                exc_info=True,
            )
            return {"受益人_证件号码": ""}

    def _format_beneficiary_info(self, contract: Any) -> str:
        """
        格式化受益人信息

        优先获取身份为"受益人"的我方当事人,如果没有则使用"委托人"

        Args:
            contract: Contract 实例

        Returns:
            格式化的受益人信息字符串
        """
        try:
            # 获取所有合同当事人
            contract_parties = contract.contract_parties.select_related("client").all()

            # 使用字符串常量代替直接导入 PartyRole 枚举
            # Requirements: 3.2
            # 先找受益人
            beneficiaries = [cp.client for cp in contract_parties if cp.role == "BENEFICIARY"]

            # 如果没有受益人,则使用委托人
            if not beneficiaries:
                beneficiaries = [cp.client for cp in contract_parties if cp.role == "PRINCIPAL"]

            if not beneficiaries:
                return ""

            # 格式化每个当事人的信息
            formatted_list: list[Any] = []
            for client in beneficiaries:
                formatted = self._format_single_client(client)
                if formatted:
                    formatted_list.append(formatted)

            # 用顿号分隔
            return "、".join(formatted_list)

        except Exception as e:
            logger.warning("格式化受益人信息失败: %s", e, extra={"contract_id": getattr(contract, "id", None)})
            return ""

    def _format_single_client(self, client: Any) -> str:
        """
        格式化单个当事人的信息

        Args:
            client: Client 实例

        Returns:
            格式化的字符串,如 "张三（身份证号码：110101199001011234）"
        """
        try:
            name = getattr(client, "name", None) or ""
            id_number = getattr(client, "id_number", None) or ""

            if not name:
                return ""

            if id_number:
                return f"{name}（身份证号码：{id_number}）"
            else:
                return name

        except Exception as e:
            logger.warning("格式化单个当事人信息失败: %s", e, extra={"client_id": getattr(client, "id", None)})
            return ""
