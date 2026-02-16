"""ErrorAnalyzer - 分析和分类mypy错误，生成修复优先级报告"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)


@dataclass
class ErrorInfo:
    """错误信息数据类"""

    file_path: str
    line_number: int
    error_code: str
    message: str
    context: str


class ErrorAnalyzer:
    """分析mypy输出，按错误类型分组，生成修复优先级报告"""

    # 错误优先级映射（P0-P3）
    PRIORITY_MAP: dict[str, Literal["P0", "P1", "P2", "P3"]] = {
        # P0 - 高频基础错误（快速修复）
        "type-arg": "P0",
        "name-defined": "P0",
        "redundant-cast": "P0",
        "unused-ignore": "P0",
        # P1 - 函数签名错误（中等修复）
        "no-untyped-def": "P1",
        "assignment": "P1",
        "no-any-return": "P1",
        # P2 - 属性访问错误（复杂修复）
        "attr-defined": "P2",
        "union-attr": "P2",
        # P3 - 其他错误（按需修复）
        "no-redef": "P3",
    }

    def __init__(self) -> None:
        """初始化ErrorAnalyzer"""
        # 匹配mypy输出格式：file.py:123:45: error: message [error-code]
        self._error_pattern = re.compile(
            r"^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s+"
            r"(?P<severity>\w+):\s+(?P<message>.+?)\s+\[(?P<code>[^\]]+)\]"
        )

    def parse_mypy_output(self, output_file: str) -> dict[str, list[ErrorInfo]]:
        """
        解析mypy输出文件，按错误类型分组

        Args:
            output_file: mypy输出文件路径

        Returns:
            按错误类型分组的错误字典
        """
        output_path = Path(output_file)
        if not output_path.exists():
            logger.error(f"输出文件不存在: {output_file}")
            return {}

        content = output_path.read_text(encoding="utf-8")

        # 处理被截断的行：将连续的行合并
        lines = content.strip().split("\n")
        merged_lines: list[str] = []
        current_line = ""

        for line in lines:
            # 如果行以文件路径开头（包含.py:数字:数字:），这是新的错误行
            if re.match(r"^[^:]+\.py:\d+:\d+:", line):
                if current_line:
                    merged_lines.append(current_line)
                current_line = line
            else:
                # 否则，这是上一行的延续
                current_line += " " + line.strip()

        # 添加最后一行
        if current_line:
            merged_lines.append(current_line)

        errors: dict[str, list[ErrorInfo]] = defaultdict(list)

        for line in merged_lines:
            line = line.strip()
            if not line:
                continue

            match = self._error_pattern.match(line)
            if match:
                groups = match.groupdict()
                error_code = groups["code"]

                error_info = ErrorInfo(
                    file_path=groups["file"],
                    line_number=int(groups["line"]),
                    error_code=error_code,
                    message=groups["message"],
                    context="",  # 上下文需要单独读取文件获取
                )

                errors[error_code].append(error_info)

        logger.info(f"解析完成，共 {sum(len(v) for v in errors.values())} 个错误，{len(errors)} 种类型")
        return dict(errors)

    def generate_priority_report(self, errors: dict[str, list[ErrorInfo]]) -> str:
        """
        生成修复优先级报告

        Args:
            errors: 按错误类型分组的错误字典

        Returns:
            格式化的优先级报告文本
        """
        # 按优先级分组
        by_priority: dict[str, list[tuple[str, int]]] = {
            "P0": [],
            "P1": [],
            "P2": [],
            "P3": [],
        }

        for error_code, error_list in errors.items():
            priority = self.PRIORITY_MAP.get(error_code, "P3")
            by_priority[priority].append((error_code, len(error_list)))

        # 生成报告
        lines = [
            "Mypy错误修复优先级报告",
            "=" * 60,
            "",
        ]

        total_errors = sum(len(v) for v in errors.values())
        lines.append(f"总错误数: {total_errors}")
        lines.append("")

        for priority in ["P0", "P1", "P2", "P3"]:
            priority_errors = by_priority[priority]
            if not priority_errors:
                continue

            priority_total = sum(count for _, count in priority_errors)

            lines.append(f"{priority} - {self._get_priority_desc(priority)} ({priority_total}个)")
            lines.append("-" * 60)

            # 按数量排序
            priority_errors.sort(key=lambda x: x[1], reverse=True)

            for error_code, count in priority_errors:
                lines.append(f"  {error_code:20s} {count:5d}个")

            lines.append("")

        return "\n".join(lines)

    def get_fixable_errors(self, error_type: str, errors: dict[str, list[ErrorInfo]]) -> list[ErrorInfo]:
        """
        获取指定类型的可修复错误

        Args:
            error_type: 错误类型代码
            errors: 按错误类型分组的错误字典

        Returns:
            该类型的错误列表
        """
        return errors.get(error_type, [])

    def _get_priority_desc(self, priority: str) -> str:
        """获取优先级描述"""
        desc_map = {
            "P0": "高频基础错误（快速修复）",
            "P1": "函数签名错误（中等修复）",
            "P2": "属性访问错误（复杂修复）",
            "P3": "其他错误（按需修复）",
        }
        return desc_map.get(priority, "未知优先级")
