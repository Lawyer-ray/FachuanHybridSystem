"""立案前「材料够不够」的判断：模型只能填要件，结论由代码里的确定性闸门给。

## 为什么要件来自数据、结论来自代码
如果让模型决定「这个案子法律上需要哪几条」，每次跑出来的清单都不一样，律师无法复核，
也解释不了「为什么这次说缺、下次说不缺」。所以：

- 要件清单来自 `element_profiles`（同一案由永远同一套 key）；
- 模型只回答「这一条在本案对应什么事实、出处在哪、是否具备」；
- `blocked / draftable_with_gaps / ready` 三档由本模块的硬闸门算出来，与模型措辞无关。

## 为什么失败一律 unknown 而不是抛
这是起草前的判断，不是起草本身。模型超时、网关 429、输出不是 JSON 都会发生；
把它抛出去会让「先看看缺什么」这种最轻的动作变成 500。unknown 的含义是「这次没判断
出来」，不是「材料齐了」——矩阵铺满 missing，律师看到的仍是完整要件面，只是没有逐条比对。

## 模型能碰到什么
只给材料摘录与结构化事实，system prompt 明确禁止补写材料里没有的主体/金额/日期；
材料摘录硬截断到 `MATERIAL_SUMMARY_LIMIT` 字并声明「可能不完整」，避免拿前 2000 字
合同去断言第九条解除权不存在。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

from apps.core.llm.exceptions import LLMError
from apps.core.llm.structured_output import StructuredValidationError, json_schema_instructions, retry_structured

from .element_profiles import ElementProfile, ElementRequirement, pick_profile

logger = logging.getLogger(__name__)

#: 与 `spec_service.LLMCaller` 同一约定：消息列表 → 纯文本
LLMCaller = Callable[[list[dict[str, str]]], str]

#: 材料摘录上限：14 页扫描件 OCR 两万多字，整篇塞进去模型会围着无关段落烧上下文，
#: 而决定「够不够」的往往只是付款条款、催告事实与主体信息。
MATERIAL_SUMMARY_LIMIT = 6000

#: 无 blocking 缺口时，要件缺失达到这个数就不该直接出稿（报告 4.1 的闸门口径）
MISSING_GATE = 3

Verdict = Literal["ready", "draftable_with_gaps", "blocked", "unknown"]
Status = Literal["met", "partial", "missing"]
Severity = Literal["blocking", "amount", "defense"]

VERDICT_READY: Verdict = "ready"
VERDICT_DRAFTABLE_WITH_GAPS: Verdict = "draftable_with_gaps"
VERDICT_BLOCKED: Verdict = "blocked"
VERDICT_UNKNOWN: Verdict = "unknown"

_MAX_ATTEMPTS = 3
_ERROR_DETAIL_CHARS = 200

SYSTEM_PROMPT = """你是律所立案前的材料审查助手。律师要判断「手上的材料够不够支撑这个案子」，你要把材料逐条对到要件上。

硬规则：
1. 只能使用本次给出的材料与已知事实。材料里没有出现的主体名称、金额、日期、合同条款，一律不得写进 fact 或 source；宁可写 status=missing，也不要补一个看起来合理的内容。
2. 只能对「要件清单」里的 requirement_key 逐条打分，不得新增、改写或遗漏 key。
3. status 三档：met = 材料里有可直接引用的内容且 source 能指到出处；partial = 有线索但材料不完整或需核对（fact 写清已知与待核）；missing = 材料里没有。
4. fact 只写能落到材料上的事实，不写推理过程、不写「可能需要」；没有出处就降为 partial 或 missing。
5. missing_materials 只列为了满足要件还必须补的材料；severity 取 blocking（不补就无法立案或无法证明核心事实）、amount（影响金额认定）、defense（影响抗辩应对）。
6. questions 只问材料回答不了、需要向委托人或经办人核实的问题；能在材料里找到答案的不要问。"""


class _RequirementItem(BaseModel):
    """模型对单条要件的比对结果。"""

    requirement_key: str = ""
    fact: str = ""
    source: str = ""
    status: Status = "missing"


class _MissingMaterialItem(BaseModel):
    """模型给出的缺口材料。"""

    item: str = ""
    why: str = ""
    from_whom: str = ""
    form: str = ""
    severity: Severity = "amount"


class _QuestionItem(BaseModel):
    """模型给出的核实问题。"""

    to: str = ""
    question: str = ""
    why: str = ""


class _Assessment(BaseModel):
    """一次结构化评估的完整输出（模型只能填这个形状）。"""

    items: list[_RequirementItem] = Field(default_factory=list)
    missing_materials: list[_MissingMaterialItem] = Field(default_factory=list)
    questions: list[_QuestionItem] = Field(default_factory=list)


@dataclass
class ReadinessResult:
    """立案前判断结果：所有字段都是可 JSON 序列化的 dict/list。"""

    verdict: Verdict
    profile_key: str
    matrix: list[dict[str, Any]] = field(default_factory=list)
    missing_materials: list[dict[str, str]] = field(default_factory=list)
    questions: list[dict[str, str]] = field(default_factory=list)
    blocking: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def assess(
    *,
    facts: dict[str, str] | None = None,
    material_summary: str = "",
    cause_of_action: str = "",
    llm_caller: LLMCaller | None = None,
    materials: list[str] | None = None,
) -> ReadinessResult:
    """判断现有材料够不够支撑这个案子，并给出缺口清单与核实问题。

    Args:
        facts: 结构化事实（键为中文事实名），优先级最高；不传等于没有结构化事实。
        material_summary: 材料摘录（合同/律师函 OCR 等），会被截断到 6000 字。
        cause_of_action: 案由，决定命中哪份要件档案；空串落到兜底档案。
        llm_caller: 与 `spec_service.LLMCaller` 同约定；为 None 时直接 unknown。
        materials: 额外的材料片段，与 `material_summary` 拼成同一段摘录后再截断——
            两个参数都进同一个 6000 字预算，否则上限会被第二份材料绕过。

    Returns:
        判断结果。**本函数不抛异常**：模型缺失/超时/输出不合法一律 unknown。
    """
    # 案由常常只有一个大类（真机 case 489 是「合同纠纷」），用材料抬头补足档案选择
    # 案由常只有大类（真机 case 489 是「合同纠纷」），用**整段材料**补足档案选择：
    # 不能只看头部 500 字——合同的「承包金/土地」往往出现在第 2 页之后
    profile = pick_profile(cause_of_action, hint=material_summary)
    warnings: list[str] = []
    material_excerpt, truncated = _material_excerpt(material_summary, materials=materials)
    if truncated:
        warnings.append(f"材料摘要超过 {MATERIAL_SUMMARY_LIMIT} 字，仅使用前 {MATERIAL_SUMMARY_LIMIT} 字摘录")

    if llm_caller is None:
        logger.warning("立案前材料评估缺少 llm_caller，按 unknown 返回: profile=%s", profile.key)
        warnings.append("未提供 llm_caller：没有做要件事实比对，全部要件按缺失处理")
        return _unknown_result(profile, warnings)

    messages = _build_messages(
        profile=profile,
        facts=facts or {},
        cause_of_action=cause_of_action,
        material_excerpt=material_excerpt,
        truncated=truncated,
    )
    try:
        assessment = _request_assessment(messages=messages, llm_caller=llm_caller)
    except StructuredValidationError as exc:
        logger.warning("立案前材料评估输出无法解析: profile=%s", profile.key)
        warnings.append(f"模型输出无法解析成约定结构（重试 {_MAX_ATTEMPTS} 次后仍失败）：{_brief(exc)}")
        return _unknown_result(profile, warnings)
    except (LLMError, TimeoutError, ConnectionError, OSError, RuntimeError, ValueError) as exc:
        # 只收「模型侧故障」，与 `spec_service._llm_write` 同口径：LLM 网关/超时/解析/
        # 生成器 RuntimeError。不收宽异常——仓库棘轮只许下调；程序性错误（NameError/
        # AttributeError 等）照常抛，否则真 bug 会被 unknown 永久掩盖。
        logger.warning("立案前材料评估调用失败，按 unknown 返回: profile=%s", profile.key, exc_info=True)
        warnings.append(f"模型调用失败（{type(exc).__name__}）：{_brief(exc)}")
        return _unknown_result(profile, warnings)

    result = _build_result(profile=profile, assessment=assessment, warnings=warnings)
    logger.info(
        "立案前材料评估完成: profile=%s verdict=%s missing=%d blocking=%d",
        profile.key,
        result.verdict,
        _missing_count(result.matrix),
        len(result.blocking),
    )
    return result


def _request_assessment(*, messages: list[dict[str, str]], llm_caller: LLMCaller) -> _Assessment:
    """走受控结构化输出：校验失败时把错误回喂给模型，最多重试 `_MAX_ATTEMPTS` 次。"""

    def responder(last_error: StructuredValidationError | None) -> str:
        if last_error is None:
            return llm_caller(messages)
        return llm_caller([*messages, {"role": "user", "content": last_error.feedback_message}])

    return retry_structured(model_cls=_Assessment, responder=responder, max_attempts=_MAX_ATTEMPTS)


def _build_result(
    *,
    profile: ElementProfile,
    assessment: _Assessment,
    warnings: list[str],
) -> ReadinessResult:
    """把模型输出对回档案，并按硬闸门给结论。"""
    matrix = _build_matrix(profile, assessment.items, warnings)
    missing_materials = _missing_material_dicts(assessment.missing_materials, warnings)
    blocking = list(dict.fromkeys(item["item"] for item in missing_materials if item["severity"] == "blocking"))

    if blocking:
        verdict: Verdict = VERDICT_BLOCKED
    elif _missing_count(matrix) >= MISSING_GATE:
        verdict = VERDICT_DRAFTABLE_WITH_GAPS
    else:
        verdict = VERDICT_READY

    return ReadinessResult(
        verdict=verdict,
        profile_key=profile.key,
        matrix=matrix,
        missing_materials=missing_materials,
        questions=_question_dicts(assessment.questions),
        blocking=blocking,
        warnings=list(warnings),
    )


def _build_matrix(
    profile: ElementProfile,
    items: list[_RequirementItem],
    warnings: list[str],
) -> list[dict[str, Any]]:
    """逐条对回档案：未知 key 丢弃并记 warning，漏答的补 missing。

    为什么矩阵必须以档案为准而不是以模型 items 为准：模型偶尔会漏掉一两条（尤其要件多
    的时候），如果直接拿 items 当矩阵，律师看到的就是一份「只有 9 条」的要件面，缺的那
    三条永远没人知道。档案是全集，模型输出只是其中一份答案。
    """
    known = {requirement.key for requirement in profile.requirements}
    assessed: dict[str, _RequirementItem] = {}
    for item in items:
        key = item.requirement_key.strip()
        if not key:
            warnings.append("模型返回了缺少 requirement_key 的条目，已丢弃")
            continue
        if key not in known:
            warnings.append(f"模型给出档案里没有的要件 key={key}，已丢弃")
            continue
        if key in assessed:
            warnings.append(f"模型重复给出要件 key={key}，保留第一条")
            continue
        assessed[key] = item

    omitted = [requirement.key for requirement in profile.requirements if requirement.key not in assessed]
    if omitted:
        warnings.append(f"模型漏答 {len(omitted)} 个要件，矩阵已按缺失补齐：{', '.join(omitted)}")

    return [_matrix_row(requirement, assessed.get(requirement.key)) for requirement in profile.requirements]


def _matrix_row(requirement: ElementRequirement, item: _RequirementItem | None) -> dict[str, Any]:
    return {
        "requirement_key": requirement.key,
        "requirement": requirement.label,
        "why": requirement.why,
        "evidence_forms": list(requirement.evidence_forms),
        "fact": (item.fact if item else "").strip(),
        "source": (item.source if item else "").strip(),
        "status": item.status if item else "missing",
    }


def _missing_material_dicts(items: list[_MissingMaterialItem], warnings: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in items:
        name = item.item.strip()
        if not name:
            warnings.append("模型返回了没有 item 名称的缺口，已丢弃")
            continue
        rows.append(
            {
                "item": name,
                "why": item.why.strip(),
                "from_whom": item.from_whom.strip(),
                "form": item.form.strip(),
                "severity": item.severity,
            }
        )
    return rows


def _question_dicts(items: list[_QuestionItem]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in items:
        question = item.question.strip()
        if not question:
            continue
        rows.append({"to": item.to.strip(), "question": question, "why": item.why.strip()})
    return rows


def _missing_count(matrix: list[dict[str, Any]]) -> int:
    return sum(1 for row in matrix if row["status"] == "missing")


def _unknown_result(profile: ElementProfile, warnings: list[str]) -> ReadinessResult:
    """没判断出来时的结果：要件面照常铺满，全部按 missing，绝不抛。"""
    return ReadinessResult(
        verdict=VERDICT_UNKNOWN,
        profile_key=profile.key,
        matrix=[_matrix_row(requirement, None) for requirement in profile.requirements],
        missing_materials=[],
        questions=[],
        blocking=[],
        warnings=list(warnings),
    )


def _material_excerpt(material_summary: str, *, materials: list[str] | None) -> tuple[str, bool]:
    """把各段材料拼成一份摘录并截断；返回 (摘录, 是否发生截断)。"""
    parts = [str(material_summary or "").strip()]
    parts.extend(str(part or "").strip() for part in (materials or []))
    joined = "\n\n".join(part for part in parts if part)
    return joined[:MATERIAL_SUMMARY_LIMIT], len(joined) > MATERIAL_SUMMARY_LIMIT


def _build_messages(
    *,
    profile: ElementProfile,
    facts: dict[str, str],
    cause_of_action: str,
    material_excerpt: str,
    truncated: bool,
) -> list[dict[str, str]]:
    """拼 prompt：要件清单来自档案，材料摘录永远标注「可能不完整」。"""
    excerpt = material_excerpt or "（未提供材料）"
    if truncated:
        excerpt = f"{excerpt}\n\n（摘录已截断，未显示的内容一律视为未知）"

    user_parts = [
        "## 案由",
        str(cause_of_action or "").strip() or "（未提供）",
        "",
        "## 要件清单（只能使用这里的 requirement_key）",
        "\n".join(_requirement_line(requirement) for requirement in profile.requirements),
        "",
        "## 已知事实",
        _fact_lines(facts),
        "",
        "## 材料摘录（材料可能不完整）",
        excerpt,
        "",
        "## 输出要求",
        "items 必须逐个覆盖上面每一个 requirement_key；材料里没有的写 status=missing，不要推断。",
    ]
    system = "\n".join([SYSTEM_PROMPT, "", json_schema_instructions(_Assessment)])
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n".join(user_parts)},
    ]


def _requirement_line(requirement: ElementRequirement) -> str:
    evidence = "、".join(requirement.evidence_forms) or "（未列）"
    return f"- {requirement.key}｜{requirement.label}：{requirement.why}（可用证据：{evidence}）"


def _fact_lines(facts: dict[str, str]) -> str:
    rows = [f"- {str(key).strip()}: {str(value).strip()}" for key, value in facts.items() if str(value or "").strip()]
    return "\n".join(rows) or "（没有结构化事实）"


def _brief(exc: Exception) -> str:
    text = " ".join(str(exc).split())
    return text[:_ERROR_DETAIL_CHARS] if text else "（无错误信息）"


__all__ = [
    "LLMCaller",
    "MATERIAL_SUMMARY_LIMIT",
    "MISSING_GATE",
    "VERDICT_BLOCKED",
    "VERDICT_DRAFTABLE_WITH_GAPS",
    "VERDICT_READY",
    "VERDICT_UNKNOWN",
    "ReadinessResult",
    "assess",
]
