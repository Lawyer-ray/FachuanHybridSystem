"""
费用金额提取器

从交费通知书文本中提取各项费用金额.
支持横向费用明细表和纵向收费单两种格式.
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from .models import FeeAmountResult

logger = logging.getLogger("apps.automation")


# 费用名称映射
FEE_NAME_MAPPING: dict[str, str] = {
    "案件受理费": "acceptance_fee",
    "受理费": "acceptance_fee",
    "申请费": "application_fee",  # 申请费(保全申请费等)独立字段
    "保全费": "preservation_fee",
    "财产保全费": "preservation_fee",
    "执行费": "execution_fee",
    "其他诉讼费": "other_fee",
    "其他费用": "other_fee",
}

# 所有费用名称关键词
FEE_KEYWORDS: list[str] = list(FEE_NAME_MAPPING.keys())


class FeeAmountExtractor:
    """费用金额提取器"""

    def extract(self, text: str, debug: bool = False) -> FeeAmountResult:
        """
        从交费通知书文本中提取费用金额

        Args:
            text: 交费通知书文本
            debug: 是否输出调试信息

        Returns:
            FeeAmountResult: 提取结果,包含各项费用和调试信息
        """
        debug_info: dict[str, Any] = {}

        if debug:
            debug_info["raw_text"] = text[:500] if len(text) > 500 else text
            logger.info("开始提取费用金额", extra={"text_length": len(text), "debug": debug})

        # 尝试横向表格解析
        horizontal_result = self._extract_horizontal_table(text)
        if horizontal_result:
            if debug:
                debug_info["table_format"] = "horizontal"
                debug_info["extracted_fees"] = {k: str(v) for k, v in horizontal_result.items()}
                logger.info("横向表格解析成功", extra={"fees": debug_info["extracted_fees"]})
            return self._build_result(horizontal_result, "horizontal", debug_info)

        # 尝试纵向表格解析
        vertical_result = self._extract_vertical_table(text)
        if vertical_result:
            if debug:
                debug_info["table_format"] = "vertical"
                debug_info["extracted_fees"] = {k: str(v) for k, v in vertical_result.items()}
                logger.info("纵向表格解析成功", extra={"fees": debug_info["extracted_fees"]})
            return self._build_result(vertical_result, "vertical", debug_info)

        # 尝试通用模式提取
        general_result = self._extract_general_pattern(text)
        if general_result:
            if debug:
                debug_info["table_format"] = "general"
                debug_info["extracted_fees"] = {k: str(v) for k, v in general_result.items()}
                logger.info("通用模式解析成功", extra={"fees": debug_info["extracted_fees"]})
            return self._build_result(general_result, "general", debug_info)

        if debug:
            debug_info["table_format"] = "unknown"
            debug_info["error"] = "未能识别费用表格格式"
            logger.warning("未能识别费用表格格式", extra={"text_preview": text[:200]})

        return FeeAmountResult(table_format="unknown", debug_info=debug_info)

    def _extract_horizontal_table(self, text: str) -> dict[str, Decimal] | None | None:
        """
        提取横向费用明细表

        格式示例(换行分隔):
        收费项目名称 | 受理费 | 保全费 | 执行费 | 其他诉讼费
        金额        |  0    | 252.93 |  0    |    0

        格式示例(连续文本,PDF直接提取):
        收费项目名称 受理费 保全费 执行费 其他诉讼费 金额 0 252.93 0 0 应收金额 252.93
        """
        cleaned_text = self._normalize_text(text)

        # 首先尝试连续文本模式(PDF直接提取的格式)
        continuous_result = self._extract_continuous_horizontal(cleaned_text)
        if continuous_result:
            return continuous_result

        # 然后尝试换行分隔的表格模式
        lines = cleaned_text.split("\n")

        header_line_idx, header_cells = self._find_horizontal_header(lines)
        if header_line_idx < 0 or len(header_cells) < 2:
            return None

        column_mapping = self._build_column_mapping(header_cells)
        if not column_mapping:
            return None

        return self._extract_amounts_from_rows(lines[header_line_idx + 1 :], column_mapping)

    def _find_horizontal_header(self, lines: list[str]) -> tuple[int, list[str]]:
        """查找包含多个费用名称的表头行"""
        fee_keywords: list[Any] = []
        for idx, line in enumerate(lines):
            fee_count = sum(1 for kw in fee_keywords if kw in line)
            if fee_count >= 2:
                if "|" in line:
                    cells = re.split(r"[|｜\t]+", line)
                else:
                    cells = self._split_fee_header_by_space(line)
                return idx, [c.strip() for c in cells]
        return -1, []

    def _build_column_mapping(self, header_cells: list[str]) -> dict[int, str]:
        """映射列索引到费用字段"""
        mapping: dict[int, str] = {}
        for idx, col_name in enumerate(header_cells):
            if not col_name or "收费项目" in col_name or col_name == "名称":
                continue
            field_name = self._match_fee_field(col_name)
            if field_name:
                mapping[idx] = field_name
        return mapping

    def _extract_amounts_from_rows(self, lines: list[str], column_mapping: dict[int, str]) -> dict[str, Decimal] | None:
        """从金额行中提取费用"""
        result: dict[str, Decimal] = {}
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped or "应收金额" in line_stripped:
                continue
            if "金额" in line_stripped and "应收" not in line_stripped:
                if "|" in line_stripped:
                    amount_cells = re.split(r"[|｜\t]+", line_stripped)
                else:
                    amount_cells = self._split_amount_row_by_space(line_stripped)
                amount_cells: list[Any] = []
                for idx, field_name in column_mapping.items():
                    if idx < len(amount_cells):
                        cell_value = amount_cells[idx]
                        if "金额" in cell_value:
                            continue
                        amount = self._parse_amount(cell_value)
                        if amount is not None:
                            result[field_name] = amount
                break
        return result if result else None

    def _extract_continuous_horizontal(self, text: str) -> dict[str, Decimal] | None | None:
        """
        提取连续文本格式的横向费用表

        PDF直接提取的文本通常是连续的,没有换行:
        收费项目名称 受理费 保全费 执行费 其他诉讼费 金额 0 252.93 0 0 应收金额 252.93
        """
        result: dict[str, Decimal] = {}

        # 模式: 受理费 保全费 执行费 其他诉讼费 金额 数字 数字 数字 数字
        pattern = r"受理费\s+保全费\s+执行费\s+其他诉讼费\s+金额\s+([\d,\.]+)\s+([\d,\.]+)\s+([\d,\.]+)\s+([\d,\.]+)"
        match = re.search(pattern, text)

        if match:
            acceptance = self._parse_amount(match.group(1))
            preservation = self._parse_amount(match.group(2))
            execution = self._parse_amount(match.group(3))
            other = self._parse_amount(match.group(4))

            if acceptance is not None:
                result["acceptance_fee"] = acceptance
            if preservation is not None:
                result["preservation_fee"] = preservation
            if execution is not None:
                result["execution_fee"] = execution
            if other is not None:
                result["other_fee"] = other

            return result if result else None

        return None

    def _split_fee_header_by_space(self, line: str) -> list[str]:
        """
        用空格分隔费用表头行

        输入: "收费项目名称 受理费 保全费 执行费 其他诉讼费"
        输出: ["收费项目名称", "受理费", "保全费", "执行费", "其他诉讼费"]
        """
        result: list[Any] = []
        # 定义费用关键词
        fee_keywords: list[Any] = [
            "收费项目名称",
            "收费项目",
            "受理费",
            "案件受理费",
            "申请费",
            "保全费",
            "财产保全费",
            "执行费",
            "其他诉讼费",
            "其他费用",
        ]

        remaining = line.strip()
        while remaining:
            matched = False
            for kw in sorted(fee_keywords, key=len, reverse=True):  # 先匹配长的
                if remaining.startswith(kw):
                    result.append(kw)
                    remaining = remaining[len(kw) :].strip()
                    matched = True
                    break
            if not matched:
                # 跳过无法识别的字符
                remaining = remaining[1:].strip() if remaining else ""

        return result

    def _split_amount_row_by_space(self, line: str) -> list[str]:
        """
        用空格分隔金额行

        输入: "金额 0 252.93 0 0"
        输出: ["金额", "0", "252.93", "0", "0"]
        """
        # 简单按空格分隔
        parts = line.split()
        return parts

    def _extract_vertical_table(self, text: str) -> dict[str, Decimal] | None:
        """
        提取纵向收费单
        """
        result: dict[str, Decimal] = {}
        cleaned_text = self._normalize_text(text)

        # 纵向表格模式:先找到费用项目名称
        fee_name_pattern = r"收费项目名称?\s*[|｜::\t\s]+([^\n\r|｜]+)"
        fee_name_match = re.search(fee_name_pattern, cleaned_text)

        if fee_name_match:
            field_name = self._match_fee_field(fee_name_match.group(1).strip())
            if field_name:
                amount = self._find_amount_in_vertical(cleaned_text)
                if amount is not None:
                    result[field_name] = amount

        # 也尝试匹配多个纵向条目
        self._extract_named_fees(cleaned_text, result)

        return result if result else None

    def _find_amount_in_vertical(self, text: str) -> Decimal | None | None:
        """从纵向表格中查找金额"""
        amount_patterns: list[Any] = [
            r"应收金额\s*[|｜::\t\s]*([\d,]+\.?\d*)\s*[((]",
            r"应收金额\s*[|｜::\t\s]*([\d,]+\.?\d*)",
            r"总金额\s*[((]?元?[))]?\s*[|｜::\t\s]*([\d,]+\.?\d*)",
            r"金额\s*[((]?元?[))]?\s*[|｜::\t\s]*([\d,]+\.?\d*)",
        ]
        for pattern in amount_patterns:
            match = re.search(pattern, text)
            if match:
                amount = self._parse_amount(match.group(1))
                if amount is not None:
                    return amount
        return None

    def _match_fee_field(self, fee_name: str) -> str | None | None:
        """
        匹配费用名称到字段名

        支持费用名称变体:
        - 案件受理费/受理费: return "acceptance_fee"
        - 申请费: return "application_fee"
        - 财产保全费/保全费: return "preservation_fee"
        - 执行费: return "execution_fee"
        - 其他诉讼费/其他费用: return "other_fee"
        """
        fee_name_clean = fee_name.strip()
        if "申请费" in fee_name_clean:
            return "application_fee"
        if "受理费" in fee_name_clean:
            return "acceptance_fee"
        if "财产保全费" in fee_name_clean or "保全费" in fee_name_clean:
            return "preservation_fee"
        if "执行费" in fee_name_clean:
            return "execution_fee"
        if "其他诉讼费" in fee_name_clean or "其他费用" in fee_name_clean:
            return "other_fee"

        return None

    def _extract_general_pattern(self, text: str) -> dict[str, Decimal] | None:
        """
        通用模式提取费用金额

        用于处理非标准表格格式的文本
        """
        result: dict[str, Decimal] = {}
        cleaned_text = self._normalize_text(text)

        # 首先尝试提取"应收金额"并确定费用类型
        payable_amount = self._extract_payable_amount(cleaned_text)
        if payable_amount is not None:
            field = self._determine_fee_type(cleaned_text)
            if field:
                result[field] = payable_amount

        # 继续尝试匹配其他费用项
        self._extract_named_fees(cleaned_text, result)

        return result if result else None

    def _extract_payable_amount(self, text: str) -> Decimal | None | None:
        """从文本中提取应收金额"""
        payable_patterns: list[Any] = [
            r"应收金额\s*[|｜::\t\s]*([\d,]+\.?\d*)\s*[((]",
            r"应收金额\s*[|｜::\t\s]*([\d,]+\.?\d*)",
        ]
        for pattern in payable_patterns:
            match = re.search(pattern, text)
            if match:
                amount = self._parse_amount(match.group(1))
                if amount is not None:
                    return amount
        return None

    def _determine_fee_type(self, text: str) -> str | None | None:
        """根据文本内容确定费用类型"""
        # 按优先级匹配(先匹配更具体的)
        type_checks: list[tuple[str, str]] = [
            ("案件受理费", "acceptance_fee"),
            ("申请费", "application_fee"),
            ("受理费", "acceptance_fee"),
            ("财产保全费", "preservation_fee"),
            ("保全费", "preservation_fee"),
            ("执行费", "execution_fee"),
        ]
        for keyword, field in type_checks:
            if keyword in text:
                return field
        # 无法确定类型时,检查收费项目名称
        fee_name_match = re.search(r"收费项目名称?\s*[|｜::\t\s]+([^\n\r|｜]+)", text)
        if fee_name_match:
            return self._match_fee_field(fee_name_match.group(1))
        return None

    def _extract_named_fees(self, text: str, result: dict[str, Decimal]) -> None:
        """从文本中按费用名称提取金额"""
        for fee_name, field_name in FEE_NAME_MAPPING.items():
            if field_name in result:
                continue
            patterns: list[Any] = [
                rf"{fee_name}\s*([\d,]+\.?\d*)\s*元",
                rf"{fee_name}\s*[:|:]\s*([\d,]+\.?\d*)",
                rf"{fee_name}\s*([\d,]+\.?\d*)\s*[((]",
                rf"{fee_name}为?\s*([\d,]+\.?\d*)\s*元?",
                rf"([\d,]+\.?\d*)\s*元?\s*{fee_name}",
            ]
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    amount = self._parse_amount(match.group(1))
                    if amount is not None:
                        result[field_name] = amount
                        break

    def _parse_amount(self, amount_str: str) -> Decimal | None | None:
        """
        解析金额字符串

        支持:
        - 普通数字: 4425.00
        - 千分位: 4,425.00
        - 带单位: 4425元
        - 中文大写旁的数字: 4,425.00(肆仟肆佰贰拾伍元整)

        Args:
            amount_str: 金额字符串

        Returns:
            Decimal: 解析后的金额,解析失败返回 None
        """
        if not amount_str:
            return None

        # 清理字符串
        cleaned = amount_str.strip()

        # 移除单位
        cleaned = re.sub(r"元|圆|￥|¥", "", cleaned)

        # 移除中文大写部分(括号内的内容)
        cleaned = re.sub(r"[((][^))]*[))]", "", cleaned)

        # 移除千分位分隔符
        cleaned = cleaned.replace(",", "")

        # 移除空格
        cleaned = cleaned.strip()

        # 提取数字部分
        number_match = re.match(r"^(\d+\.?\d*)$", cleaned)
        if not number_match:
            # 尝试从字符串中提取数字
            number_match = re.search(r"(\d+\.?\d*)", cleaned)
            if not number_match:
                return None
            cleaned = number_match.group(1)

        try:
            amount = Decimal(cleaned)
            # 验证金额合理性(非负数)
            if amount < 0:
                return None
            return amount
        except (InvalidOperation, ValueError):
            logger.warning("金额解析失败", extra={"original": amount_str, "cleaned": cleaned})
            return None

    def _normalize_text(self, text: str) -> str:
        """
        标准化文本

        统一分隔符和空白字符等
        """
        # 统一换行符
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")

        # 统一表格分隔符
        normalized = re.sub(r"[│┃┆┇┊┋]", "|", normalized)
        normalized = normalized.replace("｜", "|")

        # 统一冒号
        normalized = normalized.replace(":", ":")

        # 压缩多余空白(但保留换行)
        normalized = re.sub(r"[ \t]+", " ", normalized)

        return normalized

    def _parse_table_row(self, row: str) -> list[str]:
        """
        解析表格行,返回单元格列表
        """
        # 按分隔符拆分
        cells = re.split(r"[|｜\t]+", row)

        # 清理每个单元格
        result: list[Any] = []
        for cell in cells:
            cleaned = cell.strip()
            if cleaned:
                result.append(cleaned)

        return result

    def _build_result(
        self,
        fees: dict[str, Decimal],
        table_format: str,
        debug_info: dict[str, Any],
    ) -> FeeAmountResult:
        """
        构建提取结果
        """
        # 计算总金额
        total = Decimal("0")
        for amount in fees.values():
            if amount:
                total += amount

        return FeeAmountResult(
            acceptance_fee=fees.get("acceptance_fee"),
            application_fee=fees.get("application_fee"),
            preservation_fee=fees.get("preservation_fee"),
            execution_fee=fees.get("execution_fee"),
            other_fee=fees.get("other_fee"),
            total_fee=total if total > 0 else None,
            table_format=table_format,
            debug_info=debug_info,
        )
