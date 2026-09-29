"""法院文书联系人/联系电话提取（标签锚定正则）。

传票/裁定书等法院文书通常在结尾以「联系人：X、Y 联系电话：0757-XXXX」标注
办案联系人。这里是确定性提取，无需 LLM；raw_text 已落库，读时重算成本可忽略，
对存量任务即时生效（区别于 LLM 结果必须落库才能复现）。
"""

import re

# 姓名标签（顺序即正则优先级）：命中后取标签后的姓名串。
# 不含裸「法官」——正文里"法官说/法官助理"等常见，标签化误报率高。
_NAME_LABEL_RE = re.compile(r"(联系人|承办法官|书记员|办案人员|经办人)[：:\s]*")
# 电话标签：只接受紧跟的数字/连字符/括号/空格串，避免吃进正文
_PHONE_LABEL_RE = re.compile(r"(?:联系电话|联系方式|电话)[：:\s]*([0-9+\-（）()．.\s]{7,30})")
# 姓名串的截断词：下一个信息标签或句读（文书常无换行，句号后必是正文而非姓名）
_STOP_RE = re.compile(r"(?:联系电话|联系方式|电话|地址|邮箱|邮编|[。；！？!?.;])")
_NAME_SPLIT_RE = re.compile(r"[、，,;；\s]+")
# 法院联系人姓名：2-4 个纯汉字（含少数民族姓名分隔符·）
_NAME_TOKEN_RE = re.compile(r"[\u4e00-\u9fa5·]{2,4}")

# 姓名标签与其电话之间的最大字符距离
_MAX_NAME_PHONE_GAP = 60
# 姓名串取值窗口（标签后最多看这么多字符找截断词）
_NAME_WINDOW = 60

# 地址标签与取值截断：地址串比姓名长，允许数字/字母/标点，遇到下一标签或句读止
_ADDRESS_LABEL_RE = re.compile(r"地址[：:\s]*")
_ADDRESS_STOP_RE = re.compile(
    r"(?:联系人|承办法官|书记员|办案人员|经办人|联系电话|联系方式|电话|邮箱|邮编|[。；！？!?.;])"
)
_ADDRESS_WINDOW = 80


def extract_address(text: str | None) -> str | None:
    """提取文书标注的地址（取首个「地址：」标签，截断到下一标签/句读）。"""
    if not text:
        return None
    m = _ADDRESS_LABEL_RE.search(text)
    if not m:
        return None
    rest = text[m.end() : m.end() + _ADDRESS_WINDOW]
    stop = _ADDRESS_STOP_RE.search(rest)
    value = (rest[: stop.start()] if stop else rest).strip()
    value = value.strip("，,、；;：: ")
    if not (4 <= len(value) <= 60):
        return None
    return value


def _clean_phone(raw: str) -> str | None:
    """校验并清洗电话串（区号-号码/手机号），不合格返回 None。"""
    phone = re.sub(r"[^0-9]", "", raw)
    if not (7 <= len(phone) <= 12):
        return None
    return raw.strip()


def _name_groups(text: str) -> list[tuple[str, int, str]]:
    """提取 (角色, 标签位置, 姓名)，姓名以「、」连接多人。"""
    groups: list[tuple[str, int, str]] = []
    for m in _NAME_LABEL_RE.finditer(text):
        rest = text[m.end() : m.end() + _NAME_WINDOW]
        stop = _STOP_RE.search(rest)
        value = rest[: stop.start()] if stop else rest
        names = [n for n in _NAME_SPLIT_RE.split(value) if _NAME_TOKEN_RE.fullmatch(n)]
        if names:
            groups.append((m.group(1), m.start(), "、".join(names)))
    return groups


def extract_contacts(text: str | None) -> list[dict[str, str | None]]:
    """从文书原文提取联系人条目 [{role, name, phone}]。

    配对规则：姓名标签之后 _MAX_NAME_PHONE_GAP 字符内的第一个电话标签视为
    该联系人的电话；无姓名标签的孤立电话单独成条（name 为空）。
    """
    if not text:
        return []

    phones = [(m.start(), _clean_phone(m.group(1))) for m in _PHONE_LABEL_RE.finditer(text)]
    phones = [(pos, p) for pos, p in phones if p]

    contacts: list[dict[str, str | None]] = []
    used_phone_positions: set[int] = set()
    for role, pos, names in _name_groups(text):
        phone: str | None = None
        for phone_pos, phone_value in phones:
            if pos < phone_pos <= pos + _MAX_NAME_PHONE_GAP and phone_pos not in used_phone_positions:
                phone = phone_value
                used_phone_positions.add(phone_pos)
                break
        contacts.append({"role": role, "name": names, "phone": phone})

    for phone_pos, phone_value in phones:
        if phone_pos not in used_phone_positions:
            contacts.append({"role": "联系电话", "name": "", "phone": phone_value})

    # 去重（同文档重复标注）
    seen: set[tuple[str, str, str | None]] = set()
    unique: list[dict[str, str | None]] = []
    for c in contacts:
        key = (str(c["role"]), str(c["name"]), c["phone"])
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique
