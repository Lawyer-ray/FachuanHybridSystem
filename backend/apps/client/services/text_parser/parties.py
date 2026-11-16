"""当事人文本解析入口与多当事人分块。"""

from __future__ import annotations

import re
from typing import Any

from .fields import (
    _determine_client_type,
    _empty_result,
    _extract_address,
    _extract_credit_code,
    _extract_id_number,
    _extract_legal_representative,
    _extract_phone,
)
from .names import _clean_name_candidate, _extract_name, _extract_name_smart, _is_valid_name_candidate
from .patterns import (
    _ENUMERATION_PREFIX_PATTERN,
    _FIELD_KEYWORDS_PATTERN,
    _FULL_STOP_BREAK_PATTERN,
    _INLINE_BREAK_PATTERN,
    _PHONE_FALLBACK_PATTERN,
    _ROLE_SPLIT_PATTERNS,
)


def parse_client_text(text: str) -> dict[str, Any]:
    """
    解析当事人文本信息，支持有换行和无换行格式
    """
    if not text or not text.strip():
        return _empty_result()

    # 预处理：在关键字前插入换行，方便后续解析
    text = _normalize_text(text.strip())

    # 尝试解析
    parties = _extract_parties(text)

    if not parties:
        # 如果角色标签匹配失败，尝试直接提取字段
        return _parse_fields_directly(text)

    return parties[0]


def parse_multiple_clients_text(text: str) -> list[dict[str, Any]]:
    """解析包含多个当事人的文本"""
    if not text or not text.strip():
        return []

    text = _normalize_text(text.strip())
    return _extract_parties(text)


def _normalize_text(text: str) -> str:
    """预处理文本：统一换行、拆分内联字段、清理列表序号"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("；", "\n").replace(";", "\n")
    text = _FULL_STOP_BREAK_PATTERN.sub("\n", text)
    text = _ENUMERATION_PREFIX_PATTERN.sub("", text)
    text = _INLINE_BREAK_PATTERN.sub("\n", text)
    text = _FIELD_KEYWORDS_PATTERN.sub(r"\n\g<0>", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def _parse_fields_directly(text: str) -> dict[str, Any]:
    """直接从文本提取字段（无角色标签时使用）"""
    return _parse_single_party(text, use_smart_name=True)


def _extract_parties(text: str) -> list[dict[str, Any]]:
    """提取所有当事人信息"""
    parties = []

    # 定义角色标签模式（支持 甲方（原告）、乙方（被告）等格式）
    role_patterns = _ROLE_SPLIT_PATTERNS

    # 找到所有角色标签的位置
    all_matches: list[re.Match[str]] = []
    for compiled in role_patterns:
        all_matches.extend(compiled.finditer(text))

    # 按位置排序，去除同一起始位置的重复匹配（保留最长匹配）
    all_matches.sort(key=lambda x: (x.start(), -(x.end() - x.start())))
    seen_starts: set[int] = set()
    deduped: list[re.Match[str]] = []
    for m in all_matches:
        if m.start() not in seen_starts:
            seen_starts.add(m.start())
            deduped.append(m)
    all_matches = deduped

    # 提取每个当事人的信息
    for i, match in enumerate(all_matches):
        start_pos = match.end()

        # 确定当事人信息的结束位置
        if i + 1 < len(all_matches):
            end_pos = all_matches[i + 1].start()
        else:
            end_pos = len(text)

        # 提取当事人信息段落
        party_text = text[start_pos:end_pos].strip()

        if party_text:
            # 重新构造完整的当事人信息（包含角色标签）
            role_label = text[match.start() : match.end()]
            full_party_text = role_label + party_text

            party_info = _parse_single_party(full_party_text, use_smart_name=True)
            if party_info["name"]:  # 只有名称不为空才添加
                parties.append(party_info)

    # 无角色标签时按行独立解析：含姓名+电话的行各成一块，
    # 其余行（纯字段行等）并入当前块，避免多客户文本只解析出第一个客户
    if not parties:
        return _parse_unlabeled_lines(text)

    return parties


def _is_standalone_party_line(line: str) -> bool:
    """判断一行是否为自含姓名+电话的独立当事人块（如「张三 138…」含手机号的行）"""
    if not _PHONE_FALLBACK_PATTERN.search(line):
        return False
    name = _clean_name_candidate(line)
    return _is_valid_name_candidate(name)


def _parse_unlabeled_lines(text: str) -> list[dict[str, Any]]:
    """无角色标签时按行分块解析：姓名+电话同行的独立成块，其余行并入当前块"""
    blocks: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if blocks and not _is_standalone_party_line(line):
            blocks[-1] += f"\n{line}"
        else:
            blocks.append(line)

    parties: list[dict[str, Any]] = []
    for block in blocks:
        party_info = _parse_single_party(block, use_smart_name=True)
        if party_info["name"]:
            parties.append(party_info)
    return parties


def _parse_single_party(text: str, *, use_smart_name: bool = False) -> dict[str, Any]:
    """解析单个当事人信息"""
    result = _empty_result()

    name = _extract_name_smart(text) if use_smart_name else _extract_name(text)
    if name:
        result["name"] = name
        result["client_type"] = _determine_client_type(name, text)

    # 提取统一社会信用代码
    credit_code = _extract_credit_code(text)
    if credit_code:
        result["id_number"] = credit_code
        result["client_type"] = "legal"  # 有统一社会信用代码的是法人

    # 提取身份证号码
    if not result["id_number"]:
        id_number = _extract_id_number(text)
        if id_number:
            result["id_number"] = id_number
            result["client_type"] = "natural"  # 有身份证号的是自然人

    # 提取地址
    address = _extract_address(text)
    if address:
        result["address"] = address

    # 提取电话
    phone = _extract_phone(text)
    if phone:
        result["phone"] = phone

    # 提取法定代表人
    legal_rep = _extract_legal_representative(text)
    if legal_rep:
        result["legal_representative"] = legal_rep
        if result["client_type"] == "natural":
            result["client_type"] = "legal"  # 有法定代表人的是法人

    return result
