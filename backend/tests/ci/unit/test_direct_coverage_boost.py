"""Direct coverage tests for top uncovered files."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


# ── mock_trial_flow_service.py ──────────────────────────────────────


class TestParseMode:
    def test_judge_by_number(self):
        from apps.litigation_ai.services.mock_trial.mock_trial_flow_service import parse_mode
        assert parse_mode("1") == "judge"

    def test_judge_by_chinese(self):
        from apps.litigation_ai.services.mock_trial.mock_trial_flow_service import parse_mode
        assert parse_mode("法官") == "judge"
        assert parse_mode("法官视角") == "judge"

    def test_cross_exam(self):
        from apps.litigation_ai.services.mock_trial.mock_trial_flow_service import parse_mode
        assert parse_mode("2") == "cross_exam"
        assert parse_mode("质证") == "cross_exam"

    def test_debate(self):
        from apps.litigation_ai.services.mock_trial.mock_trial_flow_service import parse_mode
        assert parse_mode("3") == "debate"
        assert parse_mode("辩论") == "debate"

    def test_adversarial(self):
        from apps.litigation_ai.services.mock_trial.mock_trial_flow_service import parse_mode
        assert parse_mode("4") == "adversarial"
        assert parse_mode("对抗") == "adversarial"

    def test_unknown_returns_none(self):
        from apps.litigation_ai.services.mock_trial.mock_trial_flow_service import parse_mode
        assert parse_mode("unknown") is None
        assert parse_mode("") is None
        assert parse_mode(None) is None


class TestFormatJudgeReport:
    def test_empty_report(self):
        from apps.litigation_ai.services.mock_trial.mock_trial_flow_service import format_judge_report
        result = format_judge_report({})
        assert "法官视角分析报告" in result

    def test_with_dispute_focuses(self):
        from apps.litigation_ai.services.mock_trial.mock_trial_flow_service import format_judge_report
        report = {
            "dispute_focuses": [
                {
                    "description": "合同效力",
                    "focus_type": "法律适用",
                    "plaintiff_position": "合同有效",
                    "defendant_position": "合同无效",
                    "burden_of_proof": "原告",
                    "key_evidence": ["合同原件", "转账记录"],
                }
            ]
        }
        result = format_judge_report(report)
        assert "争议焦点" in result
        assert "合同效力" in result
        assert "合同原件" in result

    def test_with_evidence_comparison(self):
        from apps.litigation_ai.services.mock_trial.mock_trial_flow_service import format_judge_report
        report = {
            "evidence_strength_comparison": [
                {
                    "focus": "因果关系",
                    "plaintiff_strength": "强",
                    "defendant_strength": "弱",
                    "analysis": "原告证据充分",
                }
            ]
        }
        result = format_judge_report(report)
        assert "证据强弱对比" in result
        assert "因果关系" in result

    def test_with_judge_questions(self):
        from apps.litigation_ai.services.mock_trial.mock_trial_flow_service import format_judge_report
        report = {"judge_questions": ["请原告说明损失计算依据", "被告是否有反诉请求"]}
        result = format_judge_report(report)
        assert "法官可能提问" in result
        assert "损失计算依据" in result


# ── sms_matching_stage.py ───────────────────────────────────────────


class TestFilterValidCaseNumbers:
    def test_empty(self):
        from apps.automation.services.sms.stages.sms_matching_stage import filter_valid_case_numbers
        result = filter_valid_case_numbers([])
        assert result == []

    def test_valid_numbers(self):
        from apps.automation.services.sms.stages.sms_matching_stage import filter_valid_case_numbers
        result = filter_valid_case_numbers(["(2024)京01民初123号", "invalid"])
        assert isinstance(result, list)
