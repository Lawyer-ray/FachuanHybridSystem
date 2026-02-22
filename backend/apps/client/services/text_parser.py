"""当事人文本解析器。"""

from __future__ import annotations

import re
from typing import Any

# 关键字列表，用于智能分割无换行文本
_FIELD_KEYWORDS: list[str] = [
    "法定代表人",
    "法人代表",
    "负责人",
    "统一社会信用代码",
    "社会信用代码",
    "信用代码",
    "身份证号码",
    "身份证号",
    "身份证",
    "证件号码",
    "地址",
    "住址",
    "住所地",
    "住所",
    "联系电话",
    "电话",
    "联系方式",
    "手机",
]


# 角色标签模式（用于分割多当事人文本）
# 带括号注释的模式优先（更具体），无括号的作为回退
_ROLE_SPLIT_STRS: list[str] = [
    r"甲方\s*（[^）]*）\s*[:：]",
    r"乙方\s*（[^）]*）\s*[:：]",
    r"丙方\s*（[^）]*）\s*[:：]",
    r"申请人\s*（[^）]*）\s*[:：]",
    r"被申请人\s*（[^）]*）\s*[:：]",
    r"答辩人\s*（[^）]*）\s*[:：]",
    r"被答辩人\s*（[^）]*）\s*[:：]",
    r"原告\s*[:：]",
    r"被告\s*[:：]",
    r"上诉人\s*[:：]",
    r"被上诉人\s*[:：]",
    r"第三人\s*[:：]",
    r"申请人\s*[:：]",
    r"被申请人\s*[:：]",
    r"答辩人\s*[:：]",
    r"被答辩人\s*[:：]",
    r"甲方\s*[:：]",
    r"乙方\s*[:：]",
]

_ROLE_SPLIT_PATTERNS: list[re.Pattern[str]] = [re.compile(p, re.IGNORECASE) for p in _ROLE_SPLIT_STRS]

# 角色标签 + 名称捕获模式（用于提取名称）
_ROLE_NAME_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p.replace(r"[:：]", r"[:：]\s*([^\n法统地住电]+)"), re.IGNORECASE)
    for p in _ROLE_SPLIT_STRS
]


_ETHNICITY_PATTERN = re.compile(
    r"[，,]\s*(?:男|女|汉族|回族|满族|蒙古族|维吾尔族|藏族|壮族|朝鲜族|苗族|瑶族|"
    r"土家族|布依族|侗族|白族|哈尼族|哈萨克族|黎族|傣族|畲族|傈僳族|仡佬族|东乡族|"
    r"高山族|拉祜族|水族|佤族|纳西族|羌族|土族|仫佬族|锡伯族|柯尔克孜族|达斡尔族|"
    r"景颇族|毛南族|撒拉族|布朗族|塔吉克族|阿昌族|普米族|鄂温克族|怒族|京族|基诺族|"
    r"德昂族|保安族|俄罗斯族|裕固族|乌孜别克族|门巴族|鄂伦春族|独龙族|塔塔尔族|"
    r"赫哲族|珞巴族).*"
)
_BIRTH_DATE_PATTERN = re.compile(r"[，,]\s*\d{4}年\d{1,2}月\d{1,2}日.*")

_CREDIT_CODE_PATTERN = re.compile(
    r"(?:统一社会信用代码|信用代码|社会信用代码)\s*[:：]\s*([A-Z0-9]{18})", re.IGNORECASE
)
_ID_NUMBER_PATTERN = re.compile(
    r"(?:身份证号码|身份证号|身份证|证件号码)\s*[:：]\s*([0-9Xx]{15,18})", re.IGNORECASE
)
_ADDRESS_PATTERN = re.compile(
    r"(?:地址|住址|住所地|住所)\s*[:：]\s*([^\n]*?)(?=\n|$)", re.IGNORECASE
)
_PHONE_PATTERN = re.compile(
    r"(?:联系电话|电话|联系方式|手机)\s*[:：]\s*([0-9\-\+\s]{7,20})", re.IGNORECASE
)
_LEGAL_REP_PATTERN = re.compile(
    r"(?:法定代表人|法人代表|负责人)\s*[:：]\s*([^\n]*?)(?=\n|$)", re.IGNORECASE
)
_PAREN_CLEANUP_PATTERN = re.compile(r"（[^）]*）|\([^)]*\)")
_WHITESPACE_PATTERN = re.compile(r"\s+")

_LEGAL_KEYWORDS: tuple[str, ...] = (
    "有限公司", "股份公司", "集团", "企业", "厂", "店", "中心",
    "协会", "基金会", "研究院", "学校", "医院", "银行",
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


_FIELD_KEYWORDS_PATTERN = re.compile(
    r"(?<!\n)(" + "|".join(re.escape(kw) for kw in _FIELD_KEYWORDS) + r")\s*[:：]"
)


def _normalize_text(text: str) -> str:
    """预处理文本：在关键字前插入换行"""
    return _FIELD_KEYWORDS_PATTERN.sub(r"\n\g<0>", text)


def _parse_fields_directly(text: str) -> dict[str, Any]:
    """直接从文本提取字段（无角色标签时使用）"""
    return _parse_single_party(text, use_smart_name=True)


_SMART_NAME_PATTERN = re.compile(
    r"^[甲乙丙丁]方\s*(?:（[^）]*）)?\s*[:：]\s*(.+?)(?=法定代表人|统一社会信用代码|地址|电话|$)",
    re.DOTALL,
)


def _extract_name_smart(text: str) -> str | None:
    """智能提取名称"""
    name = _extract_name(text)
    if name:
        return name

    match = _SMART_NAME_PATTERN.search(text)
    if match:
        name = _WHITESPACE_PATTERN.sub("", match.group(1).strip())
        if name:
            return name

    return None


def _extract_parties(text: str) -> list[dict[str, Any]]:
    """提取所有当事人信息"""
    parties = []

    # 定义角色标签模式（支持 甲方（原告）、乙方（被告）等格式）
    role_patterns = _ROLE_SPLIT_PATTERNS

    # 找到所有角色标签的位置
    all_matches = []
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

            party_info = _parse_single_party(full_party_text)
            if party_info["name"]:  # 只有名称不为空才添加
                parties.append(party_info)

    # 如果没有找到角色标签，尝试直接解析
    if not parties:
        party_info = _parse_single_party(text)
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


def _extract_name(text: str) -> str | None:
    """提取名称"""
    # 定义角色标签模式（支持 甲方（原告）、乙方（被告）等格式）
    role_patterns = _ROLE_NAME_PATTERNS

    for compiled in role_patterns:
        match = compiled.search(text)
        if match:
            name_part = match.group(1).strip()

            # 去除性别、民族、出生日期等个人信息
            name = _ETHNICITY_PATTERN.sub("", name_part)
            name = _BIRTH_DATE_PATTERN.sub("", name)

            if name.strip():
                return name.strip()

    return None


def _extract_credit_code(text: str) -> str | None:
    """提取统一社会信用代码"""
    match = _CREDIT_CODE_PATTERN.search(text)
    return match.group(1).strip() if match else None


def _extract_id_number(text: str) -> str | None:
    """提取身份证号码"""
    match = _ID_NUMBER_PATTERN.search(text)
    return match.group(1).strip() if match else None


def _extract_address(text: str) -> str | None:
    """提取地址"""
    match = _ADDRESS_PATTERN.search(text)
    if not match:
        return None
    address = _PAREN_CLEANUP_PATTERN.sub("", match.group(1).strip()).strip()
    return address or None


def _extract_phone(text: str) -> str | None:
    """提取电话号码"""
    match = _PHONE_PATTERN.search(text)
    if not match:
        return None
    phone = _WHITESPACE_PATTERN.sub("", match.group(1).strip())
    return phone or None


def _extract_legal_representative(text: str) -> str | None:
    """提取法定代表人"""
    match = _LEGAL_REP_PATTERN.search(text)
    if not match:
        return None
    legal_rep = match.group(1).strip()
    return legal_rep or None

    return None


def _determine_client_type(name: str, text: str) -> str:
    """根据名称和文本内容判断客户类型"""
    if _extract_credit_code(text):
        return "legal"
    if _extract_legal_representative(text):
        return "legal"
    if any(kw in name for kw in _LEGAL_KEYWORDS):
        return "legal"
    if _extract_id_number(text):
        return "natural"
    return "natural"


def _empty_result() -> dict[str, Any]:
    """返回空的解析结果"""
    return {
        "name": "",
        "phone": "",
        "address": "",
        "client_type": "natural",
        "id_number": "",
        "legal_representative": "",
    }
