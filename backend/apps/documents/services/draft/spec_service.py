"""一句话起草的规格解析：doc_type → DocumentSpec → 骨架占位符的取值。

## 为什么 context 的键只能是骨架里真实存在的占位符
渲染器是 docxtpl，它只会替换骨架里写着的 `{{x}}`。凭空造一个键不会进成稿，
只会让「已填充」变成幻觉；所以这里先取骨架的占位符清单（复用现有 extractor，
不另写一套正则），再决定每个槽归谁，最后按骨架认领——没认领到的就是未决项。

## 段的落点怎么定（三档，先显式后惯例）
1. 规格声明的 `claim_slot_key` / `facts_slot_key` 恰好是骨架占位符；
2. 规格的小标题（如「事实与理由：」）出现在某个占位符名里；
3. 骨架族的标准节名（litigation_v1 脊柱上的请求段 / 事实段）。

三档都没命中时，这一段的内容没有落点：请求段并入事实段（答辩状这类骨架只有一个
正文占位符），事实段记 warning 并保持空——绝不悄悄另起一个占位符。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from apps.core.exceptions import ValidationException
from apps.core.llm.exceptions import LLMError
from apps.core.llm.structured_output import StructuredValidationError
from apps.documents.models import DocumentSpec
from apps.documents.models.document_spec import SlotSource
from apps.documents.services.document_template.placeholder_extractor import extract_placeholders
from apps.documents.services.draft.facts_builder import MATERIAL_FACTS_KEY, build_facts

logger = logging.getLogger(__name__)

#: 与 `apps.doc_workspace.services.draft_service.LLMCaller` 同一约定：消息列表 → 纯文本
LLMCaller = Callable[[list[dict[str, str]]], str]

#: 骨架族的标准节名：规格没声明落点时按这条脊柱认领（实测：起诉状/保全申请/执行申请的节名都在里面）
_FAMILY_SECTION_HINTS: dict[str, dict[str, tuple[str, ...]]] = {
    "litigation_v1": {
        "claim": ("诉讼请求", "申请事项", "申请执行事项"),
        "facts": ("事实与理由", "答辩理由"),
    },
}

_SECTION_LABELS: dict[str, str] = {"claim": "请求事项", "facts": "事实与理由"}

_SECTION_INSTRUCTIONS: dict[str, str] = {
    "claim": "逐项列出请求事项，每项单独一行；不要写「请求事项」这类小标题，也不要解释理由。",
    "facts": "分段陈述事实与理由，每段单独一行，按时间顺序或争议焦点组织；不要写小标题。",
}

#: 判空口径与 `draft_service` 一致：模型很爱回「待定」「无」，写进文书就是坑
_NON_ANSWERS = frozenset({"", "待定", "未知", "无", "n/a", "na", "null", "none", "-", "—", "tbd", "todo"})


def get_spec(doc_type: str) -> DocumentSpec | None:
    """按文书类型取规格；没有或已停用都返回 None（停用等价于「还没有这个骨架」）。"""
    key = str(doc_type or "").strip()
    if not key:
        return None
    return DocumentSpec.objects.filter(doc_type=key, is_active=True).first()


def list_specs(*, active_only: bool = True) -> list[DocumentSpec]:
    """列出规格（默认只列启用的），按骨架族与类型名排序供选择器使用。"""
    queryset = DocumentSpec.objects.all()
    if active_only:
        queryset = queryset.filter(is_active=True)
    return list(queryset.order_by("family", "doc_type"))


def resolve_slot_values(
    spec: DocumentSpec,
    *,
    case: Any = None,
    contract: Any = None,
    facts: dict[str, str] | None = None,
    llm_caller: LLMCaller | None = None,
) -> tuple[dict[str, str], list[str]]:
    """把规格 + 事实解析成骨架的渲染上下文。

    Returns:
        `(context, pending_keys)`。context 的键全是骨架里真实存在的占位符；
        pending_keys 是既没素材也没写出来的槽（骨架占位符名，或附加槽位的标签）。
        本函数**不抛异常**：缺素材、模型挂掉、事实组装失败都只进 pending。
    """
    placeholders = _skeleton_placeholders(spec)
    if not placeholders:
        # 没有骨架就没有可渲染的槽：规格声明过哪些槽就报哪些，绝不凭空造键
        logger.warning("文书规格没有可读骨架，全部槽位按未决处理: doc_type=%s", spec.doc_type)
        return {}, _declared_slot_names(spec)

    available = set(placeholders)
    fact_values = _safe_facts(spec, case=case, contract=contract, explicit=facts)
    context: dict[str, str] = {}
    pending: list[str] = []

    extra_values, extra_missing = _resolve_extra_slots(spec, available=available, facts=fact_values)
    context.update(extra_values)
    pending.extend(extra_missing)

    # 附加槽位常常正是请求/事实段要引用的前提事实（如「原受理法院」），一并喂给模型
    material = dict(fact_values)
    material.update({key: value for key, value in extra_values.items() if key not in material})

    claim_target = _section_target(spec, "claim", available)
    facts_target = _section_target(spec, "facts", available)
    claim_value = _section_value(spec, "claim", facts=fact_values, material=material, llm_caller=llm_caller)
    facts_value = _section_value(spec, "facts", facts=fact_values, material=material, llm_caller=llm_caller)

    _place_sections(
        spec,
        context,
        claim_target=claim_target,
        claim_value=claim_value,
        facts_target=facts_target,
        facts_value=facts_value,
    )

    # 事实里同名的键直接填同名占位符（原告、案由、审理机构…）：实体字段本来就该原样进文档
    for name in placeholders:
        if name in context:
            continue
        value = _answer(fact_values.get(name))
        if value:
            context[name] = value

    pending.extend(name for name in placeholders if name not in context)
    return context, _dedupe(pending)


def _place_sections(
    spec: DocumentSpec,
    context: dict[str, str],
    *,
    claim_target: str | None,
    claim_value: str,
    facts_target: str | None,
    facts_value: str,
) -> None:
    """把两段内容按落点写进 context（请求段没独立落点时并入事实段开头）。"""
    if claim_value and claim_target:
        context[claim_target] = claim_value
        claim_merged = False
    elif claim_value and facts_target and facts_value:
        # 答辩状这类骨架只有一个正文占位符：请求段并到事实段开头，
        # 而不是把律所写死的固定文案静默丢掉（丢掉等于少一句答辩请求）
        logger.info("请求段没有独立占位符，已并入事实段: doc_type=%s", spec.doc_type)
        claim_merged = True
    else:
        if claim_value:
            logger.warning("请求段有内容但骨架里没有落点，内容未进成稿: doc_type=%s", spec.doc_type)
        claim_merged = False

    if facts_value and facts_target:
        context[facts_target] = f"{claim_value}\n{facts_value}" if claim_merged else facts_value
    elif facts_value:
        logger.warning("事实段有内容但骨架里没有落点，内容未进成稿: doc_type=%s", spec.doc_type)


def _skeleton_placeholders(spec: DocumentSpec) -> list[str]:
    """骨架 docx 里的占位符清单（复用现有 extractor：docxtpl 未声明变量 + 段落/表格扫描）。"""
    template = spec.skeleton_template
    if template is None:
        return []
    location = template.get_file_location()
    if not location:
        logger.warning("骨架模板没有可用文件: doc_type=%s template_id=%s", spec.doc_type, template.pk)
        return []
    return extract_placeholders(location)


def _safe_facts(spec: DocumentSpec, *, case: Any, contract: Any, explicit: dict[str, str] | None) -> dict[str, str]:
    try:
        return build_facts(case=case, contract=contract, explicit=explicit)
    except (ValidationException, AttributeError, KeyError, TypeError, LookupError):
        # 事实组装失败不该让整份起草失败：退回调用方显式给的那几条，其余走未决。
        # 只接「数据形状不对」这一类——它们来自实体字段缺失或 DTO 变更；程序性错误
        # （NameError/ImportError 等）照常抛，否则真 bug 会被这条兜底永久掩盖。
        logger.warning("事实组装失败，退回调用方显式事实: doc_type=%s", spec.doc_type, exc_info=True)
        return {str(key): _answer(value) for key, value in (explicit or {}).items() if _answer(value)}


def _section_target(spec: DocumentSpec, section: str, available: set[str]) -> str | None:
    """这一段该填到哪个骨架占位符（显式声明 > 小标题 > 骨架族标准节名）。"""
    explicit = _answer(getattr(spec, f"{section}_slot_key", ""))
    if explicit:
        if explicit in available:
            return explicit
        logger.warning("规格声明的槽位不在骨架里，改按小标题/骨架族认领: doc_type=%s key=%s", spec.doc_type, explicit)

    target = _match_placeholder(available, _answer(getattr(spec, f"{section}_heading", "")).rstrip("：:"))
    if target:
        return target

    hints = _FAMILY_SECTION_HINTS.get(str(spec.family), {}).get(section, ())
    for hint in hints:
        target = _match_placeholder(available, hint)
        if target:
            return target
    return None


def _match_placeholder(names: Iterable[str], text: str) -> str | None:
    """在占位符名里找与 text 对应的那个：先精确，再互相包含。"""
    if not text:
        return None
    ordered = sorted(names)
    for name in ordered:
        if name == text:
            return name
    for name in ordered:
        if text in name or name in text:
            return name
    return None


def _section_value(
    spec: DocumentSpec,
    section: str,
    *,
    facts: dict[str, str],
    material: dict[str, str],
    llm_caller: LLMCaller | None,
) -> str:
    source = _answer(getattr(spec, f"{section}_source", "")) or str(SlotSource.LLM.value)
    if source == SlotSource.SLOT:
        key = _answer(getattr(spec, f"{section}_slot_key", ""))
        return _answer(facts.get(key, "")) if key else ""
    if source == SlotSource.FIXED:
        if section != "claim":
            # 事实段没有固定文案字段：把 facts_source 设成 fixed 是配置错误，别当空文处理
            logger.warning("事实段没有固定文案字段，按未决处理: doc_type=%s", spec.doc_type)
            return ""
        return _answer(spec.claim_text)
    if source == SlotSource.LLM:
        if llm_caller is None:
            return ""
        return _llm_write(spec, section, material=material, llm_caller=llm_caller)
    logger.warning("未知的槽位来源: doc_type=%s section=%s source=%s", spec.doc_type, section, source)
    return ""


def _llm_write(
    spec: DocumentSpec,
    section: str,
    *,
    material: dict[str, str],
    llm_caller: LLMCaller,
) -> str:
    try:
        raw = llm_caller(_build_messages(spec, section, material=material))
    except (LLMError, TimeoutError, StructuredValidationError, ValueError, RuntimeError):
        # 模型超时/报错/输出不合 schema 不让整份起草失败：这一段转未决项，其余槽照常填。
        # 收窄到「模型侧故障」：LLMError/超时/schema 校验失败/ValueError，以及
        # RuntimeError——`litigation_llm_generator` 在「结构化调用失败且无异常对象」时
        # 抛的就是它，属真实失败面。其余程序性错误照常抛——否则模板写错、拼串写错都会被
        # 伪装成「模型没写出来」，成稿里只剩一串 <待填写>。
        logger.warning("模型撰写失败，该段转未决: doc_type=%s section=%s", spec.doc_type, section, exc_info=True)
        return ""
    return _answer(raw)


def _build_messages(spec: DocumentSpec, section: str, *, material: dict[str, str]) -> list[dict[str, str]]:
    heading = _answer(getattr(spec, f"{section}_heading", "")) or _SECTION_LABELS.get(section, "")
    system = [
        "你在为一律所起草法律文书，只写本节正文：不写标题、不加序号、不重复小标题。",
        f"文书：{spec.display_name}；我方称谓：{_answer(spec.party_label) or '未指定'}；本节：{heading}",
    ]
    brief = _answer(spec.ai_brief)
    if brief:
        system.append(f"写作要点：{brief}")
    system.append("规则：只能使用给定事实里能推出的信息，不许编造金额、日期、主体名称；推不出来的内容宁可不写。")

    facts_lines = [
        f"- {key}: {value}" for key, value in material.items() if key != MATERIAL_FACTS_KEY and _answer(value)
    ] or ["- （没有可用事实）"]
    parts = ["## 已知事实", *facts_lines]
    excerpt = _answer(material.get(MATERIAL_FACTS_KEY))
    if excerpt:
        # 材料摘录单独成节：它是长文本，混在键值对里模型会当成某一条事实的值
        parts.extend(["", "## 材料摘录", excerpt])
    parts.extend(["", "## 本节要求", _SECTION_INSTRUCTIONS.get(section, "")])

    return [
        {"role": "system", "content": "\n".join(system)},
        {"role": "user", "content": "\n".join(parts)},
    ]


def _resolve_extra_slots(
    spec: DocumentSpec, *, available: set[str], facts: dict[str, str]
) -> tuple[dict[str, str], list[str]]:
    """附加槽位：既是喂给模型的素材，也是律师必须补齐的事实清单。"""
    values: dict[str, str] = {}
    missing: list[str] = []
    for slot in _extra_slot_items(spec):
        key = _answer(slot.get("key"))
        if not key:
            continue
        label = _answer(slot.get("label")) or key
        value = _extra_slot_value(spec, slot, key=key, facts=facts)
        if not value:
            missing.append(label)
            continue
        if key in available:
            values[key] = value
    return values, missing


def _extra_slot_value(spec: DocumentSpec, slot: dict[str, Any], *, key: str, facts: dict[str, str]) -> str:
    source = _answer(slot.get("source")) or str(SlotSource.SLOT.value)
    if source != SlotSource.SLOT:
        # 附加槽位的语义就是「一条事实」：模型不能编，固定文案也没有对应字段
        logger.warning(
            "附加槽位只支持 source=slot，已按未决处理: doc_type=%s key=%s source=%s", spec.doc_type, key, source
        )
        return ""
    return _answer(facts.get(key, ""))


def _extra_slot_items(spec: DocumentSpec) -> list[dict[str, Any]]:
    items = spec.extra_slots or []
    if not isinstance(items, list):
        logger.warning("附加槽位配置不是数组，已忽略: doc_type=%s", spec.doc_type)
        return []
    return [item for item in items if isinstance(item, dict)]


def _declared_slot_names(spec: DocumentSpec) -> list[str]:
    """骨架不可读时，规格声明过哪些槽就报哪些（宁多报，不静默留空）。"""
    names = [_answer(spec.claim_slot_key), _answer(spec.facts_slot_key)]
    names.extend(_answer(slot.get("label")) or _answer(slot.get("key")) for slot in _extra_slot_items(spec))
    return _dedupe([name for name in names if name])


def _answer(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in _NON_ANSWERS else text


def _dedupe(names: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(names))


__all__ = ["LLMCaller", "get_spec", "list_specs", "resolve_slot_values"]
