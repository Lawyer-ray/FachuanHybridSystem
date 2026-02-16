"""
顾问合同收费条款占位符服务

根据收费模式生成顾问合同收费条款.
支持固定收费和自定义收费两种模式.
"""

import logging
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class AdvisorFeeTermsService(BasePlaceholderService):
    """顾问合同收费条款服务"""

    name: str = "advisor_fee_terms_service"
    display_name: str = "顾问合同收费条款服务"
    description: str = "根据收费模式生成顾问合同收费条款(支持固定收费和自定义收费)"
    category: str = "contract"
    placeholder_keys: ClassVar = ["顾问合同收费条款"]

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        生成顾问合同收费条款占位符

        Args:
            context_data: 包含 contract 等数据的上下文

        Returns:
            包含顾问合同收费条款占位符的字典
        """
        result: dict[str, Any] = {}
        contract = context_data.get("contract")

        if contract:
            # {{顾问合同收费条款}} - 根据收费模式生成收费条款
            result["顾问合同收费条款"] = self.generate_advisor_fee_terms(contract)

        return result

    def generate_advisor_fee_terms(self, contract: Any) -> str:
        """
        根据收费模式格式化顾问合同收费条款

        只处理固定收费和自定义收费两种模式

        Args:
            contract: Contract 实例

        Returns:
            格式化的收费条款字符串
        """
        try:
            fee_mode = getattr(contract, "fee_mode", None)

            # 使用字符串常量代替直接导入 FeeMode 枚举
            # Requirements: 3.2
            if fee_mode == "FIXED":
                return self._generate_fixed_fee_terms(contract)
            elif fee_mode == "CUSTOM":
                return self._generate_custom_fee_terms(contract)
            else:
                # 顾问合同只支持固定收费和自定义收费
                return "收费条款待定."

        except Exception as e:
            logger.warning(f"生成顾问合同收费条款失败: {e}", extra={"contract_id": getattr(contract, "id", None)})
            return "收费条款待定."

    def _generate_fixed_fee_terms(self, contract: Any) -> str:
        """
        生成固定收费条款

        格式:甲方向乙方支付法律顾问费¥XXX元(大写:人民币YYY)
        """
        fixed_amount = getattr(contract, "fixed_amount", None)

        if fixed_amount:
            amount_str = str(fixed_amount)
            amount_chinese = self._number_to_chinese(fixed_amount)
            return f"甲方向乙方支付法律顾问费¥{amount_str}元(大写:人民币{amount_chinese})"
        else:
            return "甲方向乙方支付法律顾问费¥[金额待定]元(大写:人民币[金额待定])"

    def _generate_custom_fee_terms(self, contract: Any) -> str:
        """生成自定义收费条款"""
        custom_terms = getattr(contract, "custom_terms", None)
        return custom_terms or "收费条款详见自定义条款."

    def _number_to_chinese(self, amount: Any) -> str:
        """
        将数字转换为中文大写金额

        Args:
            amount: 数字金额

        Returns:
            中文大写金额字符串(包含"元整"等完整格式)
        """
        if not amount:
            return "零元整"

        try:
            from apps.documents.services.placeholders.basic.number_service import NumberPlaceholderService

            number_service = NumberPlaceholderService()
            # number_to_chinese 返回带"元整"的完整格式
            return number_service.number_to_chinese(amount)
        except Exception as e:
            logger.warning(f"数字转换失败: {e}", extra={"amount": amount})
            return "零元整"
