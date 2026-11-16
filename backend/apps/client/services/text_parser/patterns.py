"""当事人文本解析的正则模式与关键字常量。"""

from __future__ import annotations

import re

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
    r"([一-龥A-Za-z0-9（）()·]{4,}"
    r"(?:有限责任公司|有限公司|股份有限公司|股份公司|集团有限公司|集团|合伙企业|律师事务所|研究院|银行|医院|学校|中心|店|厂))"
)
_NATURAL_PERSON_NAME_PATTERN = re.compile(r"([一-龥·]{2,10})\s*[，,]\s*(?:男|女)")
_LEADING_NAME_BEFORE_FIELD_PATTERN = re.compile(
    r"^\s*([^\n；;。]{2,80}?)"
    r"(?=\s*(?:统一社会信用代码|社会信用代码|信用代码|身份证号码|身份证号|身份证|证件号码|"
    r"法定代表人|法人代表|法定负责人|负责人|联系电话|电话|联系方式|手机|联系电话号码|联系人电话|"
    r"地址|住址|住所地|住所|注册地址|经营地址|联系地址))"
)
_LEADING_PERSON_NAME_PATTERN = re.compile(
    r"^\s*([一-龥·]{2,10})"
    r"(?=\s*(?:[，,；;]?\s*(?:男|女|出生|身份证号码|身份证号|身份证|证件号码|联系电话|电话|联系方式|手机|地址|住址|住所)))"
)
_ADDRESS_LINE_FALLBACK_PATTERN = re.compile(
    r"^(?:中国)?(?:北京市|天津市|上海市|重庆市|[一-龥]{2,}(?:省|自治区|特别行政区))"
    r"[一-龥A-Za-z0-9\-（）()#号室栋单元路街道区县乡镇村]{4,}$"
)
_TRAILING_GENDER_PATTERN = re.compile(r"(?:\s|[，,])(?:男|女)\s*$")
_TRAILING_BIRTH_INFO_PATTERN = re.compile(r"(?:\s|[，,])\d{4}年\d{1,2}月\d{1,2}日(?:出生)?\s*$")
# 名称候选中的电话/长数字串：剥离后避免把「张三 138…」这类含手机号的行整行当名称
_PHONE_IN_NAME_PATTERN = re.compile(
    r"(?<!\d)(?:\+?86[-\s]?)?1[3-9]\d{9}(?!\d)"
    r"|(?<!\d)(?:\+?86[-\s]?)?0\d{2,3}[-\s]?\d{7,8}(?!\d)"
    r"|(?<!\d)\d{15,18}(?!\d)"
)
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

_FIELD_KEYWORDS_PATTERN = re.compile(r"(?<!\n)(" + "|".join(re.escape(kw) for kw in _FIELD_KEYWORDS) + r")\s*[:：]")
_INLINE_BREAK_KEYWORDS_ALT = "|".join(
    re.escape(keyword) for keyword in dict.fromkeys([*_FIELD_KEYWORDS, *_ROLE_LABELS])
)
_INLINE_BREAK_PATTERN = re.compile(rf"(?<!\n)(?<=\S)\s+(?=(?:{_INLINE_BREAK_KEYWORDS_ALT})\s*(?:[:：]|为|是|\S))")
_FULL_STOP_BREAK_PATTERN = re.compile(r"[。]+(?=\s*\S)")

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
