"""事实账本：把「能从材料里读到什么」抄成带出处、带依据类型的三档事实。

## 为什么金额/日期只认实体与合同原文、不认模型推断

沿用 `facts_builder` 的既有口径：金额、日期错一个字符就是一份要重签的文书，而模型
推不出来时只会编。真机基线（D3）里「被告于 2026 年 5 月 8 日缴交履约保证金」就是模型
补的——合同只写了变更后的金额，缴交日期原文没有。所以这里不给推断「算事实」的权力：

1. 每条事实必须附一句能在材料原文里核到的引文（`source`），归一化后做包含校验；
   核不到就丢弃并记 warning——模型写不出原文引文时，那条事实通常也是编的；
2. `basis` 三档 `contract_clause` / `letter` / `inference` 把「原文抄的」与「模型推的」
   分开记，`writable_facts()` 只放行前两档：推断可以留给律师看，但不得直接进文书。

## 为什么一致性核对放在代码里

「分项加起来是否等于声称合计」「日期区间是否倒置」「日比率是否超过 0.5%/日」都能用
算术判定，不该问模型。OCR 把「每日 3‰」读成「每日 3%」（年化 1095%）时，这里直接进
`conflicts`，而不是让一个错的比率原样落到起诉状上。

## 边界

不读库、不渲染、不落盘：材料原文与模型调用口都由调用方给。模型侧任何失败（调用异常、
输出不是合法 JSON、校验不过）都折算成空账本 + `warnings`，绝不抛——与
`spec_service.resolve_slot_values` 同一纪律。
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from pydantic import BaseModel, Field

from apps.core.llm.exceptions import LLMError
from apps.core.llm.structured_output import StructuredValidationError, json_schema_instructions, retry_structured

logger = logging.getLogger(__name__)

#: 与 `spec_service.LLMCaller` 同一约定：消息列表 → 纯文本
LLMCaller = Callable[[list[dict[str, str]]], str]

#: 一份材料的账本默认上限：再多的条目律师也复核不过来，还会把提示词撑满
DEFAULT_FACT_LIMIT = 40
#: 结构化输出重试次数（首次 + 2 次把校验错误回喂给模型）
_MAX_ATTEMPTS = 3
#: 金额核对容差（一分钱）：合同金额都是两位小数，差一分才是真不一致
_AMOUNT_TOLERANCE = Decimal("0.01")
#: 日比率上限：超过 0.5%/日（年化 182.5%）在违约金/资金占用费里都属异常，多半是 OCR 把 ‰ 读成 %
_MAX_DAILY_RATE_PERCENT = Decimal("0.5")
#: 出处引文的最短长度：一两个字的片段（「甲方」）能在原文里到处命中，等于没有定位
_MIN_SOURCE_CHARS = 2

_WHITESPACE_RE = re.compile(r"[\s\u00a0\u3000]+")
#: 同时认「2026-05-08」「2026/5/8」「2026 年 5 月 8 日」三种写法；finditer 保证按出现顺序取
_DATE_RE = re.compile(r"(\d{4})\s*(?:[-/.]|年)\s*(\d{1,2})\s*(?:[-/.]|月)\s*(\d{1,2})\s*日?")
#: 日比率：只认阿拉伯数字尾随 % 或 ‰（「每日 3%」「日利率 0.05%」「每日 3‰」）
_DAILY_RATE_RE = re.compile(r"(?:每日|每天|日利率|按日|日)\s*(?:按|为)?\s*(万分之|千分之)?\s*(\d+(?:\.\d+)?)\s*(%|‰)?")
#: 金额取值：去掉货币符号/千分位/单位后必须是纯数字，避免把「第九条」当成 9 元
_PLAIN_AMOUNT_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
_AMOUNT_NOISE = ("人民币", "元", "¥", "￥", ",", "，", " ", "\u3000", "整")
#: 合计类事实的 key 标记：`欠款合计` 的「分项域」是它前面的 `欠款`
_TOTAL_KEY_MARKERS = ("合计", "总计")
_KEY_SEPARATORS = "-－—_、：: \u3000"


class FactBasis(StrEnum):
    """这条事实是抄来的还是推出来的——决定它能不能进文书。"""

    CONTRACT_CLAUSE = "contract_clause"
    LETTER = "letter"
    INFERENCE = "inference"


class ConflictKind(StrEnum):
    """一致性核对的问题类别（机器判别用；给律师看的解释在 `LedgerConflict.detail`）。"""

    AMOUNT_SUM = "amount_sum"
    DATE_RANGE = "date_range"
    DAILY_RATE = "daily_rate"
    DUPLICATE_KEY = "duplicate_key"


class LawFact(BaseModel):
    """一条带出处的事实；也是模型结构化输出的条目结构。"""

    key: str = Field(description="事实名，同一类分项共用一个前缀，如「欠款-水费」「欠款合计」")
    value: str = Field(description="原文抄录的取值（金额/日期/条款表述），不要换算、不要补全")
    source: str = Field(description="材料原文里原样出现的一段引文（10~40 字），系统会回原文核对")
    basis: FactBasis = Field(description="contract_clause=合同条款 / letter=函件 / inference=模型推断")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="抄录把握度 0~1，OCR 可疑处给低分")


class LedgerExtraction(BaseModel):
    """模型输出的外壳：只有 facts 一个字段，防止模型自造结论字段。"""

    facts: list[LawFact] = Field(default_factory=list, description="逐条事实")


@dataclass(frozen=True)
class LedgerConflict:
    """一致性核对发现的问题；`keys` 指向涉及的账本条目，供 `writable_facts()` 拦下。"""

    kind: ConflictKind
    detail: str
    keys: tuple[str, ...] = ()


@dataclass
class LedgerResult:
    """一次账本抽取的产出：事实、冲突、以及「为什么少了东西」的说明。"""

    facts: list[LawFact] = field(default_factory=list)
    conflicts: list[LedgerConflict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def writable_facts(self) -> list[LawFact]:
        """可以写进文书的事实：只放行有原文出处的两档，且不碰有冲突的条目。

        推断（`inference`）一律不返回；同一条事实有多个取值、或分项与合计对不上时，
        涉及的条目**一条都不返回**——错的可能是任何一边，猜哪边对就等于替律师改账。
        """
        blocked = {key for conflict in self.conflicts for key in conflict.keys}
        return [fact for fact in self.facts if fact.basis is not FactBasis.INFERENCE and fact.key not in blocked]


def extract_ledger(material_text: str, *, llm_caller: LLMCaller, limit: int = DEFAULT_FACT_LIMIT) -> LedgerResult:
    """把材料原文抽成带出处的事实账本，并做确定性一致性核对。

    Args:
        material_text: 材料原文（律师函、合同 OCR 文本等，多份可直接拼在一起）
        llm_caller: 模型调用口，消息列表 → 纯文本
        limit: 保留的事实条数上限（超过按模型给出的先后顺序截断，并记 warning）

    Returns:
        `LedgerResult`。模型挂掉、输出不是合法 JSON、校验不过都只返回空 facts + warnings。

    Raises:
        ValueError: `limit` < 1（调用方参数写错，不是模型侧故障，不折算成 warning）
    """
    if limit < 1:
        raise ValueError("limit 必须 >= 1")

    text = str(material_text or "").strip()
    if not text:
        return LedgerResult(warnings=["材料正文为空，账本没有可核对的对象"])

    extraction, failure = _request_extraction(text, llm_caller)
    if extraction is None:
        return LedgerResult(warnings=[failure])

    warnings: list[str] = []
    if not extraction.facts:
        warnings.append("模型没有从材料里抽到任何事实")
    facts = _locatable_facts(extraction.facts, text, warnings)
    if len(facts) > limit:
        warnings.append(f"事实条数 {len(facts)} 超过上限 {limit}，已截断")
        facts = facts[:limit]
    return LedgerResult(facts=facts, conflicts=_check_conflicts(facts), warnings=warnings)


def _request_extraction(material_text: str, llm_caller: LLMCaller) -> tuple[LedgerExtraction | None, str]:
    """一次结构化抽取（含把校验错误回喂的重试）。

    Returns:
        `(抽取结果, 失败说明)`；成功时说明为空串。失败说明区分「输出不合 JSON」与「模型
        调用失败」——两种情况都可能出现，混成一句会让律师去查错方向。
    """

    def responder(last_error: StructuredValidationError | None) -> str:
        return llm_caller(_ledger_messages(material_text, last_error))

    try:
        return retry_structured(model_cls=LedgerExtraction, responder=responder, max_attempts=_MAX_ATTEMPTS), ""
    except StructuredValidationError as exc:
        logger.warning("事实账本输出无法解析，本次不产出事实: %s", exc)
        return None, f"模型输出无法解析为事实账本（已重试 {_MAX_ATTEMPTS} 次），本次不产出事实"
    except (LLMError, TimeoutError, ValueError, RuntimeError) as exc:
        # 与 `spec_service._llm_write` 同一失败面收窄：模型侧故障才吞，程序性错误照常抛
        logger.warning("事实账本抽取调用模型失败，本次不产出事实", exc_info=True)
        return None, f"账本抽取调用模型失败（{type(exc).__name__}），本次不产出事实"


def _ledger_messages(material_text: str, last_error: StructuredValidationError | None) -> list[dict[str, str]]:
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"## 材料原文\n{material_text}\n\n## 输出格式\n{json_schema_instructions(LedgerExtraction)}",
        },
    ]
    if last_error is not None:
        messages.append({"role": "user", "content": last_error.feedback_message})
    return messages


_SYSTEM_PROMPT = """\
你是律所的事实账本整理助手。用户会给你材料原文（律师函、合同扫描 OCR 文本等），\
请把能读到的事实逐条抄进账本，供律师复核后写进文书。

铁律（违反会被系统直接丢弃）：
1. **只抄原文**。每条 fact 的 `source` 必须是原文中**原样出现**的一段文字（10~40 字，\
不要改写、不要用省略号拼接）；系统会拿它回原文核对，核不到这条就作废。
2. `basis` 三档：`contract_clause`=合同/协议条款原文；`letter`=律师函等函件原文；\
`inference`=由多条信息推出、原文没有明说的（如缴交日期、合计金额）。推断可以记，\
但系统不会让推断直接进文书。
3. 金额、日期按原文写法抄（保留千分位和「元」），**不要换算、不要补全、不要推算**。
4. `key` 用简短中文短语；同一类分项共用一个前缀，合计用「前缀+合计」，例如：\
`欠款-管理维护费`、`欠款-水费`、`欠款合计`——系统靠这个前缀核对分项之和是否等于合计。
5. 原文没有的类别不要硬凑；同一件事只记一条，原文前后矛盾时两条都记，系统会做一致性核对。
6. 覆盖范围：当事人、合同编号、签订日、标的（地块/面积）、期限、各项费用金额与到期规则、\
保证金、解除条件、管辖、催告、欠款明细。
7. `confidence` 如实给 0~1：照抄通常 0.9 以上，OCR 字形可疑处给低分。"""


def _locatable_facts(raw_facts: list[LawFact], material_text: str, warnings: list[str]) -> list[LawFact]:
    """只留能在材料原文里核到出处的事实；核不到的丢弃并记账。"""
    haystack = _normalize(material_text)
    kept: list[LawFact] = []
    for fact in raw_facts:
        key = fact.key.strip()
        value = fact.value.strip()
        if not key or not value:
            warnings.append(f"事实缺少 key 或 value，已丢弃: {key or '（空 key）'}")
            continue
        if not _source_is_locatable(fact.source, haystack):
            warnings.append(f"出处核对失败，已丢弃: {key}")
            continue
        kept.append(fact.model_copy(update={"key": key, "value": value, "source": fact.source.strip()}))
    return kept


def _source_is_locatable(source: str, normalized_material: str) -> bool:
    normalized_source = _normalize(source)
    return len(normalized_source) >= _MIN_SOURCE_CHARS and normalized_source in normalized_material


def _normalize(text: str) -> str:
    """比对用归一化：全半角折成 NFKC + 去掉空白（OCR 常在词中间塞空格）。

    只用于**核对**，不用于落笔——写进文书时必须用账本里抄下来的原文，否则律师看到的
    引文和系统核对的那一段对不上。
    """
    return _WHITESPACE_RE.sub("", unicodedata.normalize("NFKC", text or "")).lower()


def _check_conflicts(facts: list[LawFact]) -> list[LedgerConflict]:
    conflicts = _duplicate_key_conflicts(facts)
    conflicts.extend(_date_range_conflicts(facts))
    conflicts.extend(_daily_rate_conflicts(facts))
    conflicts.extend(_amount_sum_conflicts(facts))
    return conflicts


def _duplicate_key_conflicts(facts: list[LawFact]) -> list[LedgerConflict]:
    """同一个 key 出现多个不同取值：原文可能自相矛盾，也可能模型抄错了一处。"""
    values_by_key: dict[str, list[str]] = {}
    seen: dict[str, set[str]] = {}
    for fact in facts:
        normalized = _normalize(fact.value)
        bucket = seen.setdefault(fact.key, set())
        if normalized in bucket:
            continue
        bucket.add(normalized)
        values_by_key.setdefault(fact.key, []).append(fact.value)
    return [
        LedgerConflict(
            kind=ConflictKind.DUPLICATE_KEY,
            detail=f"同一事实出现 {len(values)} 个取值: {key} = {' / '.join(values)}",
            keys=(key,),
        )
        for key, values in values_by_key.items()
        if len(values) > 1
    ]


def _date_range_conflicts(facts: list[LawFact]) -> list[LedgerConflict]:
    """一个取值里带两个日期时，顺序不能倒：倒了要么是抄反了，要么是原文本身有问题。"""
    conflicts: list[LedgerConflict] = []
    for fact in facts:
        dates = _dates_in(fact.value)
        if len(dates) < 2:
            continue
        start, end = dates[0], dates[-1]
        if start <= end:
            continue
        conflicts.append(
            LedgerConflict(
                kind=ConflictKind.DATE_RANGE,
                detail=f"日期区间倒置: {fact.key} 起 {_format_date(start)} 晚于 止 {_format_date(end)}",
                keys=(fact.key,),
            )
        )
    return conflicts


def _dates_in(value: str) -> list[tuple[int, int, int]]:
    dates: list[tuple[int, int, int]] = []
    for year, month, day in _DATE_RE.findall(value):
        parsed = (int(year), int(month), int(day))
        if 1 <= parsed[1] <= 12 and 1 <= parsed[2] <= 31:
            dates.append(parsed)
    return dates


def _format_date(value: tuple[int, int, int]) -> str:
    return f"{value[0]:04d}-{value[1]:02d}-{value[2]:02d}"


def _daily_rate_conflicts(facts: list[LawFact]) -> list[LedgerConflict]:
    conflicts: list[LedgerConflict] = []
    for fact in facts:
        percent = _daily_rate_percent(fact.value)
        if percent is None or percent <= _MAX_DAILY_RATE_PERCENT:
            continue
        conflicts.append(
            LedgerConflict(
                kind=ConflictKind.DAILY_RATE,
                detail=f"日比率异常: {fact.key} 折算每日 {_format_decimal(percent)}%，超过 0.5%/日 上限"
                "（常见成因：OCR 把「‰」读成「%」）",
                keys=(fact.key,),
            )
        )
    return conflicts


def _daily_rate_percent(value: str) -> Decimal | None:
    """把「每日 3%」「日利率 0.05%」「每日 3‰」折算成每日百分比；不是日比率的取值返回 None。

    只认阿拉伯数字：原文写「每日万分之五」这类中文数字时不折算——本函数是**异常哨兵**，
    不是利率计算器，漏判一条只少一个提示，误判一条会让律师去查一个不存在的问题。
    """
    match = _DAILY_RATE_RE.search(value)
    if match is None:
        return None
    unit, raw_number, symbol = match.groups()
    number = Decimal(raw_number)
    if unit == "万分之":
        return number / 100
    if unit == "千分之":
        return number / 10
    if symbol == "%":
        return number
    if symbol == "‰":
        return number / 10
    return None


def _amount_sum_conflicts(facts: list[LawFact]) -> list[LedgerConflict]:
    """同前缀的分项之和必须等于「前缀+合计」；对不上就把涉及的条目全部标冲突。"""
    conflicts: list[LedgerConflict] = []
    for total in facts:
        marker = _total_marker(total.key)
        if marker is None:
            continue
        total_amount = _single_amount(total.value)
        if total_amount is None:
            continue
        domain = total.key[: total.key.find(marker)].strip(_KEY_SEPARATORS)
        if not domain:
            continue
        parts = _parts_in_domain(facts, domain=domain, total_key=total.key)
        if len(parts) < 2:
            continue
        parts_sum = sum((amount for _, amount in parts), start=Decimal("0"))
        if abs(total_amount - parts_sum) <= _AMOUNT_TOLERANCE:
            continue
        conflicts.append(
            LedgerConflict(
                kind=ConflictKind.AMOUNT_SUM,
                detail=(
                    f"分项合计不符: {total.key}={_format_decimal(total_amount)}，"
                    f"分项之和={_format_decimal(parts_sum)}（容差 0.01）"
                ),
                keys=(total.key, *(key for key, _ in parts)),
            )
        )
    return conflicts


def _parts_in_domain(facts: list[LawFact], *, domain: str, total_key: str) -> list[tuple[str, Decimal]]:
    parts: list[tuple[str, Decimal]] = []
    for fact in facts:
        if fact.key == total_key or _total_marker(fact.key) is not None:
            continue
        if not fact.key.startswith(domain):
            continue
        amount = _single_amount(fact.value)
        if amount is not None:
            parts.append((fact.key, amount))
    return parts


def _total_marker(key: str) -> str | None:
    for marker in _TOTAL_KEY_MARKERS:
        if marker in key:
            return marker
    return None


def _single_amount(value: str) -> Decimal | None:
    """取值本身就是一个金额（可带货币符号/千分位/「元」）时返回它，否则 None。"""
    text = value.strip()
    for token in _AMOUNT_NOISE:
        text = text.replace(token, "")
    if not _PLAIN_AMOUNT_RE.match(text):
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _format_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


__all__ = [
    "DEFAULT_FACT_LIMIT",
    "ConflictKind",
    "FactBasis",
    "LawFact",
    "LedgerConflict",
    "LedgerResult",
    "extract_ledger",
]
