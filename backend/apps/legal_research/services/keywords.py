from __future__ import annotations

import re

KEYWORD_INPUT_HELP_TEXT = "支持多关键词：可用空格、逗号(,，)、分号(;；)、顿号(、)或换行分隔。系统会自动合并为联合检索。"


def normalize_keyword_query(raw_keyword: str) -> str:
    text = (raw_keyword or "").strip()
    if not text:
        return ""

    parts = re.split(r"[,\n\r\t;；，、\s]+", text)
    normalized: list[str] = []
    seen: set[str] = set()

    for part in parts:
        keyword = part.strip()
        if not keyword or keyword in seen:
            continue
        seen.add(keyword)
        normalized.append(keyword)

    return " ".join(normalized)
