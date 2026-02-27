from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# 匹配各方名称的正则 (甲乙丙丁)
_PARTY_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "party_a": [
        re.compile(r"甲\s*方[：:]\s*(.+?)(?:\s|$|（)"),
        re.compile(r"甲\s*方.*?[：:]\s*(.+?)(?:\s|$|（)"),
    ],
    "party_b": [
        re.compile(r"乙\s*方[：:]\s*(.+?)(?:\s|$|（)"),
        re.compile(r"乙\s*方.*?[：:]\s*(.+?)(?:\s|$|（)"),
    ],
    "party_c": [
        re.compile(r"丙\s*方[：:]\s*(.+?)(?:\s|$|（)"),
        re.compile(r"丙\s*方.*?[：:]\s*(.+?)(?:\s|$|（)"),
    ],
    "party_d": [
        re.compile(r"丁\s*方[：:]\s*(.+?)(?:\s|$|（)"),
        re.compile(r"丁\s*方.*?[：:]\s*(.+?)(?:\s|$|（)"),
    ],
}

# 各方中文标签
PARTY_LABELS: dict[str, str] = {
    "party_a": "甲方",
    "party_b": "乙方",
    "party_c": "丙方",
    "party_d": "丁方",
}


class PartyIdentifier:
    """当事人识别器，支持甲乙丙丁四方"""

    def identify_parties(self, paragraphs: list[str]) -> dict[str, str]:
        """通过正则从合同文本中识别各方名称，返回 {party_key: name}，仅包含识别到的"""
        text = "\n".join(paragraphs)
        result: dict[str, str] = {}
        for key, patterns in _PARTY_PATTERNS.items():
            name = self._find_party(text, patterns)
            if name:
                logger.info("识别%s: %s", PARTY_LABELS[key], name)
                result[key] = name
            else:
                logger.debug("未识别到%s", PARTY_LABELS[key])
        return result

    @staticmethod
    def _find_party(text: str, patterns: list[re.Pattern[str]]) -> str:
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                name = match.group(1).strip().rstrip("，。,.")
                if name:
                    return name
        return ""
