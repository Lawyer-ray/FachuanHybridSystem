"""当事人文本解析器。"""

from __future__ import annotations

import re
from typing import Any

# 关键字列表，用于智能分割无换行文本
_FIELD_KEYWORDS: list[str] = [
    "名称",
    "企业名称",
    "公司名称",
    "单位名称",
    "姓名",
    "类型",
    "当事人",
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
    "注册地址",
    "经营地址",
    "联系地址",
    "住址",
    "住所地",
    "住所",
    "联系电话",
    "电话",
    "联系方式",
    "手机",
]


# 角色标签模式（用于分割多当事人文本）
# 统一支持：
# - 带序号：被告一 / 被告1 / 甲方二
# - 带括号注释：原告（反诉被告）
# - 带冒号或仅空格分隔：原告：张三 / 原告 张三
_ROLE_LABELS: tuple[str, ...] = (
    "再审被申请人",
    "再审申请人",
    "申请再审人",
    "被申请复议人",
    "申请复议人",
    "原审被告",
    "原审原告",
    "被申请执行人",
    "申请执行人",
    "被上诉人",
    "被申请人",
    "被执行人",
    "被答辩人",
    "申请人",
    "上诉人",
    "答辩人",
    "第三人",
    "委托方",
    "受托方",
    "委托人",
    "当事人",
    "原告",
    "被告",
    "甲方",
    "乙方",
    "丙方",
    "丁方",
)
_ROLE_LABELS_ALT = "|".join(re.escape(label) for label in _ROLE_LABELS)
_ROLE_SPLIT_STRS: list[str] = [
    rf"(?:{re.escape(label)})\s*(?:[一二三四五六七八九十\d]+)?\s*(?:（[^）]*）|\([^)]*\))?\s*(?:[:：]\s*|\s+)"
    for label in _ROLE_LABELS
]

_ROLE_SPLIT_PATTERNS: list[re.Pattern[str]] = [re.compile(p, re.IGNORECASE) for p in _ROLE_SPLIT_STRS]

# 角色标签 + 名称捕获模式（用于提取名称）
_ROLE_NAME_PATTERNS: list[re.Pattern[str]] = [re.compile(rf"{p}([^\n]+)", re.IGNORECASE) for p in _ROLE_SPLIT_STRS]


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
    r"(?:统一社会信用代码|信用代码|社会信用代码)\s*(?:[:：]|为|是)?\s*([A-Z0-9]{18})",
    re.IGNORECASE,
)
_CREDIT_CODE_FALLBACK_PATTERN = re.compile(r"\b([A-Z0-9]{18})\b", re.IGNORECASE)
_ID_NUMBER_PATTERN = re.compile(
    r"(?:身份证号码|身份证号|身份证|证件号码)\s*(?:[:：]|为|是)?\s*([0-9Xx]{15,18})",
    re.IGNORECASE,
)
_ID_NUMBER_FALLBACK_PATTERN = re.compile(r"\b([1-9]\d{16}[0-9Xx]|[1-9]\d{14})\b")
_ADDRESS_PATTERN = re.compile(
    r"(?:注册地址|经营地址|联系地址|地址|住址|住所地|住所)\s*(?:[:：]|为|是)?\s*([^\n；;。]*?)"
    r"(?=\n|$|；|;|。|(?:联系电话|电话|联系方式|手机|法定代表人|法人代表|法定负责人|负责人)\s*(?:[:：]|为|是)?)",
    re.IGNORECASE,
)
_PHONE_PATTERN = re.compile(
    r"(?:联系电话|电话|联系方式|手机|联系电话号码|联系人电话)\s*(?:[:：]|为|是)?\s*([0-9\-\+\s]{7,20})",
    re.IGNORECASE,
)
_PHONE_FALLBACK_PATTERN = re.compile(r"(?<!\d)(1[3-9]\d{9}|(?:0\d{2,3}-?)?\d{7,8})(?!\d)")
_LEGAL_REP_PATTERN = re.compile(
    r"(?:法定代表人|法人代表|法定负责人|负责人)\s*(?:[:：]|为|是)?\s*([^\n；;。]*?)"
    r"(?=\n|$|；|;|。|(?:联系电话|电话|联系方式|手机|注册地址|经营地址|联系地址|地址|住址|住所地|住所)\s*(?:[:：]|为|是)?)",
    re.IGNORECASE,
)
_PAREN_CLEANUP_PATTERN = re.compile(r"（[^）]*）|\([^)]*\)")
_WHITESPACE_PATTERN = re.compile(r"\s+")

_ROLE_NAME_FALLBACK_PATTERN = re.compile(
    r"(?:^|\n)\s*"
    rf"(?:{_ROLE_LABELS_ALT})"
    r"\s*(?:[一二三四五六七八九十\d]+)?\s*(?:（[^）]*）|\([^)]*\))?\s*(?:[:：]\s*|\s+)([^\n，,；;。]+)",
    re.IGNORECASE,
)
_ROLE_PREFIX_CLEANUP_PATTERN = re.compile(
    rf"^(?:{_ROLE_LABELS_ALT})\s*(?:[一二三四五六七八九十\d]+)?\s*(?:（[^）]*）|\([^)]*\))?\s*(?:[:：]\s*|\s+)",
    re.IGNORECASE,
)
_LEGAL_ENTITY_NAME_PATTERN = re.compile(
    r"([\u4e00-\u9fa5A-Za-z0-9（）()·]{4,}"
    r"(?:有限责任公司|有限公司|股份有限公司|股份公司|集团有限公司|集团|合伙企业|律师事务所|研究院|银行|医院|学校|中心|店|厂))"
)
_NATURAL_PERSON_NAME_PATTERN = re.compile(r"([\u4e00-\u9fa5·]{2,10})\s*[，,]\s*(?:男|女)")
_LEADING_NAME_BEFORE_FIELD_PATTERN = re.compile(
    r"^\s*([^\n；;。]{2,80}?)"
    r"(?=\s*(?:统一社会信用代码|社会信用代码|信用代码|身份证号码|身份证号|身份证|证件号码|"
    r"法定代表人|法人代表|法定负责人|负责人|联系电话|电话|联系方式|手机|联系电话号码|联系人电话|"
    r"地址|住址|住所地|住所|注册地址|经营地址|联系地址))"
)
_LEADING_PERSON_NAME_PATTERN = re.compile(
    r"^\s*([\u4e00-\u9fa5·]{2,10})"
    r"(?=\s*(?:[，,；;]?\s*(?:男|女|出生|身份证号码|身份证号|身份证|证件号码|联系电话|电话|联系方式|手机|地址|住址|住所)))"
)
_ADDRESS_LINE_FALLBACK_PATTERN = re.compile(
    r"^(?:中国)?(?:北京市|天津市|上海市|重庆市|[\u4e00-\u9fa5]{2,}(?:省|自治区|特别行政区))"
    r"[\u4e00-\u9fa5A-Za-z0-9\-（）()#号室栋单元路街道区县乡镇村]{4,}$"
)
_TRAILING_GENDER_PATTERN = re.compile(r"(?:\s|[，,])(?:男|女)\s*$")
_TRAILING_BIRTH_INFO_PATTERN = re.compile(r"(?:\s|[，,])\d{4}年\d{1,2}月\d{1,2}日(?:出生)?\s*$")
_ENUMERATION_PREFIX_PATTERN = re.compile(r"(?m)^\s*(?:[（(]?[一二三四五六七八九十\d]+[）)\.、]|[-*•])\s*")

_LEGAL_KEYWORDS: tuple[str, ...] = (
    "有限公司",
    "股份公司",
    "集团",
    "企业",
    "厂",
    "店",
    "中心",
    "协会",
    "基金会",
    "研究院",
    "学校",
    "医院",
    "银行",
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


_FIELD_KEYWORDS_PATTERN = re.compile(r"(?<!\n)(" + "|".join(re.escape(kw) for kw in _FIELD_KEYWORDS) + r")\s*[:：]")
_INLINE_BREAK_KEYWORDS_ALT = "|".join(
    re.escape(keyword) for keyword in dict.fromkeys([*_FIELD_KEYWORDS, *_ROLE_LABELS])
)
_INLINE_BREAK_PATTERN = re.compile(rf"(?<!\n)(?<=\S)\s+(?=(?:{_INLINE_BREAK_KEYWORDS_ALT})\s*(?:[:：]|为|是|\S))")
_FULL_STOP_BREAK_PATTERN = re.compile(r"[。]+(?=\s*\S)")


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


_SMART_NAME_PATTERN = re.compile(
    r"^[甲乙丙丁]方\s*(?:（[^）]*）)?\s*[:：]\s*(.+?)(?=法定代表人|统一社会信用代码|地址|电话|$)",
    re.DOTALL,
)

# 支持字段式名称（保留冒号约束，避免过度吞并整段文本）
_NAME_FIELD_PATTERN = re.compile(
    r"(?:^|\n)\s*(?:名称|企业名称|公司名称|单位名称|姓名|当事人名称)\s*(?:[:：]|为|是)?\s*([^\n]+)",
    re.IGNORECASE,
)
_NON_NAME_KEYWORDS: tuple[str, ...] = (
    "统一社会信用代码",
    "社会信用代码",
    "信用代码",
    "身份证",
    "证件号码",
    "法定代表人",
    "法人代表",
    "负责人",
    "联系电话",
    "联系方式",
    "电话",
    "手机",
    "地址",
    "住址",
    "住所",
    "注册地址",
    "经营地址",
    "联系地址",
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

    # 如果没有找到角色标签，尝试直接解析
    if not parties:
        party_info = _parse_single_party(text, use_smart_name=True)
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
            name = _clean_name_candidate(match.group(1))
            if _is_valid_name_candidate(name):
                return name.strip()

    return None


def _extract_credit_code(text: str) -> str | None:
    """提取统一社会信用代码"""
    match = _CREDIT_CODE_PATTERN.search(text)
    if match:
        return match.group(1).strip().upper()

    # 无标签兜底：仅接受含字母的18位编码，避免误判身份证号
    # 但需要排除明显是身份证号的情况（文本中有"身份证"关键词）
    for fallback_match in _CREDIT_CODE_FALLBACK_PATTERN.finditer(text):
        code = fallback_match.group(1).strip().upper()
        if not any(ch.isalpha() for ch in code):
            continue
        # 排除身份证号：如果编码附近有"身份证"关键词，跳过
        # 计算编码在文本中的位置
        start_pos = fallback_match.start()
        end_pos = fallback_match.end()
        # 检查前面 20 个字符内是否有"身份证"
        context_before = text[max(0, start_pos - 20) : start_pos].lower()
        if "身份证" in context_before:
            continue
        return code

    return None


def _extract_id_number(text: str) -> str | None:
    """提取身份证号码"""
    match = _ID_NUMBER_PATTERN.search(text)
    if match:
        return match.group(1).strip().upper()

    fallback = _ID_NUMBER_FALLBACK_PATTERN.search(text)
    return fallback.group(1).strip().upper() if fallback else None


def _extract_address(text: str) -> str | None:
    """提取地址"""
    match = _ADDRESS_PATTERN.search(text)
    if match:
        address = match.group(1).strip()
        if address:
            return address

    # 无标签兜底：从明显的省市开头行提取
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line and _ADDRESS_LINE_FALLBACK_PATTERN.fullmatch(line):
            return line
    return None


def _extract_phone(text: str) -> str | None:
    """提取电话号码"""
    match = _PHONE_PATTERN.search(text)
    if match:
        phone = _WHITESPACE_PATTERN.sub("", match.group(1).strip())
        if phone:
            return phone

    # 无标签兜底：优先手机号，其次座机
    fallback_phone: str | None = None
    for fallback in _PHONE_FALLBACK_PATTERN.finditer(text):
        candidate = _WHITESPACE_PATTERN.sub("", fallback.group(1).strip())
        digits_only = re.sub(r"\D", "", candidate)
        if len(digits_only) == 11 and digits_only.startswith("1"):
            return candidate
        if fallback_phone is None:
            fallback_phone = candidate
    return fallback_phone


def _extract_legal_representative(text: str) -> str | None:
    """提取法定代表人"""
    match = _LEGAL_REP_PATTERN.search(text)
    if not match:
        return None
    legal_rep = _clean_name_candidate(match.group(1))
    return legal_rep or None


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
