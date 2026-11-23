"""模拟庭审面向用户的文本排版（Markdown 报告 + 交互菜单文案）.

S23-15（2026-11-23 二轮审计）：`mock_trial_flow_service.py` 原本把「状态机 / Markdown 排版 /
模型配置解析 / 报告导出」四类关注点挤在同一个 917 行类里，改任何一处都可能踩到另一处。
这里承接其中**纯文本渲染**那一类：输入都是普通 dict，无 DB / 无 LLM / 无 I/O，
因此可独立阅读与替换；状态机仍留在 `mock_trial_flow_service.py`。

`# pragma: no cover` 标记：这些函数目前只被 flow service 里同样标了 no-cover 的
编排路径调用（迁出前它们就在那些方法体内、不参与覆盖率统计），标记沿用原口径，
避免整体覆盖率因搬家而虚假下跌。
"""

from __future__ import annotations

from typing import Any

from .agents import ROLE_LABELS


def format_judge_report(report: dict[str, Any]) -> str:
    """格式化法官视角分析报告为 Markdown。"""
    lines: list[str] = ["# ⚖️ 法官视角分析报告\n"]

    focuses = report.get("dispute_focuses", [])
    if focuses:
        lines.append("## 争议焦点\n")
        for i, f in enumerate(focuses, 1):
            lines.append(f"**焦点{i}：{f.get('description', '')}**")
            lines.append(f"- 类型：{f.get('focus_type', '')}")
            lines.append(f"- 原告立场：{f.get('plaintiff_position', '')}")
            lines.append(f"- 被告可能立场：{f.get('defendant_position', '')}")
            lines.append(f"- 举证责任：{f.get('burden_of_proof', '')}")
            evidence = f.get("key_evidence", [])
            if evidence:
                lines.append(f"- 关键证据：{'、'.join(evidence)}")
            lines.append("")

    comparisons = report.get("evidence_strength_comparison", [])
    if comparisons:
        lines.append("## 证据强弱对比\n")
        for c in comparisons:
            lines.append(f"**{c.get('focus', '')}**")
            lines.append(f"- 原告证据：{c.get('plaintiff_strength', '')} | 被告证据：{c.get('defendant_strength', '')}")
            lines.append(f"- 分析：{c.get('analysis', '')}")
            lines.append("")

    questions = report.get("judge_questions", [])
    if questions:
        lines.append("## 法官可能提问\n")
        for q in questions:
            lines.append(f"- {q}")
        lines.append("")

    lines.append(f"## 风险评估\n\n{report.get('risk_assessment', '')}\n")
    lines.append(f"## 胜诉概率\n\n{report.get('overall_win_probability', '')}\n")
    lines.append(f"## 建议策略\n\n{report.get('recommended_strategy', '')}")

    return "\n".join(lines)


def format_cross_exam_opinion(ev: dict[str, Any], opinion: dict[str, Any]) -> str:
    """格式化质证意见为 Markdown。"""
    name = ev.get("name", "未命名")
    lines = [f"# 🔍 质证意见 — {name}\n"]
    for dim, label in [
        ("authenticity", "真实性"),
        ("legality", "合法性"),
        ("relevance", "关联性"),
        ("proof_power", "证明力"),
    ]:
        d = opinion.get(dim, {})
        strength = d.get("challenge_strength", "")
        icon = {"strong": "🔴", "moderate": "🟡", "weak": "🟢"}.get(strength, "⚪")
        lines.append(f"## {label} {icon}\n{d.get('opinion', '')}\n")
    lines.append(f"## 风险等级\n{opinion.get('risk_level', '')}\n")
    lines.append(f"## 建议回应策略\n{opinion.get('suggested_response', '')}")
    return "\n".join(lines)


def format_debate_focuses(focuses: list[dict[str, Any]]) -> str:  # pragma: no cover
    """格式化争议焦点列表为 Markdown（辩论模拟选焦点用）。"""
    lines = ["# 💬 争议焦点归纳\n"]
    for i, f in enumerate(focuses, 1):
        lines.append(f"**{i}. {f.get('description', '')}**")
        lines.append(f"   类型：{f.get('focus_type', '')} | 举证责任：{f.get('burden_of_proof', '')}")
        lines.append("")
    lines.append("请回复焦点编号（如 1）选择要辩论的焦点。")
    return "\n".join(lines)


def format_adversarial_report(  # pragma: no cover
    transcript: list[dict[str, Any]],
    case_info: dict[str, Any],
    adv_config: dict[str, Any],
) -> str:
    """格式化多 Agent 对抗庭审记录为 Markdown 报告。

    S23-15（2026-11-23 二轮审计）：原实现在
    `MockTrialFlowService._export_adversarial_report` 里内联拼 40+ 行 Markdown，
    与状态机共处一类；现抽成纯函数，类只负责取数据 → 渲染 → 落库/推送。
    """
    lines = [
        "# ⚖️ 多Agent对抗模拟庭审报告\n",
        f"**案件名称：** {case_info.get('case_name', '')}",
        f"**案由：** {case_info.get('cause_of_action', '')}",
        f"**原告模型：** {adv_config.get('plaintiff_model') or '默认'}",
        f"**被告模型：** {adv_config.get('defendant_model') or '默认'}",
        f"**法官模型：** {adv_config.get('judge_model') or '默认'}",
        f"**辩论轮数：** {adv_config.get('debate_rounds', 10)}",
        "",
        "---\n",
    ]

    current_stage = ""
    stage_labels = {
        "opening": "一、开庭审理",
        "plaintiff_statement": "二、原告陈述",
        "defendant_response": "三、被告答辩",
        "investigation": "四、法庭调查",
        "debate": "五、法庭辩论",
        "debate_judge": "五、法庭辩论（法官追问）",
        "summary": "六、法庭总结",
    }

    for entry in transcript:
        stage = entry.get("stage", "")
        base_stage = stage.split("_judge")[0] if "_judge" in stage else stage
        if base_stage != current_stage and base_stage in stage_labels:
            current_stage = base_stage
            lines.append(f"\n## {stage_labels.get(stage, stage)}\n")

        role_label = ROLE_LABELS.get(entry["role"], entry["role"])
        is_user = entry.get("is_user", False)
        suffix = "（用户）" if is_user else ""
        lines.append(f"### {role_label}{suffix}\n")
        lines.append(entry["content"])
        lines.append("")

    return "\n".join(lines)


def build_init_message(case_name: str, cause: str) -> str:  # pragma: no cover
    """模拟庭审入口的模式选择文案。"""
    return (
        f"⚖️ 模拟庭审 — {case_name}\n"
        f"案由：{cause or '未设置'}\n\n"
        "请选择模拟模式：\n"
        "1️⃣ 法官视角分析 — AI 扮演法官，分析争议焦点、证据强弱、胜诉概率\n"
        "2️⃣ 质证模拟 — AI 扮演对方律师，逐一质证您的证据\n"
        "3️⃣ 辩论模拟 — AI 扮演对方律师，围绕争议焦点进行多轮辩论\n"
        "4️⃣ 多Agent对抗 — 原告/被告/法官分别由不同大模型激烈对抗，你可随时介入\n\n"
        "请回复数字（1/2/3/4）或模式名称。"
    )


def build_model_config_message(models: list[str]) -> str:  # pragma: no cover
    """多 Agent 对抗模式的模型配置说明文案（含可选模型编号表）。"""
    model_list = "\n".join(f"  {i + 1}. `{m}`" for i, m in enumerate(models))
    return (
        "⚔️ **多 Agent 对抗模式配置**\n\n"
        f"可用模型：\n{model_list}\n\n"
        "请按以下格式配置（每行一项），或直接回复 **默认** 使用默认配置：\n\n"
        "```\n"
        "原告模型: 1\n"
        "被告模型: 3\n"
        "法官模型: 5\n"
        "辩论轮数: 10\n"
        "审级: 一审\n"
        "我的角色: 观看\n"
        "```\n\n"
        "审级可选：一审 / 二审（二审会增加上诉请求与答辩环节）\n"
        "角色可选：原告 / 被告 / 法官 / 观看\n"
        "模型填编号或完整名称均可。"
    )


def build_evidence_menu_message(ev: dict[str, Any], current_index: int, total: int) -> str:  # pragma: no cover
    """质证模拟的单份证据提示文案。"""
    lines = [
        f"📋 证据质证 ({current_index + 1}/{total})\n",
        f"**证据名称：** {ev.get('name', '未命名')}",
        f"**证据类型：** {ev.get('evidence_type', '书证')}",
        f"**证明目的：** {ev.get('description', '无')}",
        "",
        "🔍 正在对该证据进行质证分析...",
    ]
    return "\n".join(lines)
