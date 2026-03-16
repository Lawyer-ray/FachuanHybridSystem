"""案号提取 Mixin"""

import logging
import re

logger = logging.getLogger("apps.document_recognition")

# 案号正则表达式模式
CASE_NUMBER_PATTERNS = [
    r"（(\d{4})）([^\s（）\(\)]{2,20}?)(\d+)号",
    r"\((\d{4})\)([^\s（）\(\)]{2,20}?)(\d+)号",
    r"(\d{4})([^\d\s]{1}[^\s（）\(\)]{1,19}?)(\d+)号",
]


class CaseNumberMixin:
    """案号提取 Mixin"""

    def _extract_case_number_by_regex(self, text: str) -> str | None:
        """使用正则表达式从文本中提取案号"""
        if not text:
            return None
        for pattern in CASE_NUMBER_PATTERNS:
            matches = re.findall(pattern, text)
            if matches:
                match = matches[0]
                if len(match) == 3:
                    year, court_type, seq = match
                    case_number = f"（{year}）{court_type}{seq}号"
                    normalized = self._normalize_case_number(case_number)
                    logger.info(f"正则提取到案号: {normalized} (原始匹配: {match})")
                    return normalized
        logger.debug("正则未能提取到案号")
        return None

    def _normalize_case_number(self, case_number: str) -> str:
        """标准化案号格式"""
        if not case_number:
            return case_number
        case_number = case_number.strip()
        case_number = case_number.replace("（", "(").replace("）", ")")
        no_bracket_pattern = r"^(\d{4})([^\d\(\)])"
        match = re.match(no_bracket_pattern, case_number)
        if match:
            year = match.group(1)
            rest = case_number[4:]
            case_number = f"({year}){rest}"
        case_number = case_number.replace("(", "（").replace(")", "）")
        return case_number
