"""当事人名称提取与清洗。"""

from __future__ import annotations

from .patterns import (
    _BIRTH_DATE_PATTERN,
    _CREDIT_CODE_FALLBACK_PATTERN,
    _ETHNICITY_PATTERN,
    _ID_NUMBER_FALLBACK_PATTERN,
    _LEADING_NAME_BEFORE_FIELD_PATTERN,
    _LEADING_PERSON_NAME_PATTERN,
    _LEGAL_ENTITY_NAME_PATTERN,
    _NAME_FIELD_PATTERN,
    _NATURAL_PERSON_NAME_PATTERN,
    _NON_NAME_KEYWORDS,
    _PHONE_IN_NAME_PATTERN,
    _ROLE_LABELS,
    _ROLE_NAME_FALLBACK_PATTERN,
    _ROLE_NAME_PATTERNS,
    _ROLE_PREFIX_CLEANUP_PATTERN,
    _SMART_NAME_PATTERN,
    _TRAILING_BIRTH_INFO_PATTERN,
    _TRAILING_GENDER_PATTERN,
    _WHITESPACE_PATTERN,
)


def _extract_name_smart(text: str) -> str | None:
    """智能提取名称"""
    name = _extract_name(text)
    if name:
        return name

    # 支持 "名称: xxx" 格式
    match = _NAME_FIELD_PATTERN.search(text)
    if match:
        name = _clean_name_candidate(match.group(1))
        if _is_valid_name_candidate(name):
            return name

    match2 = _SMART_NAME_PATTERN.search(text)
    if match2:
        name = _clean_name_candidate(_WHITESPACE_PATTERN.sub("", match2.group(1).strip()))
        if _is_valid_name_candidate(name):
            return name

    leading_name_match = _LEADING_NAME_BEFORE_FIELD_PATTERN.search(text)
    if leading_name_match:
        name = _clean_name_candidate(leading_name_match.group(1))
        if _is_valid_name_candidate(name):
            return name

    # 兼容无冒号的角色写法：如 "被告 张三，男..."
    role_match = _ROLE_NAME_FALLBACK_PATTERN.search(text)
    if role_match:
        name = _clean_name_candidate(role_match.group(1))
        if _is_valid_name_candidate(name):
            return name

    leading_person_match = _LEADING_PERSON_NAME_PATTERN.search(text)
    if leading_person_match:
        name = _clean_name_candidate(leading_person_match.group(1))
        if _is_valid_name_candidate(name):
            return name

    # 兼容仅出现公司全称的文本
    legal_name_match = _LEGAL_ENTITY_NAME_PATTERN.search(text)
    if legal_name_match:
        name = _clean_name_candidate(legal_name_match.group(1))
        if _is_valid_name_candidate(name):
            return name

    # 兼容自然人常见写法：如 "李四，男..."
    person_match = _NATURAL_PERSON_NAME_PATTERN.search(text)
    if person_match:
        name = _clean_name_candidate(person_match.group(1))
        if _is_valid_name_candidate(name):
            return name

    # 兜底：第一行即名称
    first_line_name = _extract_name_from_first_meaningful_line(text)
    if first_line_name:
        return first_line_name

    return None


def _clean_name_candidate(name_part: str) -> str:
    """清洗名称候选值（保留公司括号地名，不做激进删减）"""
    name = _ROLE_PREFIX_CLEANUP_PATTERN.sub("", name_part.strip())
    name = _PHONE_IN_NAME_PATTERN.sub(" ", name)
    name = _ETHNICITY_PATTERN.sub("", name)
    name = _BIRTH_DATE_PATTERN.sub("", name)
    name = _TRAILING_BIRTH_INFO_PATTERN.sub("", name)
    name = _TRAILING_GENDER_PATTERN.sub("", name)
    return name.strip().strip("，,；;。")


def _is_valid_name_candidate(name: str) -> bool:
    """判断名称候选值是否有效，避免把字段值误判为名称"""
    if not name or len(name) < 2 or len(name) > 120:
        return False

    if any(keyword in name for keyword in _NON_NAME_KEYWORDS):
        return False
    if any(keyword.startswith(name) for keyword in _NON_NAME_KEYWORDS):
        return False
    if any(role.startswith(name) for role in _ROLE_LABELS):
        return False

    compact = _WHITESPACE_PATTERN.sub("", name)
    if not compact:
        return False
    if compact.isdigit():
        return False
    if _ID_NUMBER_FALLBACK_PATTERN.fullmatch(compact):
        return False
    if _CREDIT_CODE_FALLBACK_PATTERN.fullmatch(compact) and any(ch.isalpha() for ch in compact):
        return False
    return True


def _extract_name_from_first_meaningful_line(text: str) -> str | None:
    """从第一条有效信息行提取名称"""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = _clean_name_candidate(line)
        if _is_valid_name_candidate(line):
            return line

    return None


def _extract_name(text: str) -> str | None:
    """提取名称"""
    # 定义角色标签模式（支持 甲方（原告）、乙方（被告）等格式）
    role_patterns = _ROLE_NAME_PATTERNS

    for compiled in role_patterns:
        match = compiled.search(text)
        if match:
            name = _clean_name_candidate(match.group(1))
            if _is_valid_name_candidate(name):
                return name.strip()

    return None
