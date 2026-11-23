"""
数字占位符服务

提供数字转中文大写金额功能.
"""

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry

logger = logging.getLogger(__name__)

_DIGIT_NAMES = ("零", "壹", "贰", "叁", "肆", "伍", "陆", "柒", "捌", "玖")
_UNIT_NAMES = ("", "拾", "佰", "仟")
# 整数位每 4 位一组：个、万、亿、万亿
_GROUP_UNIT_NAMES = ("", "万", "亿", "万亿")


def _render_group(group: str) -> str:
    """把 ≤4 位的一组数字渲染成「X仟Y佰Z拾W」；组内连续零压成一个、组尾零不输出。"""
    chunk = ""
    pending_zero = False
    for position, digit_char in enumerate(group):
        digit = int(digit_char)
        if digit == 0:
            pending_zero = bool(chunk)
            continue
        if pending_zero:
            chunk += "零"
            pending_zero = False
        chunk += _DIGIT_NAMES[digit] + _UNIT_NAMES[len(group) - 1 - position]
    return chunk


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
        """将数字转换为中文大写金额

        S19-06（2026-11-23 二轮审计）：原实现先把金额转 float 再拆整数/小数，整数位又只
        zfill(9)（只补不截），于是 ≥10 亿元时单位数组取到负下标、单位错位
        （1000000000 输出「壹亿元整」而不是「壹拾亿元整」），更大金额还会被 float 精度串味。
        现在全程走 Decimal，整数位按 4 位一组拼「万/亿/万亿」。
        """
        if not amount:
            return "零"

        try:
            if isinstance(amount, str):
                value = Decimal(amount)
            elif isinstance(amount, Decimal):
                value = amount
            else:
                value = Decimal(str(amount))

            if value < 0:
                logger.warning("金额为负数,大写按零处理", extra={"amount": amount})
                return "零"

            fixed = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            integer_part, decimal_part = f"{fixed:.2f}".split(".")

            return self._convert_integer_part(integer_part) + "元" + self._convert_decimal_part(decimal_part)

        except (ValueError, TypeError, ArithmeticError) as e:
            logger.warning("数字转换失败: %s", e, extra={"amount": amount})
            return "零"

    def _convert_integer_part(self, integer_part: str) -> str:
        """整数位转中文大写（不设 9 位上限，支持到「万亿」组）。

        S19-06（2026-11-23 二轮审计）：原实现固定 zfill(9) + 长度 9 的单位数组，
        ≥10 位整数时 chinese_units[8 - i] 变负下标，高位全落在「亿」上。
        """
        text = (integer_part or "").lstrip("0")
        if not text:
            return "零"

        group_count = (len(text) + 3) // 4
        if group_count > len(_GROUP_UNIT_NAMES):
            raise ValueError(f"金额整数位 {len(text)} 位，超出中文大写支持范围")

        # 低位在前切组：index 0 是个位组
        groups = [text[max(len(text) - 4 * (i + 1), 0) : len(text) - 4 * i] for i in range(group_count)]

        parts: list[str] = []
        for index in range(len(groups) - 1, -1, -1):
            group = groups[index]
            chunk = _render_group(group)
            if not chunk:
                # 整组为零：补一个「零」隔断，避免「壹亿壹」这类串读（连续空组只补一次）
                if parts and not parts[-1].endswith("零"):
                    parts.append("零")
                continue
            # 本组高位是零（如 10323 的低 4 位 0323）也要补「零」，否则读成「壹万叁佰……」
            if parts and group.startswith("0") and not parts[-1].endswith("零"):
                parts.append("零")
            parts.append(chunk + _GROUP_UNIT_NAMES[index])

        result = "".join(parts).rstrip("零")
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
