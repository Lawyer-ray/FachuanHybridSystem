"""Tests for litigation_ai chains: user_choice_parse, document_type_parse, goal_schemas, mock_trial agents."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ── goal_schemas ───────────────────────────────────────────────────────────


class TestGoalSchemas:
    def test_user_choice_result(self) -> None:
        from apps.litigation_ai.chains.goal_schemas import UserChoiceResult

        result = UserChoiceResult(
            primary_document_type="complaint",
            pending_document_types=["defense"],
            notes="test",
        )
        assert result.primary_document_type == "complaint"
        assert len(result.pending_document_types) == 1


# ── UserChoiceParseChain ───────────────────────────────────────────────────


class TestUserChoiceParseChain:
    def _make_chain(self):
        from apps.litigation_ai.chains.user_choice_parse_chain import UserChoiceParseChain

        return UserChoiceParseChain()

    def test_fallback_parse_all(self) -> None:
        chain = self._make_chain()
        result = chain._fallback_parse(
            user_input="都要",
            primary_document_type="complaint",
            optional_document_types=["defense", "counterclaim"],
            notes="test",
        )
        assert "defense" in result.pending_document_types
        assert "counterclaim" in result.pending_document_types

    def test_fallback_parse_none(self) -> None:
        chain = self._make_chain()
        result = chain._fallback_parse(
            user_input="不要",
            primary_document_type="complaint",
            optional_document_types=["defense"],
            notes="test",
        )
        assert result.pending_document_types == []

    def test_fallback_parse_select_type(self) -> None:
        chain = self._make_chain()
        result = chain._fallback_parse(
            user_input="先生成答辩状",
            primary_document_type="complaint",
            optional_document_types=["defense"],
            notes="test",
        )
        assert result.primary_document_type == "defense"

    def test_fallback_parse_counterclaim_defense(self) -> None:
        chain = self._make_chain()
        result = chain._fallback_parse(
            user_input="反诉答辩状",
            primary_document_type="complaint",
            optional_document_types=["counterclaim_defense"],
            notes="test",
        )
        assert result.primary_document_type == "counterclaim_defense"

    def test_fallback_parse_no_match(self) -> None:
        chain = self._make_chain()
        result = chain._fallback_parse(
            user_input="随便",
            primary_document_type="complaint",
            optional_document_types=["defense"],
            notes="test",
        )
        assert result.primary_document_type == "complaint"
        assert "heuristic" in result.notes

    def test_fallback_parse_type_maps(self) -> None:
        chain = self._make_chain()
        test_cases = [
            ("起诉状", "complaint"),
            ("答辩状", "defense"),
            ("反诉状", "counterclaim"),
            ("反诉答辩状", "counterclaim_defense"),
        ]
        for text, expected in test_cases:
            result = chain._fallback_parse(
                user_input=text,
                primary_document_type="",
                optional_document_types=[],
                notes="test",
            )
            assert result.primary_document_type == expected, f"Failed for {text}"

    def test_default_prompt(self) -> None:
        chain = self._make_chain()
        prompt = chain._default_prompt()
        assert "文书" in prompt or "法律" in prompt


# ── DocumentTypeParseChain ─────────────────────────────────────────────────


class TestDocumentTypeParseChain:
    def _make_chain(self):
        from apps.litigation_ai.chains.document_type_parse_chain import DocumentTypeParseChain

        return DocumentTypeParseChain()

    def test_fallback_parse_empty(self) -> None:
        chain = self._make_chain()
        result = chain._fallback_parse(user_input="", allowed_types=["complaint"], notes="test")
        assert result.document_type == ""
        assert result.confidence == 0.0

    def test_fallback_parse_chinese_keyword(self) -> None:
        chain = self._make_chain()
        result = chain._fallback_parse(
            user_input="起诉状",
            allowed_types=["complaint", "defense"],
            notes="test",
        )
        assert result.document_type == "complaint"
        assert result.confidence == 0.9

    def test_fallback_parse_english_code(self) -> None:
        chain = self._make_chain()
        result = chain._fallback_parse(
            user_input="complaint",
            allowed_types=["complaint", "defense"],
            notes="test",
        )
        assert result.document_type == "complaint"
        assert result.confidence == 0.95

    def test_fallback_parse_index(self) -> None:
        chain = self._make_chain()
        result = chain._fallback_parse(
            user_input="2",
            allowed_types=["complaint", "defense", "counterclaim"],
            notes="test",
        )
        assert result.document_type == "defense"
        assert result.confidence == 0.75

    def test_fallback_parse_unmatched(self) -> None:
        chain = self._make_chain()
        result = chain._fallback_parse(
            user_input="随便",
            allowed_types=["complaint"],
            notes="test",
        )
        assert result.document_type == ""
        assert result.confidence == 0.0

    def test_fallback_parse_all_chinese_types(self) -> None:
        chain = self._make_chain()
        test_cases = [
            ("起诉状", "complaint"),
            ("起诉书", "complaint"),
            ("起诉", "complaint"),
            ("答辩状", "defense"),
            ("答辩", "defense"),
            ("反诉状", "counterclaim"),
            ("反诉起诉状", "counterclaim"),
            ("反诉答辩状", "counterclaim_defense"),
            ("反诉答辩", "counterclaim_defense"),
        ]
        for text, expected in test_cases:
            result = chain._fallback_parse(user_input=text, allowed_types=[], notes="test")
            assert result.document_type == expected, f"Failed for '{text}'"

    def test_fallback_parse_not_in_allowed(self) -> None:
        chain = self._make_chain()
        result = chain._fallback_parse(
            user_input="起诉状",
            allowed_types=["defense", "counterclaim"],
            notes="test",
        )
        # "complaint" is not in allowed_types
        assert result.document_type == ""

    def test_fallback_parse_index_out_of_range(self) -> None:
        chain = self._make_chain()
        result = chain._fallback_parse(
            user_input="10",
            allowed_types=["complaint"],
            notes="test",
        )
        assert result.document_type == ""

    def test_default_prompt(self) -> None:
        chain = self._make_chain()
        prompt = chain._default_prompt()
        assert "文书类型" in prompt

    def test_document_type_parse_result_model(self) -> None:
        from apps.litigation_ai.chains.document_type_parse_chain import DocumentTypeParseResult

        result = DocumentTypeParseResult()
        assert result.document_type == ""
        assert result.confidence == 0.0
        assert result.notes == ""


# ── mock_trial agents ──────────────────────────────────────────────────────


class TestMockTrialAgents:
    def test_role_constants(self) -> None:
        from apps.litigation_ai.services.mock_trial.agents import (
            CLERK,
            DEFENDANT,
            JUDGE,
            PLAINTIFF,
            ROLE_LABELS,
        )

        assert PLAINTIFF == "plaintiff"
        assert DEFENDANT == "defendant"
        assert JUDGE == "judge"
        assert CLERK == "clerk"
        assert len(ROLE_LABELS) == 4

    def test_agent_dataclass(self) -> None:
        from apps.litigation_ai.services.mock_trial.agents import Agent

        agent = Agent(role="plaintiff", model="test", system_prompt="You are plaintiff")
        assert agent.role == "plaintiff"
        assert agent.model == "test"

    def test_judge_templates_have_placeholders(self) -> None:
        from apps.litigation_ai.services.mock_trial.agents import JUDGE_OPEN_FIRST, JUDGE_OPEN_SECOND

        assert "{court_name}" in JUDGE_OPEN_FIRST
        assert "{appellant_name}" in JUDGE_OPEN_SECOND

    def test_system_prompts_not_empty(self) -> None:
        from apps.litigation_ai.services.mock_trial.agents import (
            DEFENDANT_SYSTEM,
            JUDGE_SYSTEM,
            JUDGE_SUMMARY_SYSTEM,
            PLAINTIFF_SYSTEM,
        )

        assert len(PLAINTIFF_SYSTEM) > 100
        assert len(DEFENDANT_SYSTEM) > 100
        assert len(JUDGE_SYSTEM) > 100
        assert len(JUDGE_SUMMARY_SYSTEM) > 100

    def test_court_rituals_not_empty(self) -> None:
        from apps.litigation_ai.services.mock_trial.agents import (
            CLERK_ANNOUNCE,
            JUDGE_CLOSING,
            JUDGE_CROSS_EXAM,
            JUDGE_DEBATE_START,
            JUDGE_FINAL_STATEMENT,
            JUDGE_IDENTITY_CHECK,
            JUDGE_INVESTIGATION_START_FIRST,
            JUDGE_INVESTIGATION_START_SECOND,
            JUDGE_MEDIATION,
            JUDGE_RIGHTS_NOTICE,
        )

        for text in [
            CLERK_ANNOUNCE,
            JUDGE_IDENTITY_CHECK,
            JUDGE_RIGHTS_NOTICE,
            JUDGE_INVESTIGATION_START_FIRST,
            JUDGE_INVESTIGATION_START_SECOND,
            JUDGE_CROSS_EXAM,
            JUDGE_DEBATE_START,
            JUDGE_FINAL_STATEMENT,
            JUDGE_MEDIATION,
            JUDGE_CLOSING,
        ]:
            assert len(text) > 20


# ── DocumentTypeParseResult model ──────────────────────────────────────────


class TestSchemas:
    def test_agent_response_model_dump(self) -> None:
        from apps.litigation_ai.agent.schemas import AgentResponse

        resp = AgentResponse(type="test", content="hello", metadata={"k": "v"})
        dumped = resp.model_dump()
        assert dumped["type"] == "test"
        assert dumped["metadata"] == {"k": "v"}

    def test_draft_output_model_dump(self) -> None:
        from apps.litigation_ai.agent.schemas import DraftOutput

        draft = DraftOutput(document_type="complaint", litigation_request="test request")
        dumped = draft.model_dump()
        assert dumped["document_type"] == "complaint"
        assert dumped["litigation_request"] == "test request"
        assert dumped["defense_opinion"] is None

    def test_tool_call_record_model_dump(self) -> None:
        from apps.litigation_ai.agent.schemas import ToolCallRecord

        record = ToolCallRecord(tool_name="test", arguments={"x": 1}, result="ok", duration_ms=150.5)
        dumped = record.model_dump()
        assert dumped["tool_name"] == "test"
        assert dumped["duration_ms"] == 150.5


# ── schemas chain ──────────────────────────────────────────────────────────


class TestChainSchemas:
    def test_litigation_schemas_import(self) -> None:
        from apps.litigation_ai.chains.schemas import ComplaintDraft

        assert ComplaintDraft is not None

    def test_mock_trial_schemas_import(self) -> None:
        from apps.litigation_ai.chains.mock_trial_schemas import JudgePerspectiveReport

        assert JudgePerspectiveReport is not None

    def test_goal_schemas_import(self) -> None:
        from apps.litigation_ai.chains.goal_schemas import UserChoiceResult

        assert UserChoiceResult is not None
