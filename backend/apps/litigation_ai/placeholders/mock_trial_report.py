"""模拟庭审报告占位符服务."""

from __future__ import annotations

from typing import Any

from apps.documents.services.placeholders import BasePlaceholderService, PlaceholderRegistry


@PlaceholderRegistry.register
class MockTrialReportPlaceholderService(BasePlaceholderService):
    """模拟庭审报告占位符服务."""

    name = "mock_trial_report"
    display_name = "模拟庭审报告占位符"
    description = "生成模拟庭审报告的占位符数据"
    category = "litigation"
    placeholder_keys = [
        "模拟庭审_案件名称",
        "模拟庭审_案由",
        "模拟庭审_模式",
        "模拟庭审_争议焦点",
        "模拟庭审_证据分析",
        "模拟庭审_风险评估",
        "模拟庭审_胜诉概率",
        "模拟庭审_建议策略",
        "模拟庭审_生成时间",
    ]
    placeholder_metadata = {
        "模拟庭审_案件名称": {
            "display_name": "案件名称",
            "description": "模拟庭审关联的案件名称",
            "example_value": "张三诉李四民间借贷纠纷案",
        },
        "模拟庭审_案由": {
            "display_name": "案由",
            "description": "案件的案由",
            "example_value": "民间借贷纠纷",
        },
        "模拟庭审_模式": {
            "display_name": "模拟模式",
            "description": "模拟庭审的模式（法官视角/质证模拟/辩论模拟）",
            "example_value": "法官视角分析",
        },
        "模拟庭审_争议焦点": {
            "display_name": "争议焦点",
            "description": "法官视角分析中的争议焦点列表",
            "example_value": "1. 借贷关系是否成立\n2. 借款金额如何认定",
        },
        "模拟庭审_证据分析": {
            "display_name": "证据分析",
            "description": "证据强弱对比分析",
            "example_value": "原告证据较强，被告证据存在瑕疵...",
        },
        "模拟庭审_风险评估": {
            "display_name": "风险评估",
            "description": "案件风险评估",
            "example_value": "中等风险，主要争议在于借款交付事实的认定",
        },
        "模拟庭审_胜诉概率": {
            "display_name": "胜诉概率",
            "description": "胜诉概率评估",
            "example_value": "原告胜诉概率约70%",
        },
        "模拟庭审_建议策略": {
            "display_name": "建议策略",
            "description": "庭审策略建议",
            "example_value": "重点准备借款交付的证据，应对被告的抗辩...",
        },
        "模拟庭审_生成时间": {
            "display_name": "生成时间",
            "description": "报告生成时间",
            "example_value": "2026年3月15日",
        },
    }

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        生成模拟庭审报告占位符值.

        Args:
            context_data: 包含 session_id, report_data 等

        Returns:
            占位符键值对字典
        """
        report_data = context_data.get("report_data", {})
        case_info = context_data.get("case_info", {})

        mode_map = {
            "judge": "法官视角分析",
            "cross_exam": "质证模拟",
            "debate": "辩论模拟",
        }
        mode = report_data.get("mode", "")
        mode_display = mode_map.get(mode, mode)

        # 格式化争议焦点
        focuses = report_data.get("report", {}).get("dispute_focuses", [])
        focuses_text = self._format_focuses(focuses)

        # 格式化证据分析
        comparisons = report_data.get("report", {}).get("evidence_strength_comparison", [])
        evidence_text = self._format_evidence_analysis(comparisons)

        # 格式化生成时间
        from datetime import datetime

        generate_time = datetime.now().strftime("%Y年%m月%d日")

        return {
            "模拟庭审_案件名称": case_info.get("case_name", ""),
            "模拟庭审_案由": case_info.get("cause_of_action", ""),
            "模拟庭审_模式": mode_display,
            "模拟庭审_争议焦点": focuses_text,
            "模拟庭审_证据分析": evidence_text,
            "模拟庭审_风险评估": report_data.get("report", {}).get("risk_assessment", ""),
            "模拟庭审_胜诉概率": report_data.get("report", {}).get("overall_win_probability", ""),
            "模拟庭审_建议策略": report_data.get("report", {}).get("recommended_strategy", ""),
            "模拟庭审_生成时间": generate_time,
        }

    def _format_focuses(self, focuses: list[dict[str, Any]]) -> str:
        """格式化争议焦点列表."""
        if not focuses:
            return "无"

        lines = []
        for i, f in enumerate(focuses, 1):
            desc = f.get("description", "")
            p_pos = f.get("plaintiff_position", "")
            d_pos = f.get("defendant_position", "")
            burden = f.get("burden_of_proof", "")

            lines.append(f"{i}. {desc}")
            if p_pos:
                lines.append(f"   原告立场：{p_pos}")
            if d_pos:
                lines.append(f"   被告立场：{d_pos}")
            if burden:
                lines.append(f"   举证责任：{burden}")
            lines.append("")

        return "\n".join(lines).strip()

    def _format_evidence_analysis(self, comparisons: list[dict[str, Any]]) -> str:
        """格式化证据分析."""
        if not comparisons:
            return "无"

        lines = []
        for c in comparisons:
            focus = c.get("focus", "")
            p_strength = c.get("plaintiff_strength", "")
            d_strength = c.get("defendant_strength", "")
            analysis = c.get("analysis", "")

            lines.append(f"【{focus}】")
            lines.append(f"原告证据强度：{p_strength}")
            lines.append(f"被告证据强度：{d_strength}")
            lines.append(f"分析：{analysis}")
            lines.append("")

        return "\n".join(lines).strip()
