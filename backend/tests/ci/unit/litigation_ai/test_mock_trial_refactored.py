"""Tests for mock_trial_flow_service module-level pure functions."""

from __future__ import annotations

from apps.litigation_ai.models.choices import MockTrialMode
from apps.litigation_ai.services.mock_trial.mock_trial_flow_service import (
    format_cross_exam_opinion,
    format_judge_report,
    parse_mode,
)


class TestParseMode:
    def test_digit_1(self) -> None:
        assert parse_mode("1") == MockTrialMode.JUDGE

    def test_digit_2(self) -> None:
        assert parse_mode("2") == MockTrialMode.CROSS_EXAM

    def test_digit_3(self) -> None:
        assert parse_mode("3") == MockTrialMode.DEBATE

    def test_digit_4(self) -> None:
        assert parse_mode("4") == MockTrialMode.ADVERSARIAL

    def test_chinese_judge(self) -> None:
        assert parse_mode("法官") == MockTrialMode.JUDGE
        assert parse_mode("法官视角") == MockTrialMode.JUDGE

    def test_chinese_cross_exam(self) -> None:
        assert parse_mode("质证") == MockTrialMode.CROSS_EXAM
        assert parse_mode("质证模拟") == MockTrialMode.CROSS_EXAM

    def test_chinese_debate(self) -> None:
        assert parse_mode("辩论") == MockTrialMode.DEBATE
        assert parse_mode("辩论模拟") == MockTrialMode.DEBATE

    def test_chinese_adversarial(self) -> None:
        assert parse_mode("对抗") == MockTrialMode.ADVERSARIAL
        assert parse_mode("多agent对抗") == MockTrialMode.ADVERSARIAL
        assert parse_mode("多agent") == MockTrialMode.ADVERSARIAL

    def test_unknown(self) -> None:
        assert parse_mode("未知模式") is None

    def test_empty(self) -> None:
        assert parse_mode("") is None

    def test_none(self) -> None:
        assert parse_mode(None) is None  # type: ignore[arg-type]


class TestFormatJudgeReport:
    def test_with_focuses(self) -> None:
        report = {
            "dispute_focuses": [
                {
                    "description": "合同效力",
                    "focus_type": "法律适用",
                    "plaintiff_position": "有效",
                    "defendant_position": "无效",
                    "burden_of_proof": "原告",
                    "key_evidence": ["合同文本"],
                }
            ],
            "risk_assessment": "中等风险",
            "overall_win_probability": "60%",
            "recommended_strategy": "重点论证合同有效",
        }
        result = format_judge_report(report)
        assert "合同效力" in result
        assert "中等风险" in result
        assert "60%" in result

    def test_with_comparisons(self) -> None:
        report = {
            "evidence_strength_comparison": [
                {
                    "focus": "合同签订",
                    "plaintiff_strength": "强",
                    "defendant_strength": "弱",
                    "analysis": "原告证据充分",
                }
            ],
        }
        result = format_judge_report(report)
        assert "合同签订" in result
        assert "强" in result

    def test_with_questions(self) -> None:
        report = {"judge_questions": ["合同签订时间？", "付款金额？"]}
        result = format_judge_report(report)
        assert "合同签订时间？" in result

    def test_empty_report(self) -> None:
        result = format_judge_report({})
        assert "法官视角分析报告" in result

    def test_contains_markdown_headers(self) -> None:
        report = {
            "risk_assessment": "低",
            "overall_win_probability": "80%",
            "recommended_strategy": "继续诉讼",
        }
        result = format_judge_report(report)
        assert "# " in result


class TestFormatCrossExamOpinion:
    def test_basic(self) -> None:
        ev = {"name": "合同原件"}
        opinion = {
            "authenticity": {"challenge_strength": "strong", "opinion": "真实性存疑"},
            "legality": {"challenge_strength": "weak", "opinion": "合法"},
            "relevance": {"challenge_strength": "moderate", "opinion": "部分关联"},
            "proof_power": {"challenge_strength": "weak", "opinion": "证明力强"},
            "risk_level": "medium",
            "suggested_response": "补充公证",
        }
        result = format_cross_exam_opinion(ev, opinion)
        assert "合同原件" in result
        assert "真实性存疑" in result
        assert "medium" in result

    def test_strength_icons(self) -> None:
        ev = {"name": "test"}
        opinion = {
            "authenticity": {"challenge_strength": "strong", "opinion": "x"},
            "legality": {"challenge_strength": "moderate", "opinion": "x"},
            "relevance": {"challenge_strength": "weak", "opinion": "x"},
            "proof_power": {"challenge_strength": "unknown", "opinion": "x"},
            "risk_level": "low",
            "suggested_response": "none",
        }
        result = format_cross_exam_opinion(ev, opinion)
        # strong -> red, moderate -> yellow, weak -> green, unknown -> white
        assert "🔴" in result
        assert "🟡" in result
        assert "🟢" in result
        assert "⚪" in result

    def test_empty_opinion(self) -> None:
        result = format_cross_exam_opinion({"name": "test"}, {})
        assert "test" in result
