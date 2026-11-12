"""响应解析 Mixin"""

import json
import logging
import re
from datetime import datetime
from typing import Any, cast

from apps.core.llm.structured_output import extract_json_text

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
                logger.warning("无法从响应中提取 JSON: %s", content[:200])
                return result
            case_number = parsed.get("case_number")
            if case_number and case_number.lower() != "null":
                result["case_number"] = self._normalize_case_number(case_number)
            court_time = parsed.get("court_time")
            if court_time and court_time.lower() != "null":
                result["court_time"] = self._parse_datetime(court_time)
            return result
        except Exception as e:
            logger.warning("解析传票响应失败: %s", e)
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
                logger.warning("无法从响应中提取 JSON: %s", content[:200])
                return result
            case_number = parsed.get("case_number")
            if case_number and case_number.lower() != "null":
                result["case_number"] = self._normalize_case_number(case_number)
            deadline = parsed.get("preservation_deadline")
            if deadline and deadline.lower() != "null":
                result["preservation_deadline"] = self._parse_date(deadline)
            return result
        except Exception as e:
            logger.warning("解析执行裁定书响应失败: %s", e)
            return result

    def _extract_json_from_response(self, content: str) -> dict[str, Any] | None:
        """从响应内容中提取 JSON 对象；非对象载荷或解析失败返回 None。

        提取逻辑统一走 ``extract_json_text``，这里只保留「必须是 JSON 对象」
        这层业务约束——调用方随后直接 ``.get(...)``。
        """
        snippet = extract_json_text(content)
        if snippet is None:
            return None
        loaded = json.loads(snippet)
        if not isinstance(loaded, dict):
            return None
        return cast(dict[str, Any], loaded)

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
        logger.warning("无法解析日期时间: %s", datetime_str)
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
        logger.warning("无法解析日期: %s", date_str)
        return None
