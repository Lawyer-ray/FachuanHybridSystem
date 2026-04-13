from __future__ import annotations

from typing import Any

# ── Prompt 模板 ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = "你是资深诉讼律师，正在为当事人撰写法律服务方案。请用专业但易懂的语言，输出 markdown 格式内容，不要输出段落标题（标题由系统添加）。"

_SECTION_PROMPTS: dict[str, str] = {
    "case_analysis": (
        "请对以下案情进行分析，提炼关键事实、时间线、当事人关系及核心争议，200-400字。\n\n案情简述：{case_summary}"
    ),
    "legal_relation": (
        "基于以下案情，认定本案的法律关系类型，指出适用的主要法律条文及司法解释，200-300字。\n\n"
        "案情简述：{case_summary}\n\n"
        "案情分析：{case_analysis}"
    ),
    "dispute_focus": (
        "基于以下案情，列出本案 2-5 个核心争议焦点，每个焦点分析双方可能的立场和主张，300-500字。\n\n"
        "案情简述：{case_summary}\n\n"
        "法律关系：{legal_relation}"
    ),
    "similar_cases": (
        "以下是检索到的类似案例，请逐一分析每个案例与本案的关联性，提炼对本案有参考价值的裁判要旨。"
        "若无类案，说明本案的特殊性。\n\n"
        "案情简述：{case_summary}\n\n"
        "类案检索结果：\n{research_results}"
    ),
    "litigation_strategy": (
        "基于案情分析、法律关系和类案参考，给出具体的诉讼策略建议，包括：\n"
        "1. 建议的诉讼路径（起诉/应诉/调解/仲裁）\n"
        "2. 核心证据准备方向\n"
        "3. 关键法律论点\n"
        "4. 诉讼时机建议\n"
        "300-500字。\n\n"
        "案情简述：{case_summary}\n\n"
        "争议焦点：{dispute_focus}\n\n"
        "类案参考：{similar_cases}"
    ),
    "risk_assessment": (
        "基于以上分析，对本案进行风险评估：\n"
        "1. 胜诉可能性（高/中/低）及理由\n"
        "2. 主要风险点（2-4条）\n"
        "3. 应对措施建议\n"
        "200-400字。\n\n"
        "案情简述：{case_summary}\n\n"
        "诉讼策略：{litigation_strategy}"
    ),
    "cost_estimate": (
        "基于案情，预估本案的主要费用范围（仅供参考）：\n"
        "1. 诉讼费（按标的额计算）\n"
        "2. 律师费参考范围\n"
        "3. 其他可能费用（保全费、鉴定费等）\n"
        "100-200字。\n\n"
        "案情简述：{case_summary}\n\n"
        "风险评估：{risk_assessment}"
    ),
}


def build_section_prompt(
    *,
    section_type: str,
    case_summary: str,
    research_results: str = "",
    existing_sections: dict[str, str] | None = None,
    feedback: str = "",
) -> list[dict[str, str]]:
    """构造单段 LLM prompt。"""
    ctx: dict[str, Any] = {
        "case_summary": case_summary,
        "research_results": research_results or "暂无类案检索结果",
    }
    for key in (
        "case_analysis",
        "legal_relation",
        "dispute_focus",
        "similar_cases",
        "litigation_strategy",
        "risk_assessment",
    ):
        ctx[key] = (existing_sections or {}).get(key, "（待生成）")

    template = _SECTION_PROMPTS.get(section_type, "请根据案情生成{section_type}内容。")
    user_content = template.format(**ctx)

    if feedback:
        user_content += f"\n\n【用户调整意见】：{feedback}\n请根据以上意见重新生成，保持专业性。"

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
