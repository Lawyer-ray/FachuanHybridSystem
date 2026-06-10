from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_PARTY_KEY_MAP: dict[str, str] = {"甲": "party_a", "乙": "party_b", "丙": "party_c", "丁": "party_d"}

# 匹配 "xxx（以下简称甲方）" 格式（公司名在前，方标签在括号内）
_ABBREV_PATTERN: re.Pattern[str] = re.compile(r"(?:[^：:]*?[：:]\s*)?([^：:]+?)\s*（(?:以下简称)([甲乙丙丁])方）")

# 匹配各方名称的正则 (甲乙丙丁) —— 标签在前的格式
_PARTY_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "party_a": [
        re.compile(r"甲\s*方[：:]\s*(.+?)(?:\s*$|[\s（(])"),
        re.compile(r"甲\s*方.*?[：:]\s*(.+?)(?:\s*$|[\s（(])"),
    ],
    "party_b": [
        re.compile(r"乙\s*方[：:]\s*(.+?)(?:\s*$|[\s（(])"),
        re.compile(r"乙\s*方.*?[：:]\s*(.+?)(?:\s*$|[\s（(])"),
    ],
    "party_c": [
        re.compile(r"丙\s*方[：:]\s*(.+?)(?:\s*$|[\s（(])"),
        re.compile(r"丙\s*方.*?[：:]\s*(.+?)(?:\s*$|[\s（(])"),
    ],
    "party_d": [
        re.compile(r"丁\s*方[：:]\s*(.+?)(?:\s*$|[\s（(])"),
        re.compile(r"丁\s*方.*?[：:]\s*(.+?)(?:\s*$|[\s（(])"),
    ],
}

# 各方中文标签
PARTY_LABELS: dict[str, str] = {
    "party_a": "甲方",
    "party_b": "乙方",
    "party_c": "丙方",
    "party_d": "丁方",
}


class PartyIdentifier:  # pragma: no cover
    """当事人识别器，支持甲乙丙丁四方"""

    def identify_parties(self, paragraphs: list[str]) -> dict[str, str]:  # pragma: no cover
        """通过正则从合同文本中识别各方名称，返回 {party_key: name}，仅包含识别到的"""
        text = "\n".join(paragraphs)
        result: dict[str, str] = {}

        # 优先匹配 "xxx（以下简称甲方）" 格式
        for m in _ABBREV_PATTERN.finditer(text):
            party_char = m.group(2)
            name = m.group(1).strip().rstrip("，。,.")
            key = _PARTY_KEY_MAP.get(party_char, "")
            if key and name and key not in result:
                logger.info("识别%s（以下简称格式）: %s", PARTY_LABELS[key], name)
                result[key] = name

        # 再用传统模式补充未识别的方
        for key, patterns in _PARTY_PATTERNS.items():
            if key in result:
                continue
            name = self._find_party(text, patterns)
            if name:
                logger.info("识别%s: %s", PARTY_LABELS[key], name)
                result[key] = name
            else:
                logger.debug("未识别到%s", PARTY_LABELS[key])
        return result

    @staticmethod
    def _find_party(text: str, patterns: list[re.Pattern[str]]) -> str:  # pragma: no cover
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                name = match.group(1).strip().rstrip("，。,.")
                if name:
                    return name
        return ""
