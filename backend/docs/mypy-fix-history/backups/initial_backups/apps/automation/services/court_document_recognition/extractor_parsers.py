"""
信息提取器解析模块

提供响应解析和格式化方法.
作为 InfoExtractor 的 Mixin 使用.
"""

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger("apps.automation")


class ExtractorParsersMixin:
    """信息提取器解析 Mixin

    提供解析相关的方法:
    - Ollama 响应解析
    - JSON 提取
    - 案号标准化
    - 日期时间解析
    """

    def _parse_summons_response(self, response: dict[str, Any]) -> dict[str, Any]:
        """
        解析传票信息提取响应

        Args:
            response: Ollama API 响应

        Returns:
            Dict[str, Any]: 提取的信息
        """
        result: dict[str, Any] = {}

        try:
            if "message" not in response or "content" not in response["message"]:
                logger.warning("Ollama 响应格式异常")
                return result

            content = response["message"]["content"]
            parsed = self._extract_json_from_response(content)

            if parsed is None:
                logger.warning(f"无法从响应中提取 JSON: {content[:200]}")
                return result

            # 提取案号
            case_number = parsed.get("case_number")
            if case_number and case_number.lower() != "null":
                result["case_number"] = self._normalize_case_number(case_number)

            # 提取开庭时间
            court_time = parsed.get("court_time")
            if court_time and court_time.lower() != "null":
                result["court_time"] = self._parse_datetime(court_time)

            return result

        except Exception as e:
            logger.warning(f"解析传票响应失败: {e!s}")
            return result

    def _parse_execution_response(self, response: dict[str, Any]) -> dict[str, Any]:
        """
        解析执行裁定书信息提取响应

        Args:
            response: Ollama API 响应

        Returns:
            Dict[str, Any]: 提取的信息
        """
        result: dict[str, Any] = {}

        try:
            if "message" not in response or "content" not in response["message"]:
                logger.warning("Ollama 响应格式异常")
                return result

            content = response["message"]["content"]
            parsed = self._extract_json_from_response(content)

            if parsed is None:
                logger.warning(f"无法从响应中提取 JSON: {content[:200]}")
                return result

            # 提取案号
            case_number = parsed.get("case_number")
            if case_number and case_number.lower() != "null":
                result["case_number"] = self._normalize_case_number(case_number)

            # 提取保全到期时间
            deadline = parsed.get("preservation_deadline")
            if deadline and deadline.lower() != "null":
                result["preservation_deadline"] = self._parse_date(deadline)

            return result

        except Exception as e:
            logger.warning(f"解析执行裁定书响应失败: {e!s}")
            return result

    def _extract_json_from_response(self, content: str) -> dict[str, Any] | None:
        """
        从响应内容中提取 JSON

        支持处理包含额外文本的响应.

        Args:
            content: 响应内容

        Returns:
            Optional[dict]: 解析出的 JSON 对象,失败返回 None
        """
        content = content.strip()

        # 直接尝试解析
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # 尝试提取 JSON 块
        start_idx = content.find("{")
        end_idx = content.rfind("}")

        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_str = content[start_idx : end_idx + 1]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass

        # 尝试处理 markdown 代码块
        if "```json" in content:
            try:
                json_start = content.index("```json") + 7
                json_end = content.index("```", json_start)
                json_str = content[json_start:json_end].strip()
                return json.loads(json_str)
            except (ValueError, json.JSONDecodeError):
                pass

        if "```" in content:
            try:
                json_start = content.index("```") + 3
                json_end = content.index("```", json_start)
                json_str = content[json_start:json_end].strip()
                return json.loads(json_str)
            except (ValueError, json.JSONDecodeError):
                pass

        return None

    def _normalize_case_number(self, case_number: str) -> str:
        """
        标准化案号格式

        处理常见的案号格式变体,统一为标准格式.
        例如:2025粤0604民初41257号: case_number: 原始案号字符串

        Returns:
            str: 标准化后的案号
        """
        if not case_number:
            return case_number

        # 去除首尾空白
        case_number = case_number.strip()

        # 将全角括号转换为半角(统一处理)
        case_number = case_number.replace("(", "(").replace(")", ")")

        # 检查是否缺少括号:以年份开头但没有括号
        no_bracket_pattern = r"^(\d{4})([^\d\(\)])"
        match = re.match(no_bracket_pattern, case_number)
        if match:
            year = match.group(1)
            rest = case_number[4:]
            case_number = f"({year}){rest}"

        # 将半角括号转换为中文括号(标准格式)
        case_number = case_number.replace("(", "(").replace(")", ")")

        return case_number

    def _parse_datetime(self, datetime_str: str) -> Optional[datetime | None]:
        """
        解析日期时间字符串

        支持多种常见格式.

        Args:
            datetime_str: 日期时间字符串

        Returns:
            Optional[datetime]: 解析后的 datetime 对象,失败返回 None
        """
        if not datetime_str:
            return None

        datetime_str = datetime_str.strip()

        # 支持的日期时间格式
        formats: list[Any] = [
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y年%m月%d日 %H:%M",
            "%Y年%m月%d日 %H时%M分",
            "%Y年%m月%d日%H时%M分",
            "%Y/%m/%d %H:%M",
            "%Y.%m.%d %H:%M",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(datetime_str, fmt)
            except ValueError:
                continue

        # 尝试使用正则表达式提取
        pattern_cn = r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2})时(\d{1,2})分?"
        match = re.search(pattern_cn, datetime_str)
        if match:
            try:
                year, month, day, hour, minute = map(int, match.groups())
                return datetime(year, month, day, hour, minute)
            except ValueError:
                pass

        pattern_std = r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\s+(\d{1,2}):(\d{1,2})"
        match = re.search(pattern_std, datetime_str)
        if match:
            try:
                year, month, day, hour, minute = map(int, match.groups())
                return datetime(year, month, day, hour, minute)
            except ValueError:
                pass

        logger.warning(f"无法解析日期时间: {datetime_str}")
        return None

    def _parse_date(self, date_str: str) -> Optional[datetime | None]:
        """
        解析日期字符串

        支持多种常见格式.

        Args:
            date_str: 日期字符串

        Returns:
            Optional[datetime]: 解析后的 datetime 对象(时间部分为 00:00:00),失败返回 None
        """
        if not date_str:
            return None

        date_str = date_str.strip()

        # 支持的日期格式
        formats: list[Any] = [
            "%Y-%m-%d",
            "%Y年%m月%d日",
            "%Y/%m/%d",
            "%Y.%m.%d",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        # 尝试使用正则表达式提取
        pattern = r"(\d{4})[-年/.](\d{1,2})[-月/.](\d{1,2})"
        match = re.search(pattern, date_str)
        if match:
            try:
                year, month, day = map(int, match.groups())
                return datetime(year, month, day)
            except ValueError:
                pass

        logger.warning(f"无法解析日期: {date_str}")
        return None
