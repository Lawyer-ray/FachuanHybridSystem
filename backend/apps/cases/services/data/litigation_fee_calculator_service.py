"""诉讼费用计算服务 - 根据《诉讼费用交纳办法》计算各类诉讼费用"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import ValidationException

if TYPE_CHECKING:
    from .cause_rule_service import CauseRuleService

logger = logging.getLogger(__name__)


# ============================================================================
# 费用计算规则常量
# ============================================================================

# 财产案件受理费分段规则
# 格式: (上限金额, 费率, 基础费用)
# 基础费用 = 该分段起点对应的累计费用
PROPERTY_CASE_FEE_TIERS: list[tuple[int | None, Decimal, Decimal]] = [
    (10000, Decimal("0"), Decimal("50")),  # ≤1万: 50元
    (100000, Decimal("0.025"), Decimal("50")),  # 1万-10万: 2.5%
    (200000, Decimal("0.02"), Decimal("2300")),  # 10万-20万: 2%
    (500000, Decimal("0.015"), Decimal("4300")),  # 20万-50万: 1.5%
    (1000000, Decimal("0.01"), Decimal("8800")),  # 50万-100万: 1%
    (2000000, Decimal("0.009"), Decimal("13800")),  # 100万-200万: 0.9%
    (5000000, Decimal("0.008"), Decimal("22800")),  # 200万-500万: 0.8%
    (10000000, Decimal("0.007"), Decimal("46800")),  # 500万-1000万: 0.7%
    (20000000, Decimal("0.006"), Decimal("81800")),  # 1000万-2000万: 0.6%
    (None, Decimal("0.005"), Decimal("141800")),  # >2000万: 0.5%
]

# 财产保全费分段规则
PRESERVATION_FEE_TIERS: list[tuple[int | None, Decimal, Decimal]] = [
    (1000, Decimal("0"), Decimal("30")),  # ≤1000: 30元
    (100000, Decimal("0.01"), Decimal("30")),  # 1000-10万: 1%
    (None, Decimal("0.005"), Decimal("1020")),  # >10万: 0.5%
]
PRESERVATION_FEE_MAX = Decimal("5000")  # 最高5000元

# 执行案件费分段规则
EXECUTION_FEE_TIERS: list[tuple[int | None, Decimal, Decimal]] = [
    (10000, Decimal("0"), Decimal("50")),  # ≤1万: 50元
    (500000, Decimal("0.015"), Decimal("50")),  # 1万-50万: 1.5%
    (5000000, Decimal("0.01"), Decimal("7400")),  # 50万-500万: 1%
    (10000000, Decimal("0.005"), Decimal("52400")),  # 500万-1000万: 0.5%
    (None, Decimal("0.001"), Decimal("77400")),  # >1000万: 0.1%
]

# 破产案件费用上限
BANKRUPTCY_FEE_MAX = Decimal("300000")  # 最高30万元

# 知识产权案件固定费用范围
IP_CASE_FEE_MIN = Decimal("500")
IP_CASE_FEE_MAX = Decimal("1000")
IP_CASE_FEE_DEFAULT = Decimal("500")

# 离婚案件基础费用范围
DIVORCE_CASE_FEE_MIN = Decimal("50")
DIVORCE_CASE_FEE_MAX = Decimal("300")
DIVORCE_PROPERTY_THRESHOLD = Decimal("200000")  # 20万元免费门槛
DIVORCE_PROPERTY_RATE = Decimal("0.005")  # 超过部分0.5%

# 人格权侵权案件基础费用范围
PERSONALITY_RIGHTS_FEE_MIN = Decimal("100")
PERSONALITY_RIGHTS_FEE_MAX = Decimal("500")
# 人格权案件损害赔偿分段规则
PERSONALITY_RIGHTS_DAMAGE_TIERS: list[tuple[int | None, Decimal, Decimal]] = [
    (50000, Decimal("0"), Decimal("0")),  # ≤5万: 不收费
    (100000, Decimal("0.01"), Decimal("0")),  # 5万-10万: 1%
    (None, Decimal("0.005"), Decimal("500")),  # >10万: 0.5%
]


class DiscountType:
    """费用减免类型"""

    MEDIATION = "mediation"  # 调解结案
    WITHDRAWAL = "withdrawal"  # 撤诉
    SIMPLE_PROCEDURE = "simple"  # 简易程序
    COUNTERCLAIM = "counterclaim"  # 反诉合并审理


class LitigationFeeCalculatorService:
    """
    诉讼费用计算服务

    根据《诉讼费用交纳办法》(2007年4月1日施行)计算各类诉讼费用.
    支持财产案件、保全、执行、支付令、知识产权、离婚、人格权侵权、破产等案件类型.
    """

    def __init__(self, cause_rule_service: CauseRuleService | None = None) -> None:
        """
        初始化诉讼费用计算服务

            cause_rule_service: 案由规则服务(可选,支持依赖注入)
        """
        self._cause_rule_service = cause_rule_service

    @property
    def cause_rule_service(self) -> CauseRuleService:
        """延迟加载案由规则服务"""
        if self._cause_rule_service is None:
            from .cause_rule_service import CauseRuleService

            self._cause_rule_service = CauseRuleService()
        return self._cause_rule_service

    def _calculate_tiered_fee(self, amount: Decimal, tiers: list[tuple[int | None, Decimal, Decimal]]) -> Decimal:
        """
        通用分段累计计算方法

        根据分段规则计算费用.每个分段包含:
        - 上限金额(None 表示无上限)
        - 费率(该分段的计算费率)
        - 基础费用(到达该分段起点时的累计费用)

            amount: 计算金额(必须为非负数)
            tiers: 分段规则列表,格式为 [(上限, 费率, 基础费用), ...]

            Decimal: 计算得到的费用

        Example:
            对于金额 150000(15万),使用财产案件规则:
            - 第一段 ≤1万: 基础费用 50
            - 第二段 1万-10万: 50 + (100000-10000)*0.025 = 2300
            - 第三段 10万-20万: 2300 + (150000-100000)*0.02 = 3300
        """
        if amount <= 0:
            # 金额为0或负数,返回第一段的基础费用
            return tiers[0][2]

        prev_threshold = Decimal("0")

        for threshold, rate, base_fee in tiers:
            # 如果是最后一段(无上限)或金额在当前分段内
            if threshold is None or amount <= threshold:
                # 计算当前分段的费用
                excess = amount - prev_threshold
                return base_fee + excess * rate

            # 更新前一个分段的上限
            prev_threshold = Decimal(str(threshold))

        # 理论上不会到达这里,因为最后一段的 threshold 是 None
        return tiers[-1][2]

    def calculate_property_case_fee(self, amount: Decimal) -> Decimal:
        """
        计算财产案件受理费

        根据《诉讼费用交纳办法》第十三条第一款的10个分段规则计算.

            amount: 涉案金额(必须为非负数)

            Decimal: 案件受理费
        """
        if amount < 0:
            amount = Decimal("0")
        return self._calculate_tiered_fee(amount, PROPERTY_CASE_FEE_TIERS)

    def calculate_preservation_fee(self, amount: Decimal) -> Decimal:
        """
        计算财产保全申请费

        按照3个分段规则计算,确保不超过5000元上限.

            amount: 财产保全金额(必须为非负数)

            Decimal: 财产保全申请费(最高5000元)
        """
        if amount < 0:
            amount = Decimal("0")
        fee = self._calculate_tiered_fee(amount, PRESERVATION_FEE_TIERS)
        return min(fee, PRESERVATION_FEE_MAX)

    def calculate_execution_fee(self, amount: Decimal) -> Decimal:
        """
        计算执行案件费用

        按照5个分段规则计算.

            amount: 执行金额(必须为非负数)

            Decimal: 执行案件费用
        """
        if amount < 0:
            amount = Decimal("0")
        return self._calculate_tiered_fee(amount, EXECUTION_FEE_TIERS)

    def calculate_payment_order_fee(self, amount: Decimal) -> Decimal:
        """
        计算支付令申请费

        按财产案件受理费的1/3计算.

            amount: 申请金额(必须为非负数)

            Decimal: 支付令申请费
        """
        property_fee = self.calculate_property_case_fee(amount)
        return property_fee / Decimal("3")

    def calculate_ip_case_fee(self, amount: Decimal | None = None) -> Decimal:
        """
        计算知识产权案件费用

        无争议金额返回固定费用,有争议金额按财产案件规则计算.

            amount: 争议金额(可选,None 表示无争议金额)

            Decimal: 知识产权案件费用
        """
        if amount is None or amount <= 0:
            return IP_CASE_FEE_DEFAULT
        return self.calculate_property_case_fee(amount)

    def calculate_divorce_case_fee(self, base_fee: Decimal, property_amount: Decimal | None = None) -> Decimal:
        """
        计算离婚案件费用

        基础费用50-300元,财产超过20万按0.5%计算.

            base_fee: 基础费用(50-300元)
            property_amount: 财产分割金额(可选)

            Decimal: 离婚案件费用
        """
        # 确保基础费用在有效范围内
        base_fee = max(DIVORCE_CASE_FEE_MIN, min(base_fee, DIVORCE_CASE_FEE_MAX))

        if property_amount is None or property_amount <= DIVORCE_PROPERTY_THRESHOLD:
            return base_fee

        # 超过20万的部分按0.5%计算
        extra_fee = (property_amount - DIVORCE_PROPERTY_THRESHOLD) * DIVORCE_PROPERTY_RATE
        return base_fee + extra_fee

    def calculate_personality_rights_fee(self, base_fee: Decimal, damage_amount: Decimal | None = None) -> Decimal:
        """
        计算人格权侵权案件费用

        基础费用100-500元,按分段规则计算额外费用.

            base_fee: 基础费用(100-500元)
            damage_amount: 损害赔偿金额(可选)

            Decimal: 人格权侵权案件费用
        """
        # 确保基础费用在有效范围内
        base_fee = max(PERSONALITY_RIGHTS_FEE_MIN, min(base_fee, PERSONALITY_RIGHTS_FEE_MAX))

        if damage_amount is None or damage_amount <= 0:
            return base_fee

        # 按分段规则计算额外费用
        extra_fee = self._calculate_tiered_fee(damage_amount, PERSONALITY_RIGHTS_DAMAGE_TIERS)
        return base_fee + extra_fee

    def calculate_bankruptcy_fee(self, property_amount: Decimal) -> Decimal:
        """
        计算破产案件费用

        按财产案件受理费减半计算,最高不超过30万元.

            property_amount: 财产金额

            Decimal: 破产案件费用(最高30万元)
        """
        if property_amount < 0:
            property_amount = Decimal("0")

        property_fee = self.calculate_property_case_fee(property_amount)
        fee = property_fee / Decimal("2")
        return min(fee, BANKRUPTCY_FEE_MAX)

    def calculate_personality_rights_fee_with_range(self, amount: Decimal | None = None) -> dict[str, Any]:
        """
        计算人格权案件费用(支持范围显示)

        计算规则:
        - 金额 ≤ 5万:基础费用 100-500 元
        - 5万 < 金额 ≤ 10万:基础费用 + (金额 - 50000) × 1%
        - 金额 > 10万:基础费用 + 500 + (金额 - 100000) × 0.5%

            amount: 涉案金额(可选,None 表示无涉案金额)

            dict[str, Any]: 费用计算结果
            {
                "fee": Decimal | None,      # 精确费用(有金额时)
                "fee_min": Decimal,         # 费用范围最小值
                "fee_max": Decimal,         # 费用范围最大值
                "display_text": str,        # 显示文本
            }

        Requirements: 2.2, 2.3, 2.4, 2.5
        """
        base_min = PERSONALITY_RIGHTS_FEE_MIN  # 100
        base_max = PERSONALITY_RIGHTS_FEE_MAX  # 500

        # 无金额或金额为0:返回基础费用范围
        if amount is None or amount <= 0:
            return {
                "fee": None,
                "fee_min": base_min,
                "fee_max": base_max,
                "display_text": f"案件受理费:{base_min}-{base_max}元,减半后受理费:{base_min // 2}-{base_max // 2}元",
            }

        # 金额 ≤ 5万:基础费用范围
        threshold_1 = Decimal("50000")
        threshold_2 = Decimal("100000")

        if amount <= threshold_1:
            return {
                "fee": None,
                "fee_min": base_min,
                "fee_max": base_max,
                "display_text": f"案件受理费:{base_min}-{base_max}元,减半后受理费:{base_min // 2}-{base_max // 2}元",
            }

        # 5万 < 金额 ≤ 10万:基础费用 + (金额 - 50000) × 1%
        if amount <= threshold_2:
            extra_fee = (amount - threshold_1) * Decimal("0.01")
            fee_min = base_min + extra_fee
            fee_max = base_max + extra_fee
            return {
                "fee": None,
                "fee_min": fee_min,
                "fee_max": fee_max,
                "display_text": f"案件受理费:{fee_min:.2f}-{fee_max:.2f}元",
            }

        # 金额 > 10万:基础费用 + 500 + (金额 - 100000) × 0.5%
        # 注:500 是 5万-10万 部分的费用 (50000 × 1%)
        tier_2_fee = Decimal("500")  # (100000 - 50000) × 1%
        extra_fee = (amount - threshold_2) * Decimal("0.005")
        fee_min = base_min + tier_2_fee + extra_fee
        fee_max = base_max + tier_2_fee + extra_fee

        return {
            "fee": None,
            "fee_min": fee_min,
            "fee_max": fee_max,
            "display_text": f"案件受理费:{fee_min:.2f}-{fee_max:.2f}元",
        }

    def calculate_ip_fee_with_range(self, amount: Decimal | None = None) -> dict[str, Any]:
        """
        计算知识产权案件费用(支持范围显示)

        计算规则:
        - 无金额:500-1000元范围
        - 有金额:按财产案件标准计算

            amount: 涉案金额(可选,None 表示无涉案金额)

            dict[str, Any]: 费用计算结果
            {
                "fee": Decimal | None,      # 精确费用(有金额时)
                "fee_min": Decimal,         # 费用范围最小值
                "fee_max": Decimal,         # 费用范围最大值
                "display_text": str,        # 显示文本
            }

        Requirements: 3.2, 3.3
        """
        # 无金额或金额为0:返回固定费用范围
        if amount is None or amount <= 0:
            return {
                "fee": None,
                "fee_min": IP_CASE_FEE_MIN,
                "fee_max": IP_CASE_FEE_MAX,
                "display_text": (
                    f"案件受理费:{IP_CASE_FEE_MIN}-{IP_CASE_FEE_MAX}元,"
                    f"减半后受理费:{IP_CASE_FEE_MIN // 2}-{IP_CASE_FEE_MAX // 2}元"
                ),
            }

        # 有金额:按财产案件标准计算
        fee = self.calculate_property_case_fee(amount)
        return {
            "fee": fee,
            "fee_min": fee,
            "fee_max": fee,
            "display_text": f"案件受理费:{fee:.2f}元(按财产案件标准)",
        }

    def apply_discount(self, fee: Decimal, discount_type: str) -> Decimal:
        """
        应用费用减免

        支持调解、撤诉、简易程序、反诉合并等减免类型,均为减半.

            fee: 原始费用
            discount_type: 减免类型(mediation/withdrawal/simple/counterclaim)

            Decimal: 减免后费用
        """
        valid_types = [
            DiscountType.MEDIATION,
            DiscountType.WITHDRAWAL,
            DiscountType.SIMPLE_PROCEDURE,
            DiscountType.COUNTERCLAIM,
        ]

        if discount_type in valid_types:
            return fee / Decimal("2")

        return fee

    def _build_default_result(self) -> dict[str, Any]:
        """构建默认费用结果字典"""
        return {
            "acceptance_fee": None,
            "acceptance_fee_half": None,
            "preservation_fee": None,
            "execution_fee": None,
            "payment_order_fee": None,
            "bankruptcy_fee": None,
            "divorce_fee": None,
            "personality_rights_fee": None,
            "ip_fee": None,
            "fixed_fee": None,
            "fee_name": None,
            "calculation_details": [],
            "special_case_type": None,
            "fee_display_text": None,
            "fee_range_min": None,
            "fee_range_max": None,
            "show_acceptance_fee": True,
            "show_half_fee": True,
            "show_payment_order_fee": False,
        }

    def _append_preservation_fee(self, result: dict[str, Any], preservation_amount: Decimal | None) -> None:
        """如果有保全金额,计算并追加保全费"""
        if preservation_amount is not None and preservation_amount > 0:
            result["preservation_fee"] = float(self.calculate_preservation_fee(preservation_amount))
            result["calculation_details"].append(f"财产保全费: {result['preservation_fee']:.2f} 元(最高5000元)")

    def _apply_fee_rule(self, result: dict[str, Any], fee_rule: dict[str, Any]) -> None:
        """应用案由特殊规则到结果"""
        result["special_case_type"] = fee_rule.get("special_case_type")
        result["show_acceptance_fee"] = fee_rule.get("show_acceptance_fee", True)
        result["show_half_fee"] = fee_rule.get("show_half_fee", True)
        result["show_payment_order_fee"] = fee_rule.get("show_payment_order_fee", False)

    def _handle_special_type(
        self,
        special_type: str,
        result: dict[str, Any],
        fee_rule: dict[str, Any],
        target_amount: Decimal | None,
        preservation_amount: Decimal | None,
    ) -> bool:
        """处理特殊案件类型,返回 True 表示已处理"""
        from .cause_rule_service import FIXED_FEES, SpecialCaseType

        handler_map = {
            SpecialCaseType.PERSONALITY_RIGHTS: self._handle_personality_rights_special,
            SpecialCaseType.IP: self._handle_ip_special,
            SpecialCaseType.PAYMENT_ORDER: self._handle_payment_order_special,
        }

        # 固定费用类型
        if special_type in FIXED_FEES:
            result["fixed_fee"] = float(FIXED_FEES[special_type])
            result["fee_display_text"] = fee_rule.get("fee_display_text")
            result["calculation_details"].append(result["fee_display_text"])
            self._append_preservation_fee(result, preservation_amount)
            return True

        handler = handler_map.get(special_type)
        if handler:
            handler(result, target_amount)
            self._append_preservation_fee(result, preservation_amount)
            return True

        return False

    def _handle_personality_rights_special(self, result: dict[str, Any], target_amount: Decimal | None) -> None:
        """处理人格权特殊案件"""
        pr_result = self.calculate_personality_rights_fee_with_range(target_amount)
        result["fee_range_min"] = float(pr_result["fee_min"])
        result["fee_range_max"] = float(pr_result["fee_max"])
        result["fee_display_text"] = pr_result["display_text"]
        if pr_result["fee"] is not None:
            result["personality_rights_fee"] = float(pr_result["fee"])
            result["acceptance_fee"] = float(pr_result["fee"])
            result["acceptance_fee_half"] = float(pr_result["fee"] / Decimal("2"))
        result["calculation_details"].append(pr_result["display_text"])

    def _handle_ip_special(self, result: dict[str, Any], target_amount: Decimal | None) -> None:
        """处理知识产权特殊案件"""
        ip_result = self.calculate_ip_fee_with_range(target_amount)
        result["fee_range_min"] = float(ip_result["fee_min"])
        result["fee_range_max"] = float(ip_result["fee_max"])
        result["fee_display_text"] = ip_result["display_text"]
        if ip_result["fee"] is not None:
            result["ip_fee"] = float(ip_result["fee"])
            result["acceptance_fee"] = float(ip_result["fee"])
            result["acceptance_fee_half"] = float(ip_result["fee"] / Decimal("2"))
        result["calculation_details"].append(ip_result["display_text"])

    def _handle_payment_order_special(self, result: dict[str, Any], target_amount: Decimal | None) -> None:
        """处理支付令特殊案件"""
        if target_amount is not None and target_amount > 0:
            acceptance_fee = self.calculate_property_case_fee(target_amount)
            result["acceptance_fee"] = float(acceptance_fee)
            result["acceptance_fee_half"] = float(acceptance_fee / Decimal("2"))
            result["payment_order_fee"] = float(self.calculate_payment_order_fee(target_amount))
            result["calculation_details"].append(f"案件受理费: {result['acceptance_fee']:.2f} 元")
            result["calculation_details"].append(
                f"减半后受理费: {result['acceptance_fee_half']:.2f} 元(调解/撤诉/简易程序)"
            )
            result["calculation_details"].append(f"支付令申请费: {result['payment_order_fee']:.2f} 元(受理费的1/3)")

    def _handle_amount_based_case(self, result: dict[str, Any], case_type: str, target_amount: Decimal) -> None:
        """处理需要金额计算的案件类型"""
        handlers = {
            "execution": self._calc_execution,
            "bankruptcy": self._calc_bankruptcy,
            "payment_order": self._calc_payment_order_by_type,
            "divorce": self._calc_divorce,
            "personality_rights": self._calc_personality_rights_by_type,
            "ip_with_amount": self._calc_ip_with_amount,
        }
        handler = handlers.get(case_type)
        if handler:
            handler(result, target_amount)
        else:
            self._calc_default_property(result, target_amount)

    def _calc_execution(self, result: dict[str, Any], amount: Decimal) -> None:
        result["execution_fee"] = float(self.calculate_execution_fee(amount))
        result["calculation_details"].append(f"执行案件费用: {result['execution_fee']:.2f} 元")

    def _calc_bankruptcy(self, result: dict[str, Any], amount: Decimal) -> None:
        result["bankruptcy_fee"] = float(self.calculate_bankruptcy_fee(amount))
        result["calculation_details"].append(
            f"破产案件费用: {result['bankruptcy_fee']:.2f} 元(财产案件费减半,最高30万元)"
        )

    def _calc_payment_order_by_type(self, result: dict[str, Any], amount: Decimal) -> None:
        result["payment_order_fee"] = float(self.calculate_payment_order_fee(amount))
        result["show_payment_order_fee"] = True
        result["calculation_details"].append(f"支付令申请费: {result['payment_order_fee']:.2f} 元(财产案件费的1/3)")

    def _calc_divorce(self, result: dict[str, Any], amount: Decimal) -> None:
        base_fee = Decimal("150")
        result["divorce_fee"] = float(self.calculate_divorce_case_fee(base_fee, amount))
        if amount > DIVORCE_PROPERTY_THRESHOLD:
            result["calculation_details"].append(
                f"离婚案件费用: {result['divorce_fee']:.2f} 元(基础费150元 + 超过20万部分×0.5%)"
            )
        else:
            result["calculation_details"].append(
                f"离婚案件费用: {result['divorce_fee']:.2f} 元(基础费,财产不超过20万不另收)"
            )

    def _calc_personality_rights_by_type(self, result: dict[str, Any], amount: Decimal) -> None:
        base_fee = Decimal("300")
        result["personality_rights_fee"] = float(self.calculate_personality_rights_fee(base_fee, amount))
        result["calculation_details"].append(f"人格权侵权案件费用: {result['personality_rights_fee']:.2f} 元")

    def _calc_ip_with_amount(self, result: dict[str, Any], amount: Decimal) -> None:
        result["ip_fee"] = float(self.calculate_ip_case_fee(amount))
        result["calculation_details"].append(f"知识产权案件费用: {result['ip_fee']:.2f} 元(按财产案件标准)")

    def _calc_default_property(self, result: dict[str, Any], amount: Decimal) -> None:
        acceptance_fee = self.calculate_property_case_fee(amount)
        result["acceptance_fee"] = float(acceptance_fee)
        result["acceptance_fee_half"] = float(acceptance_fee / Decimal("2"))
        result["payment_order_fee"] = float(self.calculate_payment_order_fee(amount))
        result["calculation_details"].append(f"案件受理费: {result['acceptance_fee']:.2f} 元")
        result["calculation_details"].append(
            f"减半后受理费: {result['acceptance_fee_half']:.2f} 元(调解/撤诉/简易程序)"
        )
        result["calculation_details"].append(f"支付令申请费: {result['payment_order_fee']:.2f} 元(受理费的1/3)")

    def validate_and_convert_fee_inputs(
        self,
        target_amount: float | None,
        preservation_amount: float | None,
    ) -> tuple[Decimal | None, Decimal | None]:
        """
        验证并转换费用计算输入参数

            target_amount: 涉案金额（浮点数）
            preservation_amount: 财产保全金额（浮点数）

            转换后的 (target_amount, preservation_amount) Decimal 元组

            ValidationException: 金额为负数时抛出
        """
        if target_amount is not None and target_amount < 0:
            raise ValidationException(_("涉案金额不能为负数"))

        if preservation_amount is not None and preservation_amount < 0:
            raise ValidationException(_("财产保全金额不能为负数"))

        converted_target = Decimal(str(target_amount)) if target_amount is not None else None
        converted_preservation = Decimal(str(preservation_amount)) if preservation_amount is not None else None

        return converted_target, converted_preservation

    def calculate_all_fees(
        self,
        target_amount: Decimal | None = None,
        preservation_amount: Decimal | None = None,
        case_type: str | None = None,
        cause_of_action: str | None = None,
        cause_of_action_id: int | None = None,
    ) -> dict[str, Any]:
        """
        计算所有相关费用

        根据案件类型和案由自动选择计算规则,返回所有相关费用的字典.
        """
        result = self._build_default_result()

        # 如果提供了案由ID,获取特殊案件规则
        fee_rule = None
        if cause_of_action_id:
            fee_rule = self.cause_rule_service.get_fee_rule(cause_of_action_id)
            if fee_rule:
                self._apply_fee_rule(result, fee_rule)
                logger.info(
                    "应用案由特殊规则",
                    extra={
                        "cause_of_action_id": cause_of_action_id,
                        "special_case_type": result["special_case_type"],
                    },
                )

        # 根据特殊案件类型处理
        special_type = result["special_case_type"]
        if (
            special_type
            and fee_rule
            and self._handle_special_type(special_type, result, fee_rule, target_amount, preservation_amount)
        ):
            return result

        # 处理固定费用类型
        fixed_fee_types = {
            "labor": (Decimal("10"), "劳动争议案件"),
            "public_notice": (Decimal("100"), "公示催告申请"),
            "revoke_arbitration": (Decimal("400"), "撤销仲裁裁决/认定仲裁协议效力"),
            "admin_ip": (Decimal("100"), "商标/专利/海事行政案件"),
            "admin_other": (Decimal("50"), "其他行政案件"),
            "other_non_property": (Decimal("50"), "其他非财产案件(50-100元)"),
            "jurisdiction_objection": (Decimal("50"), "管辖权异议(50-100元)"),
            "ip_no_amount": (Decimal("500"), "知识产权案件(无争议金额,500-1000元)"),
        }

        if case_type in fixed_fee_types:
            fee, name = fixed_fee_types[case_type]
            result["fixed_fee"] = float(fee)
            result["fee_name"] = name
            result["calculation_details"].append(f"{name}: {fee:.2f} 元")
            self._append_preservation_fee(result, preservation_amount)
            return result

        # 处理需要金额计算的类型
        if target_amount is not None and target_amount > 0:
            self._handle_amount_based_case(result, case_type or "", target_amount)

        # 计算财产保全费
        if preservation_amount is not None and preservation_amount > 0:
            self._append_preservation_fee(result, preservation_amount)
        elif case_type == "preservation_only":
            result["calculation_details"].append("请输入财产保全金额")

        return result
