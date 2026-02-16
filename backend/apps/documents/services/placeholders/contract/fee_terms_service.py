"""
收费条款占位符服务

根据收费模式生成收费条款.
"""

import logging
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class FeeTermsService(BasePlaceholderService):
    """收费条款服务"""

    name: str = "fee_terms_service"
    display_name: str = "收费条款服务"
    description: str = "根据收费模式生成收费条款"
    category: str = "contract"
    placeholder_keys: ClassVar = ["合同收费条款"]

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        生成收费条款占位符

        Args:
            context_data: 包含 contract 等数据的上下文

        Returns:
            包含收费条款占位符的字典
        """
        result: dict[str, Any] = {}
        contract = context_data.get("contract")

        if contract:
            # {{合同收费条款}} - 根据收费模式生成收费条款
            result["合同收费条款"] = self.generate_fee_terms(contract)

        return result

    def generate_fee_terms(self, contract: Any) -> str:
        """
        根据收费模式格式化收费条款

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
            elif fee_mode == "SEMI_RISK":
                return self._generate_semi_risk_fee_terms(contract)
            elif fee_mode == "FULL_RISK":
                return self._generate_full_risk_fee_terms(contract)
            elif fee_mode == "CUSTOM":
                return self._generate_custom_fee_terms(contract)
            else:
                return "收费条款待定."

        except Exception as e:
            logger.warning(f"生成收费条款失败: {e}", extra={"contract_id": getattr(contract, "id", None)})
            return "收费条款待定."

    def _generate_fixed_fee_terms(self, contract: Any) -> str:
        """生成固定收费条款"""
        fixed_amount = getattr(contract, "fixed_amount", None)

        if fixed_amount:
            fixed_amount_1 = str(fixed_amount)
            fixed_amount_2 = self._number_to_chinese(fixed_amount)
            return f"本合同签订之日起5日内,甲方向乙方一次性支付律师费{fixed_amount_1}元(大写:人民币{fixed_amount_2})."
        else:
            return "本合同签订之日起5日内,甲方向乙方一次性支付律师费[金额待定]元."

    def _generate_semi_risk_fee_terms(self, contract: Any) -> str:
        """生成半风险收费条款"""
        fixed_amount = getattr(contract, "fixed_amount", None)
        risk_rate = getattr(contract, "risk_rate", None)

        fixed_amount_1 = str(fixed_amount) if fixed_amount else "[前期费用待定]"
        fixed_amount_2 = self._number_to_chinese(fixed_amount) if fixed_amount else "[前期费用大写待定]"
        risk_rate_str = str(risk_rate) if risk_rate else "[风险比例待定]"

        return (
            f"本合同为风险代理收费,前期款为本合同签订之日起5日内,甲方向乙方一次性支付本案前期律师代理服务费{fixed_amount_1}元"
            f"(大写:人民币{fixed_amount_2}).后期风险律师费自甲方通过诉讼、和解、调解、执行、案外收款等途径收到相关款项的5日内"
            f"按照实际收款金额的{risk_rate_str}%支付风险律师费.上述前期和后期律师代理服务费不重叠,计收后不再退还."
        )

    def _generate_full_risk_fee_terms(self, contract: Any) -> str:
        """生成全风险收费条款"""
        risk_rate = getattr(contract, "risk_rate", None)
        risk_rate_str = str(risk_rate) if risk_rate else "[风险比例待定]"

        return (
            f"本合同为风险代理收费.自甲方通过诉讼、和解、调解、执行、案外收款等途径收到相关款项的5日内"
            f"按照实际收款金额的{risk_rate_str}%支付风险律师费."
        )

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
            中文大写金额字符串
        """
        if not amount:
            return "零"

        try:
            # 使用 NumberPlaceholderService 的逻辑
            from apps.documents.services.placeholders.basic.number_service import NumberPlaceholderService

            number_service = NumberPlaceholderService()
            return number_service.number_to_chinese(amount)
        except Exception as e:
            logger.warning(f"数字转换失败: {e}", extra={"amount": amount})
            return "零"
