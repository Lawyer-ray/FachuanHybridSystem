"""
数字占位符服务

提供数字转中文大写金额功能.
"""

import logging
from decimal import Decimal
from typing import Any, ClassVar, cast

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class NumberPlaceholderService(BasePlaceholderService):
    """数字格式化服务"""

    name: str = "number_service"
    display_name: str = "数字格式化服务"
    description: str = "将数字转换为中文大写金额"
    category: str = "basic"
    placeholder_keys: ClassVar = ["金额大写", "固定金额大写"]

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        生成数字占位符

        Args:
            context_data: 包含 contract 等数据的上下文

        Returns:
            包含数字占位符的字典
        """
        result: dict[str, Any] = {}
        contract = context_data.get("contract")

        if contract:
            # {{固定金额大写}} - 固定金额的中文大写
            if hasattr(contract, "fixed_amount") and contract.fixed_amount:
                result["固定金额大写"] = self.number_to_chinese(contract.fixed_amount)
            else:
                result["固定金额大写"] = "零"

        return result

    def number_to_chinese(self, amount: Any) -> str:
        """将数字转换为中文大写金额"""
        if not amount:
            return "零"

        try:
            if isinstance(amount, str):
                amount = Decimal(amount)
            elif not isinstance(amount, Decimal):
                amount = Decimal(str(amount))

            amount_str = str(float(amount))
            if "." in amount_str:
                integer_part, decimal_part = amount_str.split(".")
            else:
                integer_part = amount_str
                decimal_part = "00"

            decimal_part = decimal_part.ljust(2, "0")[:2]

            result = self._convert_integer_part(integer_part)
            result += "元"
            result += self._convert_decimal_part(decimal_part)

            return cast(str, result) # type: ignore

        except (ValueError, TypeError, ArithmeticError) as e:
            logger.warning("数字转换失败: %s", e, extra={"amount": amount})
            return "零"

    def _convert_integer_part(self, integer_part: str) -> str:
        chinese_nums = ["零", "壹", "贰", "叁", "肆", "伍", "陆", "柒", "捌", "玖"]
        chinese_units = ["", "拾", "佰", "仟", "万", "拾", "佰", "仟", "亿"]
        integer_part = integer_part.zfill(9)
        result = ""
        for i, digit in enumerate(integer_part):
            digit_int = int(digit)
            if digit_int != 0:
                result += chinese_nums[digit_int] + chinese_units[8 - i]
            elif result and not result.endswith("零"):
                result += "零"
        result = result.rstrip("零")
        return result or "零"

    def _convert_decimal_part(self, decimal_part: str) -> str:
        chinese_nums = ["零", "壹", "贰", "叁", "肆", "伍", "陆", "柒", "捌", "玖"]
        jiao = int(decimal_part[0])
        fen = int(decimal_part[1])
        if jiao == 0 and fen == 0:
            return "整"
        result = ""
        if jiao != 0:
            result += chinese_nums[jiao] + "角"
        if fen != 0:
            result += chinese_nums[fen] + "分"
        return result
