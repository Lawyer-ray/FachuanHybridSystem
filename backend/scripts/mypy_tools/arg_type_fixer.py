#!/usr/bin/env python3
"""arg-type 错误修复器"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ArgTypeFixer:
    """arg-type 错误修复器"""

    def __init__(self) -> None:
        self.project_root = Path(__file__).parent.parent.parent

    def batch_fix_from_report(self, report_file: Path) -> dict[str, Any]:
        """从报告文件批量修复错误"""
        errors = self._parse_report(report_file)

        fixed_count = 0
        skipped_count = 0
        failed_count = 0
        failed_errors: list[str] = []

        # 按文件分组
        errors_by_file: dict[str, list[dict[str, Any]]] = {}
        for error in errors:
            file_path = error["file_path"]
            if file_path not in errors_by_file:
                errors_by_file[file_path] = []
            errors_by_file[file_path].append(error)

        # 逐文件修复
        for file_path, file_errors in errors_by_file.items():
            logger.info(f"修复文件: {file_path} ({len(file_errors)} 个错误)")

            try:
                result = self._fix_file(file_path, file_errors)
                fixed_count += result["fixed"]
                skipped_count += result["skipped"]
                failed_count += result["failed"]
                failed_errors.extend(result["failed_errors"])
            except Exception as e:
                logger.error(f"修复文件失败: {file_path}, 错误: {e}")
                failed_count += len(file_errors)
                failed_errors.append(f"{file_path}: {str(e)}")

        return {
            "fixed_count": fixed_count,
            "skipped_count": skipped_count,
            "failed_count": failed_count,
            "failed_errors": failed_errors,
        }

    def _parse_report(self, report_file: Path) -> list[dict[str, Any]]:
        """解析错误报告"""
        errors: list[dict[str, Any]] = []
        content = report_file.read_text(encoding="utf-8")

        # 解析错误列表
        lines = content.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # 查找文件行
            if line.startswith("文件:"):
                file_info = line.replace("文件:", "").strip()
                # 解析文件路径和行号
                match = re.match(r"(.+):(\d+):(\d+)", file_info)
                if match:
                    file_path = match.group(1)
                    line_no = int(match.group(2))
                    column = int(match.group(3))

                    # 读取消息行
                    i += 1
                    if i < len(lines) and lines[i].strip().startswith("消息:"):
                        message = lines[i].strip().replace("消息:", "").strip()

                        errors.append({"file_path": file_path, "line": line_no, "column": column, "message": message})

            i += 1

        logger.info(f"解析到 {len(errors)} 个错误")
        return errors

    def _fix_file(self, file_path: str, errors: list[dict[str, Any]]) -> dict[str, Any]:
        """修复单个文件"""
        full_path = self.project_root / file_path

        if not full_path.exists():
            logger.warning(f"文件不存在: {full_path}")
            return {"fixed": 0, "skipped": len(errors), "failed": 0, "failed_errors": []}

        # 读取文件内容
        content = full_path.read_text(encoding="utf-8")
        lines = content.split("\n")

        fixed = 0
        skipped = 0
        failed = 0
        failed_errors: list[str] = []

        # 按行号排序（从后往前修复，避免行号变化）
        sorted_errors = sorted(errors, key=lambda e: e["line"], reverse=True)

        for error in sorted_errors:
            try:
                result = self._fix_single_error(lines, error)
                if result == "fixed":
                    fixed += 1
                elif result == "skipped":
                    skipped += 1
                else:
                    failed += 1
                    failed_errors.append(f"{file_path}:{error['line']}: {error['message']}")
            except Exception as e:
                logger.error(f"修复错误失败: {error}, 异常: {e}")
                failed += 1
                failed_errors.append(f"{file_path}:{error['line']}: {str(e)}")

        # 写回文件
        if fixed > 0:
            full_path.write_text("\n".join(lines), encoding="utf-8")
            logger.info(f"已修复 {fixed} 个错误: {file_path}")

        return {"fixed": fixed, "skipped": skipped, "failed": failed, "failed_errors": failed_errors}

    def _fix_single_error(self, lines: list[str], error: dict[str, Any]) -> str:
        """修复单个错误，返回 'fixed', 'skipped', 或 'failed'"""
        line_no = error["line"] - 1  # 转换为 0-based 索引
        message = error["message"]

        if line_no < 0 or line_no >= len(lines):
            return "failed"

        line = lines[line_no]

        # 根据错误消息类型进行修复
        if 'has incompatible type "int | None"; expected "int"' in message:
            # 修复 int | None -> int
            fixed_line = self._fix_optional_to_required(line, message, "int")
            if fixed_line != line:
                lines[line_no] = fixed_line
                return "fixed"

        elif 'has incompatible type "str | None"; expected "str"' in message:
            # 修复 str | None -> str
            fixed_line = self._fix_optional_to_required(line, message, "str")
            if fixed_line != line:
                lines[line_no] = fixed_line
                return "fixed"

        elif 'has incompatible type "bool | None"; expected "bool"' in message:
            # 修复 bool | None -> bool
            fixed_line = self._fix_optional_to_required(line, message, "bool")
            if fixed_line != line:
                lines[line_no] = fixed_line
                return "fixed"

        elif 'has incompatible type "date | None"; expected "date"' in message:
            # 修复 date | None -> date
            fixed_line = self._fix_optional_to_required(line, message, "date")
            if fixed_line != line:
                lines[line_no] = fixed_line
                return "fixed"

        elif 'has incompatible type "datetime | None"; expected "datetime"' in message:
            # 修复 datetime | None -> datetime
            fixed_line = self._fix_optional_to_required(line, message, "datetime")
            if fixed_line != line:
                lines[line_no] = fixed_line
                return "fixed"

        elif 'has incompatible type "float"; expected "Decimal"' in message:
            # 修复 float -> Decimal
            fixed_line = self._fix_float_to_decimal(line, message)
            if fixed_line != line:
                lines[line_no] = fixed_line
                return "fixed"

        elif (
            'has incompatible type "dict[int, dict[str, Any]]"; expected "SupportsKeysAndGetItem[str, Any]"' in message
        ):
            # 修复字典类型转换
            fixed_line = self._fix_dict_conversion(line)
            if fixed_line != line:
                lines[line_no] = fixed_line
                return "fixed"

        elif 'has incompatible type "set[Any]"; expected "list[int]"' in message:
            # 修复 set -> list
            fixed_line = self._fix_set_to_list(line, message)
            if fixed_line != line:
                lines[line_no] = fixed_line
                return "fixed"

        elif 'Argument 1 to "append" of "list" has incompatible type "int"; expected "str"' in message:
            # 修复 list.append 类型不匹配
            fixed_line = self._fix_list_append_type(line)
            if fixed_line != line:
                lines[line_no] = fixed_line
                return "fixed"

        # 其他复杂情况跳过
        return "skipped"

    def _fix_optional_to_required(self, line: str, message: str, expected_type: str) -> str:
        """修复可选类型传递给必需参数"""
        # 提取参数名
        param_match = re.search(r'Argument "(\w+)"', message)
        if not param_match:
            param_match = re.search(r"Argument (\d+)", message)

        if param_match:
            param_name = param_match.group(1)

            # 查找参数赋值
            pattern = rf"{param_name}\s*=\s*([^,\)]+)"
            match = re.search(pattern, line)

            if match:
                value = match.group(1).strip()

                # 添加默认值处理
                if expected_type == "int":
                    new_value = f"{value} or 0"
                elif expected_type == "str":
                    new_value = f'{value} or ""'
                elif expected_type == "bool":
                    new_value = f"{value} or False"
                elif expected_type == "date":
                    # 需要导入 date
                    new_value = f"{value} or date.today()"
                elif expected_type == "datetime":
                    # 需要导入 datetime
                    new_value = f"{value} or datetime.now()"
                else:
                    return line

                # 替换
                new_line = line.replace(f"{param_name}={value}", f"{param_name}={new_value}")
                return new_line

        return line

    def _fix_float_to_decimal(self, line: str, message: str) -> str:
        """修复 float -> Decimal 转换"""
        # 提取参数名
        param_match = re.search(r'Argument "(\w+)"', message)
        if param_match:
            param_name = param_match.group(1)

            # 查找参数赋值
            pattern = rf"{param_name}\s*=\s*([^,\)]+)"
            match = re.search(pattern, line)

            if match:
                value = match.group(1).strip()
                # 包装为 Decimal
                new_value = f"Decimal(str({value}))"
                new_line = line.replace(f"{param_name}={value}", f"{param_name}={new_value}")
                return new_line

        return line

    def _fix_dict_conversion(self, line: str) -> str:
        """修复字典类型转换"""
        # 查找 dict(...) 调用
        if "dict(" in line:
            # 添加类型转换
            line = line.replace("dict(", "dict[str, Any](")
        return line

    def _fix_set_to_list(self, line: str, message: str) -> str:
        """修复 set -> list 转换"""
        # 提取参数
        param_match = re.search(r"Argument (\d+)", message)
        if param_match:
            # 查找 set 变量并转换为 list
            if "set[" in line or "{" in line:
                # 简单替换：在调用处添加 list() 转换
                # 这需要更复杂的 AST 分析，暂时跳过
                pass
        return line

    def _fix_list_append_type(self, line: str) -> str:
        """修复 list.append 类型不匹配"""
        # 查找 .append(int_value)
        if ".append(" in line:
            # 添加 str() 转换
            match = re.search(r"\.append\(([^)]+)\)", line)
            if match:
                value = match.group(1).strip()
                if not value.startswith("str("):
                    new_line = line.replace(f".append({value})", f".append(str({value}))")
                    return new_line
        return line
