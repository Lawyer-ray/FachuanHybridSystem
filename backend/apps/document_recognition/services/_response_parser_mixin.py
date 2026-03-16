"""响应解析 Mixin"""

import json
import logging
import re
from datetime import datetime
from typing import Any, cast

logger = logging.getLogger("apps.document_recognition")


class ResponseParserMixin:
    """Ollama 响应解析 Mixin"""

    def _normalize_case_number(self, case_number: str) -> str:
        raise NotImplementedError

    def _parse_summons_response(self, response: dict[str, Any]) -> dict[str, Any]:
        """解析传票信息提取响应"""
        result: dict[str, Any] = {"case_number": None, "court_time": None}
        try:
            if "message" not in response or "content" not in response["message"]:
                logger.warning("Ollama 响应格式异常")
                return result
            content = response["message"]["content"]
            parsed = self._extract_json_from_response(content)
            if parsed is None:
                logger.warning(f"无法从响应中提取 JSON: {content[:200]}")
                return result
            case_number = parsed.get("case_number")
            if case_number and case_number.lower() != "null":
                result["case_number"] = self._normalize_case_number(case_number)
            court_time = parsed.get("court_time")
            if court_time and court_time.lower() != "null":
                result["court_time"] = self._parse_datetime(court_time)
            return result
        except Exception as e:
            logger.warning(f"解析传票响应失败: {e!s}")
            return result

    def _parse_execution_response(self, response: dict[str, Any]) -> dict[str, Any]:
        """解析执行裁定书信息提取响应"""
        result: dict[str, Any] = {"case_number": None, "preservation_deadline": None}
        try:
            if "message" not in response or "content" not in response["message"]:
                logger.warning("Ollama 响应格式异常")
                return result
            content = response["message"]["content"]
            parsed = self._extract_json_from_response(content)
            if parsed is None:
                logger.warning(f"无法从响应中提取 JSON: {content[:200]}")
                return result
            case_number = parsed.get("case_number")
            if case_number and case_number.lower() != "null":
                result["case_number"] = self._normalize_case_number(case_number)
            deadline = parsed.get("preservation_deadline")
            if deadline and deadline.lower() != "null":
                result["preservation_deadline"] = self._parse_date(deadline)
            return result
        except Exception as e:
            logger.warning(f"解析执行裁定书响应失败: {e!s}")
            return result

    def _extract_json_from_response(self, content: str) -> dict[str, Any] | None:
        """从响应内容中提取 JSON"""
        content = content.strip()
        try:
            return cast(dict[str, Any], json.loads(content))
        except json.JSONDecodeError:
            pass
        start_idx = content.find("{")
        end_idx = content.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            try:
                return cast(dict[str, Any], json.loads(content[start_idx : end_idx + 1]))
            except json.JSONDecodeError:
                pass
        if "```json" in content:
            try:
                json_start = content.index("```json") + 7
                json_end = content.index("```", json_start)
                return cast(dict[str, Any], json.loads(content[json_start:json_end].strip()))
            except (ValueError, json.JSONDecodeError):
                pass
        if "```" in content:
            try:
                json_start = content.index("```") + 3
                json_end = content.index("```", json_start)
                return cast(dict[str, Any], json.loads(content[json_start:json_end].strip()))
            except (ValueError, json.JSONDecodeError):
                pass
        return None

    def _parse_datetime(self, datetime_str: str) -> datetime | None:
        """解析日期时间字符串"""
        if not datetime_str:
            return None
        datetime_str = datetime_str.strip()
        formats = [
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

    def _parse_date(self, date_str: str) -> datetime | None:
        """解析日期字符串"""
        if not date_str:
            return None
        date_str = date_str.strip()
        formats = ["%Y-%m-%d", "%Y年%m月%d日", "%Y/%m/%d", "%Y.%m.%d"]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
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
