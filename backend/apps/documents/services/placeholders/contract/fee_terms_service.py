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
        result: dict[str, Any] = {}
        contract = context_data.get("contract")

        if contract:
            split_fee: bool = bool(context_data.get("split_fee", True))
            result["合同收费条款"] = self.generate_fee_terms(contract, split_fee=split_fee)

        return result

    def generate_fee_terms(self, contract: Any, split_fee: bool = True) -> str:
        try:
            fee_mode = getattr(contract, "fee_mode", None)
            fee_mode_upper = (fee_mode or "").upper()
            if fee_mode_upper == "FIXED":
                base = self._generate_fixed_fee_terms(contract)
            elif fee_mode_upper == "SEMI_RISK":
                base = self._generate_semi_risk_fee_terms(contract)
            elif fee_mode_upper == "FULL_RISK":
                base = self._generate_full_risk_fee_terms(contract)
            elif fee_mode_upper == "CUSTOM":
                base = self._generate_custom_fee_terms(contract)
            else:
                return "收费条款待定。"

            if split_fee and fee_mode_upper in ("FIXED", "SEMI_RISK"):
                split_text = self._generate_split_fee_text(contract)
                if split_text:
                    return f"{base}\a{split_text}"
            return base

        except Exception as e:
            logger.warning("生成收费条款失败: %s", e, extra={"contract_id": getattr(contract, "id", None)})
            return "收费条款待定。"

    def _generate_split_fee_text(self, contract: Any) -> str:
        """生成拆分律师费段落，案件数 < 2 或无 fixed_amount 时返回空字符串"""
        fixed_amount = getattr(contract, "fixed_amount", None)
        if not fixed_amount:
            return ""

        cases = list(contract.cases.all())
        if len(cases) < 2:
            return ""

        total_target = sum(float(getattr(c, "target_amount", 0) or 0) for c in cases)
        if total_target <= 0:
            return ""

        fixed = float(fixed_amount)
        case_lines: list[str] = []

        # 取第一个案件的原告名作为"甲方"
        first_case = cases[0]
        plaintiff_party = next(
            (p for p in first_case.parties.all() if (getattr(p, "legal_status", "") or "") == "plaintiff"),
            None,
        )
        client_name: str = plaintiff_party.client.name if plaintiff_party else "甲方"

        for i, case in enumerate(cases):
            t = float(getattr(case, "target_amount", 0) or 0)
            amount = round(fixed * t / total_target)

            defendants = [
                p.client.name for p in case.parties.all() if (getattr(p, "legal_status", "") or "") == "defendant"
            ]
            opponent = "、".join(defendants) if defendants else "对方当事人"

            amount_cn = self._number_to_chinese(amount)
            t_wan = round(t / 10000)
            case_lines.append(
                f"    案件{self._to_chinese_ordinal(i + 1)}"
                f"（{client_name}诉{opponent}），"
                f"争议金额约{t_wan}万元，"
                f"对应律师费为人民币{amount:.2f}元（大写：人民币{amount_cn}）；"
            )

        # 最后一项改分号为句号
        case_lines[-1] = case_lines[-1][:-1] + "。"

        count_cn = {1: "一", 2: "两", 3: "三"}.get(len(cases), str(len(cases)))
        lines_text = "\n".join(case_lines)
        return f"上述费用系甲方委托乙方代理以下{count_cn}案的全部律师代理费，按争议金额比例分摊如下：\n{lines_text}"

    @staticmethod
    def _to_chinese_ordinal(n: int) -> str:
        mapping = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九", 10: "十"}
        return mapping.get(n, str(n))

    def _generate_fixed_fee_terms(self, contract: Any) -> str:
        """生成固定收费条款"""
        fixed_amount = getattr(contract, "fixed_amount", None)

        if fixed_amount:
            fixed_amount_1 = str(float(fixed_amount))
            fixed_amount_2 = self._number_to_chinese(fixed_amount)
            return (
                f"本合同签订之日起5日内，甲方向乙方一次性支付律师费{fixed_amount_1}元（大写：人民币{fixed_amount_2}）。"
            )
        else:
            return "本合同签订之日起5日内，甲方向乙方一次性支付律师费  ,000元（大写：人民币    整）。"

    def _generate_semi_risk_fee_terms(self, contract: Any) -> str:
        """生成半风险收费条款"""
        fixed_amount = getattr(contract, "fixed_amount", None)
        risk_rate = getattr(contract, "risk_rate", None)

        fixed_amount_1 = str(fixed_amount) if fixed_amount else "       "
        fixed_amount_2 = self._number_to_chinese(fixed_amount) if fixed_amount else "      "
        risk_rate_str = str(risk_rate) if risk_rate else "12"

        return (
            f"本合同为风险代理收费，前期款为本合同签订之日起5日内，甲方向乙方一次性支付本案前期律师代理服务费{fixed_amount_1}元"
            f"（大写：人民币{fixed_amount_2}）。后期风险律师费自甲方通过诉讼、和解、调解、执行、案外收款等途径收到相关款项的5日内"
            f"按照实际收款金额的{risk_rate_str}%支付风险律师费。上述前期和后期律师代理服务费不重叠，计收后不再退还。"
        )

    def _generate_full_risk_fee_terms(self, contract: Any) -> str:
        """生成全风险收费条款"""
        risk_rate = getattr(contract, "risk_rate", None)
        risk_rate_str = str(risk_rate) if risk_rate else "[风险比例待定]"

        return (
            f"本合同为风险代理收费。自甲方通过诉讼、和解、调解、执行、案外收款等途径收到相关款项的5日内"
            f"按照实际收款金额的{risk_rate_str}%支付风险律师费。"
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
            logger.warning("数字转换失败: %s", e, extra={"amount": amount})
            return "零"
