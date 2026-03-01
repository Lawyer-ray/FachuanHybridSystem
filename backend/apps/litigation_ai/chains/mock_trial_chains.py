"""模拟庭审 LLM Chain."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from .mock_trial_schemas import CrossExamOpinion, JudgePerspectiveReport

logger = logging.getLogger("apps.litigation_ai")

# 案由特定知识（初期硬编码常见案由）
CAUSE_SPECIFIC_KNOWLEDGE: dict[str, str] = {
    "民间借贷": (
        "民间借贷案件法官重点关注：\n"
        "1. 借贷合意的证据（借条、合同、聊天记录）\n"
        "2. 款项实际交付的证据（转账记录、收据），大额现金交付需重点审查\n"
        "3. 利率是否超过合同成立时一年期LPR的四倍\n"
        "4. 是否存在砍头息（预先扣除利息）\n"
        "5. 借款人已还款金额的认定\n"
        "6. 是否存在职业放贷人情形\n"
        "7. 夫妻共同债务的认定（是否用于家庭共同生活）"
    ),
    "买卖合同": (
        "买卖合同案件法官重点关注：\n"
        "1. 合同是否成立及生效\n"
        "2. 标的物是否交付及交付时间\n"
        "3. 标的物质量是否符合约定\n"
        "4. 价款支付情况\n"
        "5. 违约责任的约定及计算\n"
        "6. 检验期间和质量异议期间\n"
        "7. 所有权保留条款的效力"
    ),
    "劳动争议": (
        "劳动争议案件法官重点关注：\n"
        "1. 劳动关系是否成立（是否存在事实劳动关系）\n"
        "2. 劳动合同的签订和履行情况\n"
        "3. 工资标准和加班费计算\n"
        "4. 解除劳动合同的合法性（程序和实体）\n"
        "5. 经济补偿金/赔偿金的计算基数和年限\n"
        "6. 社会保险和公积金缴纳情况\n"
        "7. 竞业限制和服务期约定"
    ),
}


def _get_cause_knowledge(cause_of_action: str) -> str:
    """根据案由匹配特定知识."""
    for key, knowledge in CAUSE_SPECIFIC_KNOWLEDGE.items():
        if key in (cause_of_action or ""):
            return knowledge
    return ""


def _clean_llm_output(text: str) -> str:
    """清理 LLM 输出中的 markdown 标记."""
    if not text:
        return ""
    for marker in ["```json", "```", "<|begin_of_text|>", "<|end_of_text|>", "<|begin_of_box|>", "<|end_of_box|>"]:
        text = text.replace(marker, "")
    return text.strip()


@dataclass
class JudgePerspectiveResult:
    report: dict[str, Any]
    model: str
    token_usage: dict[str, int]


class JudgePerspectiveChain:
    """法官视角分析 Chain."""

    def __init__(self, model: str | None = None) -> None:
        self._model = model

    def _build_messages(
        self, case_info: dict[str, Any], evidence_text: str
    ) -> list[SystemMessage | HumanMessage]:
        cause = case_info.get("cause_of_action", "")
        cause_knowledge = _get_cause_knowledge(cause)
        cause_section = f"\n\n## 本案由特定关注点\n\n{cause_knowledge}" if cause_knowledge else ""

        schema_text = json.dumps(JudgePerspectiveReport.model_json_schema(), ensure_ascii=False)

        system = (
            "你是一位资深法官，具有20年以上民商事审判经验。\n"
            "你正在对一个案件进行庭前分析，需要从法官视角给出专业、中立、客观的分析报告。\n\n"
            "你的分析应当包括：\n"
            "1. 归纳本案的争议焦点（区分事实争议和法律适用争议）\n"
            "2. 合理分配举证责任\n"
            "3. 对比双方证据的强弱\n"
            "4. 评估整体风险\n"
            "5. 列出你在庭审中可能向双方提出的问题\n"
            "6. 给出胜诉概率评估和庭审策略建议\n\n"
            "你必须只输出一个 JSON 对象，不要输出 Markdown，不要输出多余文字。\n"
            f"该 JSON 必须严格符合以下 JSON Schema：{schema_text}"
            f"{cause_section}"
        )

        parties_text = ""
        for p in case_info.get("parties", []):
            side = "我方" if p.get("is_our_side") else "对方"
            parties_text += f"- {p.get('name', '')}（{p.get('legal_status', '')}，{side}）\n"

        user = "\n".join([
            "# 案件信息",
            f"案件名称：{case_info.get('case_name', '')}",
            f"案由：{cause}",
            f"标的额：{case_info.get('target_amount') or '未知'}",
            f"案件阶段：{case_info.get('case_stage', '')}",
            "",
            "# 当事人",
            parties_text or "无",
            "",
            "# 证据概要",
            evidence_text or "无证据信息",
        ])

        return [SystemMessage(content=system), HumanMessage(content=user)]

    async def arun(
        self,
        *,
        case_info: dict[str, Any],
        evidence_text: str,
    ) -> JudgePerspectiveResult:
        from asgiref.sync import sync_to_async

        from apps.litigation_ai.services.wiring import get_llm_service

        llm_service = await sync_to_async(get_llm_service, thread_sensitive=True)()
        llm = await sync_to_async(llm_service.get_langchain_llm, thread_sensitive=True)(model=self._model)
        model_name = self._model or getattr(llm, "model", "") or getattr(llm, "model_name", "") or ""

        messages = self._build_messages(case_info, evidence_text)
        response = await llm.ainvoke(messages)
        content = _clean_llm_output(getattr(response, "content", "") or "")

        meta = getattr(response, "response_metadata", {}) or {}
        tu = meta.get("token_usage", {}) if isinstance(meta, dict) else {}
        token_usage = {
            "prompt_tokens": tu.get("prompt_tokens", 0),
            "completion_tokens": tu.get("completion_tokens", 0),
            "total_tokens": tu.get("total_tokens", 0),
        }

        parsed = json.loads(content) if content else {}
        report = JudgePerspectiveReport.model_validate(parsed)

        return JudgePerspectiveResult(
            report=report.model_dump(),
            model=model_name,
            token_usage=token_usage,
        )


@dataclass
class CrossExamResult:
    opinion: dict[str, Any]
    model: str
    token_usage: dict[str, int]


class CrossExamChain:
    """质证模拟 Chain：扮演对方律师，对单份证据进行三性质证."""

    def __init__(self, model: str | None = None) -> None:
        self._model = model

    async def arun(
        self, *, case_info: dict[str, Any], evidence_info: dict[str, Any]
    ) -> CrossExamResult:
        from asgiref.sync import sync_to_async
        from apps.litigation_ai.services.wiring import get_llm_service

        cause = case_info.get("cause_of_action", "")
        cause_knowledge = _get_cause_knowledge(cause)
        cause_section = f"\n\n## 本案由背景知识\n{cause_knowledge}" if cause_knowledge else ""

        schema_text = json.dumps(CrossExamOpinion.model_json_schema(), ensure_ascii=False)

        system = (
            "你是一位经验丰富的诉讼律师，代表对方当事人。\n"
            "你的目标是从证据的真实性、合法性、关联性、证明力四个维度，对对方提交的证据进行质证。\n"
            "质证应当专业、有理有据，指出证据的薄弱环节。\n"
            "同时给出 suggested_response（建议对方如何回应你的质证）和 risk_level（high/medium/low）。\n"
            "challenge_strength 取值：strong（质疑有力）、moderate（有一定道理）、weak（形式质疑）。\n\n"
            "你必须只输出一个 JSON 对象，不要输出 Markdown。\n"
            f"JSON 必须严格符合以下 Schema：{schema_text}"
            f"{cause_section}"
        )

        user = "\n".join([
            "# 案件背景",
            f"案件名称：{case_info.get('case_name', '')}",
            f"案由：{cause}",
            "",
            "# 待质证的证据",
            f"证据名称：{evidence_info.get('name', '')}",
            f"证据描述/证明目的：{evidence_info.get('description', '')}",
            f"证据类型：{evidence_info.get('evidence_type', '书证')}",
        ])

        llm_service = await sync_to_async(get_llm_service, thread_sensitive=True)()
        llm = await sync_to_async(llm_service.get_langchain_llm, thread_sensitive=True)(model=self._model)
        model_name = self._model or getattr(llm, "model", "") or ""

        response = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
        content = _clean_llm_output(getattr(response, "content", "") or "")

        meta = getattr(response, "response_metadata", {}) or {}
        tu = meta.get("token_usage", {}) if isinstance(meta, dict) else {}

        parsed = json.loads(content) if content else {}
        opinion = CrossExamOpinion.model_validate(parsed)

        return CrossExamResult(
            opinion=opinion.model_dump(),
            model=model_name,
            token_usage={"prompt_tokens": tu.get("prompt_tokens", 0), "completion_tokens": tu.get("completion_tokens", 0), "total_tokens": tu.get("total_tokens", 0)},
        )


@dataclass
class DisputeFocusResult:
    focuses: list[dict[str, Any]]
    model: str


class DisputeFocusChain:
    """争议焦点归纳 Chain."""

    def __init__(self, model: str | None = None) -> None:
        self._model = model

    async def arun(self, *, case_info: dict[str, Any], evidence_text: str) -> DisputeFocusResult:
        from asgiref.sync import sync_to_async
        from apps.litigation_ai.services.wiring import get_llm_service
        from .mock_trial_schemas import DisputeFocus

        schema_text = json.dumps(DisputeFocus.model_json_schema(), ensure_ascii=False)

        system = (
            "你是一位资深法官，请根据案件信息归纳本案的争议焦点。\n"
            "每个焦点应包含：描述、类型（事实争议/法律适用争议/程序争议）、原告立场、被告可能立场、关键证据、举证责任方。\n"
            "输出 3-6 个焦点，按重要性排序。\n\n"
            "你必须只输出一个 JSON 数组，每个元素符合以下 Schema：\n"
            f"{schema_text}"
        )

        user = "\n".join([
            f"案件名称：{case_info.get('case_name', '')}",
            f"案由：{case_info.get('cause_of_action', '')}",
            f"标的额：{case_info.get('target_amount') or '未知'}",
            "", "# 证据概要", evidence_text or "无",
        ])

        llm_service = await sync_to_async(get_llm_service, thread_sensitive=True)()
        llm = await sync_to_async(llm_service.get_langchain_llm, thread_sensitive=True)(model=self._model)
        model_name = self._model or getattr(llm, "model", "") or ""

        response = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
        content = _clean_llm_output(getattr(response, "content", "") or "")
        parsed = json.loads(content) if content else []
        if isinstance(parsed, dict):
            parsed = parsed.get("dispute_focuses", parsed.get("focuses", [parsed]))
        focuses = [DisputeFocus.model_validate(f).model_dump() for f in parsed]

        return DisputeFocusResult(focuses=focuses, model=model_name)


@dataclass
class DebateResult:
    rebuttal: str
    model: str


class DebateChain:
    """辩论模拟 Chain：扮演对方律师进行反驳."""

    def __init__(self, model: str | None = None, difficulty: str = "medium") -> None:
        self._model = model
        self._difficulty = difficulty

    async def arun(
        self, *, case_info: dict[str, Any], focus: dict[str, Any], user_argument: str, history: list[dict[str, str]]
    ) -> DebateResult:
        from asgiref.sync import sync_to_async
        from apps.litigation_ai.services.wiring import get_llm_service

        difficulty_prompt = {
            "easy": "你的反驳应当温和，只提出基本抗辩观点。",
            "medium": "你的反驳应当有理有据，引用相关法律条文。",
            "hard": "你的反驳应当犀利精准，善于发现对方论证的逻辑漏洞并精准攻击。",
        }.get(self._difficulty, "")

        system = (
            "你是一位经验丰富的诉讼律师，代表对方当事人，正在围绕一个争议焦点与对方律师辩论。\n"
            f"{difficulty_prompt}\n"
            "回复应当简洁有力，200-400字，直接反驳对方观点。不要输出 JSON，直接输出反驳文本。"
        )

        history_text = "\n".join([f"{'我方' if h['role'] == 'opponent' else '对方'}：{h['content']}" for h in history[-6:]])

        user = "\n".join([
            f"案由：{case_info.get('cause_of_action', '')}",
            f"争议焦点：{focus.get('description', '')}",
            f"我方立场：{focus.get('defendant_position', '')}",
            "", "# 辩论历史", history_text or "（首轮辩论）",
            "", "# 对方律师刚才的论点", user_argument,
            "", "请针对以上论点进行反驳：",
        ])

        llm_service = await sync_to_async(get_llm_service, thread_sensitive=True)()
        llm = await sync_to_async(llm_service.get_langchain_llm, thread_sensitive=True)(model=self._model)
        model_name = self._model or getattr(llm, "model", "") or ""

        response = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
        content = (getattr(response, "content", "") or "").strip()

        return DebateResult(rebuttal=content, model=model_name)
