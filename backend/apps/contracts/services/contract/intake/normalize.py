"""把 LLM 抽取结果收成「可直接回填表单」的字面值。

这是整个链路的**闸门层**：LLM 输出一律视为不可信的自由文本，任何要进
``Contract`` 字段的值都必须在这里过一遍确定性规则。

三条硬规则：

1. **枚举白名单**：``case_type``/``fee_mode`` 只接受系统枚举内的值，模型给
   ``"非诉"``/``"固定"`` 这类中文口语一律映射到枚举，映射不到就留空（留空
   时表单回落到默认值，由用户自己选，绝不猜）。
2. **金额只做确定性换算**：中文大写金额 → ``Decimal``；换算失败返回 ``None``
   并把原文带回前端展示，让用户手工填。
3. **日期不猜**：只有能解析成确切日期的才填；「签订三日内」「至税务机关作出
   结论为止」这类相对/条件表述标记为「需人工」，不写入 ``DateField``。

另外这里承担两个**业务安全**职责：
- 剔除律所（律所不是我方客户，也不是对方当事人，建 Client 会污染数据
  且 ``on_delete=PROTECT`` 后删不掉）；
- 律师姓名按姓名/用户名做精确+去空格匹配，匹配不到就留空（不创建律师）。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from apps.contracts.models import FeeMode
from apps.contracts.services.contract.intake.extract_schema import ContractExtraction, ExtractedLawyer, ExtractedParty
from apps.core.models.enums import CaseType

logger = logging.getLogger(__name__)

#: ``custom_terms`` 入库长度上限（TextField 技术上无限，但表单里应保持可读）
_MAX_CUSTOM_TERMS_CHARS = 500

#: 合同类型中文标签（与 ``CaseType.choices`` 一致，用于生成合同名称）
_CASE_TYPE_LABELS: dict[str, str] = {
    CaseType.CIVIL.value: "民商事",
    CaseType.CRIMINAL.value: "刑事",
    CaseType.ADMINISTRATIVE.value: "行政",
    CaseType.LABOR.value: "劳动仲裁",
    CaseType.INTL.value: "商事仲裁",
    CaseType.SPECIAL.value: "专项服务",
    CaseType.ADVISOR.value: "常年法律顾问",
}

#: 需要人工确认的字段在 ``needs_review`` 里以这些键出现
REVIEW_FIELDS: tuple[str, ...] = (
    "name",
    "case_type",
    "fee_mode",
    "fixed_amount",
    "start_date",
    "end_date",
    "client",
    "parties",
    "lawyers",
    "sign_date",
)

#: 模型可能给出的中文口语 → 系统枚举
_CASE_TYPE_ALIASES: dict[str, str] = {
    "民商事": CaseType.CIVIL.value,
    "民事": CaseType.CIVIL.value,
    "商事": CaseType.CIVIL.value,
    "刑事": CaseType.CRIMINAL.value,
    "行政": CaseType.ADMINISTRATIVE.value,
    "劳动": CaseType.LABOR.value,
    "劳动仲裁": CaseType.LABOR.value,
    "商事仲裁": CaseType.INTL.value,
    "仲裁": CaseType.INTL.value,
    "专项": CaseType.SPECIAL.value,
    "专项服务": CaseType.SPECIAL.value,
    "非诉": CaseType.SPECIAL.value,
    "非诉专项": CaseType.SPECIAL.value,
    "顾问": CaseType.ADVISOR.value,
    "常法": CaseType.ADVISOR.value,
    "常年法律顾问": CaseType.ADVISOR.value,
    "法律顾问": CaseType.ADVISOR.value,
}

_FEE_MODE_ALIASES: dict[str, str] = {
    "固定": FeeMode.FIXED.value,
    "固定收费": FeeMode.FIXED.value,
    "计时": FeeMode.FIXED.value,
    "半风险": FeeMode.SEMI_RISK.value,
    "半风险收费": FeeMode.SEMI_RISK.value,
    "全风险": FeeMode.FULL_RISK.value,
    "全风险收费": FeeMode.FULL_RISK.value,
    "风险": FeeMode.FULL_RISK.value,
    "自定义": FeeMode.CUSTOM.value,
}

#: 中文数字字符 → 数值
_CN_DIGITS: dict[str, int] = {
    "零": 0,
    "〇": 0,
    "壹": 1,
    "贰": 2,
    "叁": 3,
    "肆": 4,
    "伍": 5,
    "陆": 6,
    "柒": 7,
    "捌": 8,
    "玖": 9,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
#: 中文数量级（万/亿为节权位，十百千为位权）
_CN_UNITS: dict[str, int] = {"拾": 10, "十": 10, "佰": 100, "百": 100, "仟": 1000, "千": 1000}
_CN_SECTIONS: dict[str, int] = {"万": 10_000, "萬": 10_000, "亿": 100_000_000, "億": 100_000_000}

#: 律所名称特征（用于剔除误判为我方/对方当事人的律所）
_LAW_FIRM_MARKERS: tuple[str, ...] = ("律师事务所", "律师事務所", "法律服务所")

#: 金额提取：优先带小数的阿拉伯数字，其次整数字
_MONEY_ARABIC_RE = re.compile(r"(?<!\d)(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?!\d)")


def _has_wan_unit_near(text: str, token: str) -> bool:
    """数字后面紧跟万/亿单位时返回 True（用于「5万元」「0.5万元」这类写法）。"""
    index = text.find(token)
    if index < 0:
        return False
    tail = text[index + len(token) : index + len(token) + 3]
    return any(unit in tail for unit in ("万元", "万元", "万", "亿"))


#: 完整中文日期：2026年11月10日 / 二〇二六年十一月十日
_DATE_CN_RE = re.compile(
    r"([〇零一二三四五六七八九]{4}|\d{4})\s*年\s*(\d{1,2}|[一二三四五六七八九十]{1,3})\s*月\s*(\d{1,2}|[一二三四五六七八九十]{1,3})\s*日"
)
#: 阿拉伯数字日期：2026-11-10 / 2026/11/10
_DATE_ISO_RE = re.compile(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})")
#: 相对/条件式日期表述特征——命中即视为不可直接入库
_RELATIVE_DATE_MARKERS: tuple[str, ...] = (
    "生效后",
    "签订后",
    "签署后",
    "订立后",
    "成立后",
    "盖章后",
    "签字后",
    "日内",
    "天内",
    "个工作日内",
    "之日起",
    "为止",
    "之前",
    "以前",
    "截止",
    "长期",
    "无固定期限",
    "另行",
    "待定",
    "视",
)


@dataclass
class NormalizedParty:
    """归一化后的当事人（供前端按名称匹配 Client 下拉）。"""

    name: str
    role_in_contract: str
    entity_type: str
    id_number: str
    legal_representative: str
    address: str
    suggested_role: str = "PRINCIPAL"
    match_kind: str = "none"  # exact_id / exact_name / none
    client_id: int | None = None
    client_label: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role_in_contract": self.role_in_contract,
            "entity_type": self.entity_type,
            "id_number": self.id_number,
            "legal_representative": self.legal_representative,
            "address": self.address,
            "suggested_role": self.suggested_role,
            "match_kind": self.match_kind,
            "client_id": self.client_id,
            "client_label": self.client_label,
        }


@dataclass
class NormalizedLawyer:
    """归一化后的承办律师。"""

    name: str
    law_firm: str
    is_primary: bool
    lawyer_id: int | None = None
    lawyer_label: str = ""
    matched: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "law_firm": self.law_firm,
            "is_primary": self.is_primary,
            "lawyer_id": self.lawyer_id,
            "lawyer_label": self.lawyer_label,
            "matched": self.matched,
        }


@dataclass
class ContractDraft:
    """可直接回填新建合同表单的草稿。"""

    fields: dict[str, Any] = field(default_factory=dict)
    parties: list[NormalizedParty] = field(default_factory=list)
    lawyers: list[NormalizedLawyer] = field(default_factory=list)
    needs_review: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    confidence: dict[str, float] = field(default_factory=dict)
    source_quotes: dict[str, str] = field(default_factory=dict)
    notes: str = ""
    raw_title: str = ""
    document_kind: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "fields": self.fields,
            "parties": [p.as_dict() for p in self.parties],
            "lawyers": [p.as_dict() for p in self.lawyers],
            "needs_review": self.needs_review,
            "warnings": self.warnings,
            "confidence": self.confidence,
            "source_quotes": self.source_quotes,
            "notes": self.notes,
            "raw_title": self.raw_title,
            "document_kind": self.document_kind,
        }


# ── 金额换算 ────────────────────────────────────────────────────────────


def _digits_year_to_int(text: str) -> int | None:
    """按位读年份：「二〇二六」→ 2026。

    年份是**逐位口读**而非位权累加，不能走 :func:`chinese_to_int`
    （该函数会把「二〇二六」算成 8），必须单独处理。
    """
    digits = [_CN_DIGITS[ch] for ch in text if ch in _CN_DIGITS]
    if len(digits) not in (2, 4):
        return None
    value = 0
    for digit in digits:
        value = value * 10 + digit
    return value


def chinese_to_int(raw: str) -> int | None:
    """中文数字 → 整数。支持「贰万」「壹万零伍佰」「三万二千」等常见写法。

    只处理位权式表述（金额/月份/日）；逐位口读的年份请用
    :func:`_digits_year_to_int`。
    """
    text = str(raw or "").strip()
    if not text:
        return None
    text = text.replace("整", "").replace("正", "")

    total = 0  # 已结算的「亿」以上部分
    section = 0  # 当前「万」级小节内的值
    number = 0  # 当前数字
    seen_any = False

    for char in text:
        if char in _CN_DIGITS:
            number = _CN_DIGITS[char]
            seen_any = True
        elif char in _CN_UNITS:
            unit = _CN_UNITS[char]
            # 「十万」中十前面没有数字时按 1 处理
            section += (number or 1) * unit
            number = 0
            seen_any = True
        elif char in _CN_SECTIONS:
            section_scale = _CN_SECTIONS[char]
            section = (section + number) * section_scale
            number = 0
            if section_scale >= 100_000_000:
                total += section
                section = 0
            seen_any = True
        elif char in "元圆人民币¥￥ ":
            continue
        else:
            # 出现非数字字符（如夹杂外文），放弃换算交给人工
            return None

    if not seen_any:
        return None
    return total + section + number


def parse_amount(raw: str) -> tuple[Decimal | None, str]:
    """从原文表述中解析律师费金额。

    Returns:
        ``(amount, reason)``：``amount`` 为 ``None`` 时 ``reason`` 说明原因。

    优先取括号内的阿拉伯数字（合同惯例「壹万元整（10000.00）」），
    没有阿拉伯数字再退回中文大写换算。
    """
    text = str(raw or "").strip()
    if not text:
        return None, "未提取到金额表述"

    # 0) 风险比例必须先排除：否则「按回款额 20% 收取」会被当成 20 元律师费
    if "%" in text or "％" in text or "比例" in text or "分成" in text:
        return None, "合同为风险比例收费，无固定金额"

    # 1) 优先：中文大写后跟括号阿拉伯数字——最可靠
    arabic_matches = _MONEY_ARABIC_RE.findall(text)
    if arabic_matches:
        cleaned = [m.replace(",", "") for m in arabic_matches]
        # 取最大金额：合同常写「各支付壹万元整（10000.00），共贰万元整（20000.00）」
        best: Decimal | None = None
        for token in cleaned:
            try:
                value = Decimal(token)
            except InvalidOperation:
                continue
            # 「0.5 万元」这类带万/仟单位的小数必须换算，否则 0.5 会被当成 5 角
            if value < 1000 and _has_wan_unit_near(text, token):
                value = value * 10_000
            if best is None or value > best:
                best = value
        if best is not None and best > 0:
            return best.quantize(Decimal("0.01")), ""
        if best is not None and best == 0:
            return None, "合同载明律师费为 0，请人工确认"
        if best is not None and best < 1:
            # 小于 1 的数值高度可疑（多半是把百分比小数或序号当成了金额）
            return None, f"金额「{text[:20]}」疑似非律师费，请人工确认"

    # 2) 退回：中文大写换算
    chinese = "".join(ch for ch in text if ch in _CN_DIGITS or ch in _CN_UNITS or ch in _CN_SECTIONS or ch == "整")
    if chinese:
        value_int = chinese_to_int(chinese)
        if value_int:
            return Decimal(value_int).quantize(Decimal("0.01")), ""

    return None, "金额表述无法自动换算，请人工填写"


# ── 日期解析 ────────────────────────────────────────────────────────────


def parse_date(raw: str) -> tuple[date | None, str]:
    """解析确切日期；相对/条件式表述返回 ``None`` 并说明原因。"""
    text = str(raw or "").strip()
    if not text:
        return None, "未提取到日期"

    for marker in _RELATIVE_DATE_MARKERS:
        if marker in text:
            return None, f"「{text[:20]}」为相对/条件式表述，需人工确定"

    iso = _DATE_ISO_RE.search(text)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3))), ""
        except ValueError:
            return None, f"日期「{text[:20]}」不合法"

    cn = _DATE_CN_RE.search(text)
    if cn:
        year_raw, month_raw, day_raw = cn.group(1), cn.group(2), cn.group(3)
        # 年份逐位读（二〇二六），月/日是位权读（十一、二十三）
        year = int(year_raw) if year_raw.isdigit() else _digits_year_to_int(year_raw)
        month = int(month_raw) if month_raw.isdigit() else chinese_to_int(month_raw)
        day = int(day_raw) if day_raw.isdigit() else chinese_to_int(day_raw)
        if year and month and day:
            try:
                return date(year, month, day), ""
            except ValueError:
                return None, f"日期「{text[:20]}」不合法"

    return None, f"日期「{text[:20]}」无法解析"


# ── 枚举归一 ────────────────────────────────────────────────────────────


def normalize_case_type(raw: str) -> tuple[str, bool]:
    """返回 ``(case_type, ok)``；``ok=False`` 表示无法判定需人工选。"""
    text = str(raw or "").strip()
    if not text:
        return "", False
    lowered = text.lower()
    valid = {choice.value for choice in CaseType}
    if lowered in valid:
        return lowered, True
    for alias, value in _CASE_TYPE_ALIASES.items():
        if alias in text:
            return value, True
    return "", False


def normalize_fee_mode(raw: str) -> tuple[str, bool]:
    """返回 ``(fee_mode, ok)``。"""
    text = str(raw or "").strip()
    if not text:
        return FeeMode.FIXED.value, False
    valid = {choice.value for choice in FeeMode}
    if text in valid:
        return text, True
    for alias, value in _FEE_MODE_ALIASES.items():
        if alias in text:
            return value, True
    return FeeMode.FIXED.value, False


# ── 律所剔除 / 主体判定 ─────────────────────────────────────────────────


def is_law_firm_name(name: str) -> bool:
    """名称是否为律所（按关键词判断，覆盖模型漏标 is_law_firm 的情况）。"""
    text = str(name or "")
    return any(marker in text for marker in _LAW_FIRM_MARKERS)


def guess_entity_type(party: ExtractedParty) -> str:
    """推断主体类型：法人 / 自然人 / 未知。"""
    declared = str(party.entity_type or "").strip().lower()
    if declared in {"legal", "natural"}:
        return declared
    if party.id_number and len(party.id_number) == 18 and party.id_number.startswith("91"):
        return "legal"
    if party.legal_representative:
        return "legal"
    if is_law_firm_name(party.name):
        return "legal"
    return "unknown"


def build_contract_name(*, client_name: str, matter_summary: str, title: str, case_type: str) -> str:
    """生成合同名称，对齐页面上「自动生成合同名称」按钮的既有规则。

    ``auto_contract_name.js`` 的规则是「委托人_合同类型+合同」（如
    「XXX_专项服务合同」）。这里保持一致，只在**提取到明确委托事由**时用事由
    替代泛化的类型名——同一客户常有多份同类合同，只靠类型会重名。
    """
    client = str(client_name or "").strip()
    matter = str(matter_summary or "").strip()
    type_label = _CASE_TYPE_LABELS.get(case_type, "")

    if client:
        suffix = matter or (f"{type_label}合同" if type_label else "")
        if suffix:
            return f"{client}_{suffix}"[:100]
        return f"{client}_法律服务合同"[:100]
    return matter[:100] or str(title or "").strip()[:100]


# ── 主入口 ──────────────────────────────────────────────────────────────


def normalize_extraction(
    extraction: ContractExtraction,
    *,
    client_lookup: dict[str, tuple[int, str]] | None = None,
    lawyer_lookup: dict[str, tuple[int, str]] | None = None,
) -> ContractDraft:
    """把 LLM 抽取结果归一成 :class:`ContractDraft`。

    Args:
        extraction: 模型输出（已过 Pydantic 校验）。
        client_lookup: ``{归一化名称或证照号: (client_id, 展示名)}``，用于把当事人
            关联到已有 Client。
        lawyer_lookup: ``{归一化姓名: (lawyer_id, 展示名)}``，用于把律师姓名关联到 Lawyer。
    """
    client_lookup = client_lookup or {}
    lawyer_lookup = lawyer_lookup or {}
    draft = ContractDraft()
    draft.raw_title = extraction.title
    draft.document_kind = extraction.document_kind
    draft.notes = str(extraction.notes or "").strip()
    draft.confidence = {k: float(v) for k, v in (extraction.confidence or {}).items() if isinstance(v, (int, float))}
    draft.source_quotes = dict(extraction.source_quotes or {})

    # ── 1. 当事人：剔除律所 ──
    kept: list[ExtractedParty] = []
    dropped_firms: list[str] = []
    for party in extraction.parties:
        if party.is_law_firm or is_law_firm_name(party.name):
            dropped_firms.append(party.name)
            continue
        if not str(party.name or "").strip():
            continue
        kept.append(party)

    if dropped_firms:
        draft.warnings.append(
            "已自动忽略律所（" + "、".join(dict.fromkeys(dropped_firms)) + "），律所不作为合同当事人录入"
        )

    # ── 2. 甲方 / 当事人列表 ──
    primary_name = str(extraction.client_name or "").strip()
    if not primary_name:
        # 模型没给 client_name 时退回第一个非律所「甲方」当事人
        for party in kept:
            if "甲方" in str(party.role_in_contract or "") or "委托" in str(party.role_in_contract or ""):
                primary_name = party.name
                break
    if not primary_name and kept:
        primary_name = kept[0].name
        draft.warnings.append("未能明确识别委托方，暂以首个当事人作为甲方，请核对")

    for index, party in enumerate(kept):
        np = NormalizedParty(
            name=party.name.strip(),
            role_in_contract=str(party.role_in_contract or "").strip(),
            entity_type=guess_entity_type(party),
            id_number=str(party.id_number or "").strip(),
            legal_representative=str(party.legal_representative or "").strip(),
            address=str(party.address or "").strip(),
        )
        is_primary = index == 0 and party.name.strip() == primary_name
        np.suggested_role = "PRINCIPAL" if is_primary else "OPPOSING"

        # 先按证照号匹配，再按名称匹配
        hit: tuple[int, str] | None = None
        match_kind = "none"
        if np.id_number and np.id_number in client_lookup:
            hit = client_lookup[np.id_number]
            match_kind = "exact_id"
        elif np.name in client_lookup:
            hit = client_lookup[np.name]
            match_kind = "exact_name"
        if hit:
            np.client_id, np.client_label = hit[0], hit[1]
            np.match_kind = match_kind
        draft.parties.append(np)

    if not draft.parties:
        draft.needs_review.append("parties")
        draft.warnings.append("未识别到合同当事人，请手工添加")

    if primary_name:
        draft.fields["client_name"] = primary_name

    # ── 3. 合同类型 ──
    case_type, case_type_ok = normalize_case_type(extraction.case_type)
    if case_type_ok:
        draft.fields["case_type"] = case_type
    else:
        draft.needs_review.append("case_type")
        draft.warnings.append(f"合同类型无法自动判定（模型给出「{extraction.case_type or '空'}」），请手工选择")

    # ── 4. 收费 ──
    fee_mode, fee_mode_ok = normalize_fee_mode(extraction.fee_mode)
    draft.fields["fee_mode"] = fee_mode
    if not fee_mode_ok:
        draft.needs_review.append("fee_mode")

    amount, amount_reason = parse_amount(extraction.amount_text)
    if amount is not None:
        if fee_mode == FeeMode.FULL_RISK.value:
            # 全风险收费不应有固定前期金额，避免把风险比例误填成金额
            draft.needs_review.append("fixed_amount")
            draft.warnings.append(f"全风险收费但检测到金额「{extraction.amount_text}」，请确认是否应填前期律师费")
        else:
            draft.fields["fixed_amount"] = str(amount)
    else:
        draft.needs_review.append("fixed_amount")
        if amount_reason:
            draft.warnings.append(amount_reason)

    custom_terms = str(extraction.custom_terms or "").strip()
    if custom_terms and not _is_redundant_terms(custom_terms, amount):
        # 模型有时把收费条款整段抬进 custom_terms，与 fixed_amount 重复展示
        draft.fields["custom_terms"] = custom_terms[:_MAX_CUSTOM_TERMS_CHARS]

    # ── 5. 日期 ──
    for field_name, raw_key in (
        ("start_date", "start_date_text"),
        ("end_date", "end_date_text"),
    ):
        raw = str(getattr(extraction, raw_key, "") or "")
        parsed, reason = parse_date(raw)
        if parsed:
            draft.fields[field_name] = parsed.isoformat()
        elif raw.strip():
            draft.needs_review.append(field_name)
            draft.warnings.append(f"{'开始' if field_name == 'start_date' else '结束'}日期：{reason}")

    sign_date, sign_reason = parse_date(extraction.sign_date_text)
    if sign_date:
        draft.fields["specified_date"] = sign_date.isoformat()
    else:
        # 签约日期常为空白落款，留空走表单默认值（今天），不必提示
        if str(extraction.sign_date_text or "").strip():
            draft.needs_review.append("sign_date")
            draft.warnings.append(f"签约日期：{sign_reason}")

    # ── 6. 律师 ──
    for lawyer in extraction.lawyers:
        name = str(lawyer.name or "").strip()
        if not name or is_law_firm_name(name):
            continue
        nl = NormalizedLawyer(
            name=name,
            law_firm=str(lawyer.law_firm or "").strip(),
            is_primary=bool(lawyer.is_primary),
        )
        key = _normalize_name_key(name)
        hit = lawyer_lookup.get(key)
        if hit:
            nl.lawyer_id, nl.lawyer_label = hit[0], hit[1]
            nl.matched = True
        draft.lawyers.append(nl)

    # ``is_primary`` 是排他语义（合同列表/详情按它认定唯一主办律师）。
    # 模型常把「乙方1、2 各指派 A、B 律师」这类并列指派全标成主办，
    # 直接采信会让页面出现多个主办律师。这里收敛为：
    # - 恰有一位标主办 → 保留；
    # - 多位或零位标主办 → 取第一位为主办（另在告警里提示人工确认）。
    _enforce_single_primary(draft)

    if draft.lawyers and not any(lw.matched for lw in draft.lawyers):
        draft.needs_review.append("lawyers")
        draft.warnings.append("未能自动匹配到系统内律师，请手工选择承办律师")
    if not draft.lawyers:
        draft.needs_review.append("lawyers")

    # ── 7. 合同名称 ──
    name = build_contract_name(
        client_name=primary_name,
        matter_summary=extraction.matter_summary,
        title=extraction.title,
        case_type=case_type,
    )
    if name:
        draft.fields["name"] = name
    else:
        draft.needs_review.append("name")

    # ── 8. 低置信度字段追加到待核对 ──
    for key, score in draft.confidence.items():
        if score < 0.6:
            mapped = _CONFIDENCE_FIELD_MAP.get(key)
            if mapped and mapped not in draft.needs_review:
                draft.needs_review.append(mapped)

    return draft


def _enforce_single_primary(draft: ContractDraft) -> None:
    """保证草稿里最多一位主办律师（:attr:`NormalizedLawyer.is_primary` 是排他语义）。"""
    lawyers = draft.lawyers
    if not lawyers:
        return
    primaries = [lw for lw in lawyers if lw.is_primary]
    if len(primaries) == 1:
        return
    for lawyer in lawyers:
        lawyer.is_primary = False
    # 主办律师必须从「能在表单里真正选中」的人里挑：未匹配到系统账号的律师
    # 前端根本填不进去，设他为主办等于没人为主办。优先已匹配者。
    matched = [lw for lw in lawyers if lw.matched]
    chosen = matched[0] if matched else lawyers[0]
    chosen.is_primary = True
    if len(primaries) > 1:
        draft.needs_review.append("lawyers")
        draft.warnings.append(
            "合同并列指派了多位律师（" + "、".join(lw.name for lw in primaries) + "），"
            f"已暂将「{chosen.name}」设为主办律师，请核对主办人选"
        )


def _is_redundant_terms(custom_terms: str, amount: Decimal | None) -> bool:
    """判定 custom_terms 是否只是重复叙述已提取的金额（避免两处展示同一信息）。"""
    if amount is None or len(custom_terms) < 20:
        return False
    # 不含金额以外的额外约定（支付节点/分期/退费）时视为冗余
    has_extra = any(
        marker in custom_terms for marker in ("分期", "逾期", "退", "解除", "违约", "节点", "百分比", "比例")
    )
    return not has_extra


def _normalize_name_key(raw: str) -> str:
    """姓名比对键：去空白、去「律师」职衔尾缀。"""
    text = str(raw or "").strip()
    text = re.sub(r"\s+", "", text)
    for suffix in ("律师", "大律师"):
        if text.endswith(suffix) and len(text) > len(suffix):
            text = text[: -len(suffix)]
    return text


#: 置信度键 → 表单字段名（用于把低分字段标进待核对列表）
_CONFIDENCE_FIELD_MAP: dict[str, str] = {
    "client_name": "client",
    "case_type": "case_type",
    "fee_mode": "fee_mode",
    "amount_text": "fixed_amount",
    "start_date_text": "start_date",
    "end_date_text": "end_date",
    "sign_date_text": "sign_date",
}
