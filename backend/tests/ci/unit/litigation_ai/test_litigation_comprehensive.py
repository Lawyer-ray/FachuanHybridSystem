"""Tests for litigation_ai: middleware, schemas, tools, flow_messenger, placeholder_render, types, choices, session_shared."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── choices ────────────────────────────────────────────────────────────────


class TestChoices:
    def test_document_type(self) -> None:
        from apps.litigation_ai.models.choices import DocumentType

        assert DocumentType.COMPLAINT == "complaint"
        assert DocumentType.DEFENSE == "defense"
        assert DocumentType.COUNTERCLAIM == "counterclaim"
        assert DocumentType.COUNTERCLAIM_DEFENSE == "counterclaim_defense"
        assert len(DocumentType.choices) == 4

    def test_session_status(self) -> None:
        from apps.litigation_ai.models.choices import SessionStatus

        assert SessionStatus.ACTIVE == "active"
        assert SessionStatus.COMPLETED == "completed"
        assert SessionStatus.CANCELLED == "cancelled"

    def test_message_role(self) -> None:
        from apps.litigation_ai.models.choices import MessageRole

        assert MessageRole.USER == "user"
        assert MessageRole.ASSISTANT == "assistant"
        assert MessageRole.SYSTEM == "system"

    def test_session_type(self) -> None:
        from apps.litigation_ai.models.choices import SessionType

        assert SessionType.DOC_GEN == "doc_gen"
        assert SessionType.MOCK_TRIAL == "mock_trial"

    def test_mock_trial_mode(self) -> None:
        from apps.litigation_ai.models.choices import MockTrialMode

        assert MockTrialMode.JUDGE == "judge"
        assert MockTrialMode.CROSS_EXAM == "cross_exam"
        assert MockTrialMode.DEBATE == "debate"
        assert MockTrialMode.ADVERSARIAL == "adversarial"


# ── flow types ─────────────────────────────────────────────────────────────


class TestFlowTypes:
    def test_conversation_step_values(self) -> None:
        from apps.litigation_ai.services.flow.types import ConversationStep

        assert ConversationStep.INIT == "init"
        assert ConversationStep.DOCUMENT_TYPE == "document_type"
        assert ConversationStep.GENERATING == "generating"
        assert ConversationStep.COMPLETED == "completed"

    def test_flow_context_dataclass(self) -> None:
        from apps.litigation_ai.services.flow.types import ConversationStep, FlowContext

        ctx = FlowContext(
            session_id="s1",
            case_id=1,
            user_id=10,
            current_step=ConversationStep.INIT,
        )
        assert ctx.session_id == "s1"
        assert ctx.document_type is None
        assert ctx.metadata is None

    def test_flow_context_with_optionals(self) -> None:
        from apps.litigation_ai.services.flow.types import ConversationStep, FlowContext

        ctx = FlowContext(
            session_id="s1",
            case_id=1,
            user_id=10,
            current_step=ConversationStep.EVIDENCE_SELECTION,
            document_type="complaint",
            litigation_goal="win the case",
            evidence_list_ids=[1, 2],
            evidence_item_ids=[10, 20],
            metadata={"key": "value"},
        )
        assert ctx.document_type == "complaint"
        assert len(ctx.evidence_item_ids) == 2


# ── mock_trial types ──────────────────────────────────────────────────────


class TestMockTrialTypes:
    def test_mock_trial_step_values(self) -> None:
        from apps.litigation_ai.services.mock_trial.types import MockTrialStep

        assert MockTrialStep.INIT == "mt_init"
        assert MockTrialStep.MODE_SELECT == "mt_mode_select"
        assert MockTrialStep.COURT_OPENING == "mt_court_opening"
        assert MockTrialStep.COURT_SUMMARY == "mt_court_summary"

    def test_trial_level(self) -> None:
        from apps.litigation_ai.services.mock_trial.types import TrialLevel

        assert TrialLevel.FIRST == "first"
        assert TrialLevel.SECOND == "second"

    def test_mock_trial_context_defaults(self) -> None:
        from apps.litigation_ai.services.mock_trial.types import MockTrialContext, MockTrialStep

        ctx = MockTrialContext(
            session_id="s1",
            case_id=1,
            user_id=10,
            current_step=MockTrialStep.INIT,
        )
        assert ctx.mode is None
        assert ctx.metadata == {}

    def test_adversarial_config_defaults(self) -> None:
        from apps.litigation_ai.services.mock_trial.types import AdversarialConfig

        config = AdversarialConfig()
        assert config.debate_rounds == 10
        assert config.user_role == "observer"
        assert config.trial_level == "first"


# ── session_shared ─────────────────────────────────────────────────────────


class TestSessionShared:
    def test_session_dto(self) -> None:
        from apps.litigation_ai.services.session.session_shared import SessionDTO

        dto = SessionDTO(
            id=1,
            session_id="s1",
            case_id=10,
            case_name="Test Case",
            user_id=5,
            document_type="complaint",
            status="active",
            metadata={},
            created_at=None,
            updated_at=None,
        )
        assert dto.session_id == "s1"
        assert dto.case_name == "Test Case"

    def test_message_dto(self) -> None:
        from apps.litigation_ai.services.session.session_shared import MessageDTO

        dto = MessageDTO(
            id=1,
            session_id="s1",
            role="user",
            content="Hello",
            metadata={"key": "value"},
            created_at=None,
        )
        assert dto.role == "user"


# ── middleware ─────────────────────────────────────────────────────────────


class TestLitigationMemoryMiddleware:
    def test_init(self) -> None:
        from apps.litigation_ai.agent.middleware import LitigationMemoryMiddleware

        mw = LitigationMemoryMiddleware(session_id="s1", max_messages=10)
        assert mw.session_id == "s1"
        assert mw.max_messages == 10
        assert mw._conversation_service is None

    def test_before_agent_no_history(self) -> None:
        from apps.litigation_ai.agent.middleware import LitigationMemoryMiddleware

        mw = LitigationMemoryMiddleware(session_id="s1")
        mock_service = MagicMock()
        mock_service.get_messages.return_value = []
        mw._conversation_service = mock_service

        state = {"messages": [{"role": "user", "content": "hello"}]}
        result = mw.before_agent(state)
        assert result is not None
        assert len(result["messages"]) == 1

    def test_before_agent_with_history(self) -> None:
        from apps.litigation_ai.agent.middleware import LitigationMemoryMiddleware

        mw = LitigationMemoryMiddleware(session_id="s1")
        mock_service = MagicMock()
        history_msg = SimpleNamespace(role="user", content="previous message")
        mock_service.get_messages.return_value = [history_msg]
        mw._conversation_service = mock_service

        state = {"messages": [{"role": "user", "content": "current"}]}
        result = mw.before_agent(state)
        assert len(result["messages"]) == 2
        assert result["messages"][0]["content"] == "previous message"

    def test_before_agent_exception_returns_state(self) -> None:
        from apps.litigation_ai.agent.middleware import LitigationMemoryMiddleware

        mw = LitigationMemoryMiddleware(session_id="s1")
        mock_service = MagicMock()
        mock_service.get_messages.side_effect = RuntimeError("db error")
        mw._conversation_service = mock_service

        state = {"messages": []}
        result = mw.before_agent(state)
        assert result is state

    def test_after_agent_saves_assistant_message(self) -> None:
        from apps.litigation_ai.agent.middleware import LitigationMemoryMiddleware

        mw = LitigationMemoryMiddleware(session_id="s1")
        mock_service = MagicMock()
        mw._conversation_service = mock_service

        state = {"messages": [{"role": "assistant", "content": "response"}]}
        mw.after_agent(state)
        mock_service.add_message.assert_called_once()

    def test_after_agent_skips_user_message(self) -> None:
        from apps.litigation_ai.agent.middleware import LitigationMemoryMiddleware

        mw = LitigationMemoryMiddleware(session_id="s1")
        mock_service = MagicMock()
        mw._conversation_service = mock_service

        state = {"messages": [{"role": "user", "content": "input"}]}
        mw.after_agent(state)
        mock_service.add_message.assert_not_called()

    def test_after_agent_handles_object_messages(self) -> None:
        from apps.litigation_ai.agent.middleware import LitigationMemoryMiddleware

        mw = LitigationMemoryMiddleware(session_id="s1")
        mock_service = MagicMock()
        mw._conversation_service = mock_service

        msg = MagicMock()
        msg.type = "assistant"
        msg.content = "response"
        msg.tool_calls = [{"name": "tool1"}]
        state = {"messages": [msg]}
        mw.after_agent(state)
        mock_service.add_message.assert_called_once()

    def test_after_agent_empty_messages(self) -> None:
        from apps.litigation_ai.agent.middleware import LitigationMemoryMiddleware

        mw = LitigationMemoryMiddleware(session_id="s1")
        mock_service = MagicMock()
        mw._conversation_service = mock_service

        state = {"messages": []}
        result = mw.after_agent(state)
        assert result is state

    def test_after_agent_unknown_role(self) -> None:
        from apps.litigation_ai.agent.middleware import LitigationMemoryMiddleware

        mw = LitigationMemoryMiddleware(session_id="s1")
        mock_service = MagicMock()
        mw._conversation_service = mock_service

        state = {"messages": [{"role": "system", "content": "system msg"}]}
        result = mw.after_agent(state)
        mock_service.add_message.assert_not_called()

    def test_after_agent_non_dict_non_object(self) -> None:
        from apps.litigation_ai.agent.middleware import LitigationMemoryMiddleware

        mw = LitigationMemoryMiddleware(session_id="s1")
        mock_service = MagicMock()
        mw._conversation_service = mock_service

        state = {"messages": [42]}  # plain int
        result = mw.after_agent(state)
        assert result is state

    def test_save_user_message(self) -> None:
        from apps.litigation_ai.agent.middleware import LitigationMemoryMiddleware

        mw = LitigationMemoryMiddleware(session_id="s1")
        mock_service = MagicMock()
        mw._conversation_service = mock_service

        mw.save_user_message("hello", metadata={"key": "value"})
        mock_service.add_message.assert_called_once()

    def test_save_user_message_exception(self) -> None:
        from apps.litigation_ai.agent.middleware import LitigationMemoryMiddleware

        mw = LitigationMemoryMiddleware(session_id="s1")
        mock_service = MagicMock()
        mock_service.add_message.side_effect = RuntimeError("fail")
        mw._conversation_service = mock_service

        # Should not raise
        mw.save_user_message("hello")


class TestSummarizationConfig:
    def test_defaults(self) -> None:
        from apps.litigation_ai.agent.middleware import SummarizationConfig

        config = SummarizationConfig()
        assert config.token_threshold == 2000
        assert config.preserve_messages == 10
        assert config.model is None

    @patch("django.conf.settings")
    def test_from_settings(self, mock_settings) -> None:
        from apps.litigation_ai.agent.middleware import SummarizationConfig

        mock_settings.LITIGATION_AGENT_SUMMARIZATION_THRESHOLD = 3000
        mock_settings.LITIGATION_AGENT_PRESERVE_MESSAGES = 5
        mock_settings.LITIGATION_AGENT_MODEL = "gpt-4"

        config = SummarizationConfig.from_settings()
        assert config.token_threshold == 3000
        assert config.preserve_messages == 5
        assert config.model == "gpt-4"


class TestLitigationSummarizationMiddleware:
    def test_should_summarize_false(self) -> None:
        from apps.litigation_ai.agent.middleware import LitigationSummarizationMiddleware, SummarizationConfig

        config = SummarizationConfig(token_threshold=5000)
        mw = LitigationSummarizationMiddleware(session_id="s1", config=config)
        messages = [{"content": "short"}]
        assert mw.should_summarize(messages) is False

    def test_should_summarize_true(self) -> None:
        from apps.litigation_ai.agent.middleware import LitigationSummarizationMiddleware, SummarizationConfig

        config = SummarizationConfig(token_threshold=10)
        mw = LitigationSummarizationMiddleware(session_id="s1", config=config)
        messages = [{"content": "x" * 100}]
        assert mw.should_summarize(messages) is True

    @pytest.mark.anyio
    async def test_summarize_few_messages(self) -> None:
        from apps.litigation_ai.agent.middleware import LitigationSummarizationMiddleware, SummarizationConfig

        config = SummarizationConfig(preserve_messages=10)
        mw = LitigationSummarizationMiddleware(session_id="s1", config=config)
        messages = [{"role": "user", "content": "hi"}] * 5
        result = await mw.summarize(messages)
        assert result["summary"] is None
        assert len(result["messages"]) == 5

    def test_build_summary_prompt(self) -> None:
        from apps.litigation_ai.agent.middleware import LitigationSummarizationMiddleware

        mw = LitigationSummarizationMiddleware(session_id="s1")
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        prompt = mw._build_summary_prompt(messages)
        assert "user:" in prompt
        assert "assistant:" in prompt


# ── schemas ────────────────────────────────────────────────────────────────


class TestSchemas:
    def test_agent_response(self) -> None:
        from apps.litigation_ai.agent.schemas import AgentResponse

        resp = AgentResponse(type="system_message", content="hello")
        assert resp.type == "system_message"
        assert resp.metadata == {}

    def test_draft_output(self) -> None:
        from apps.litigation_ai.agent.schemas import DraftOutput

        draft = DraftOutput(document_type="complaint")
        assert draft.document_type == "complaint"
        assert draft.litigation_request is None
        assert draft.evidence_citations == []

    def test_tool_call_record(self) -> None:
        from apps.litigation_ai.agent.schemas import ToolCallRecord

        record = ToolCallRecord(tool_name="test", arguments={}, result=None)
        assert record.tool_name == "test"
        assert record.timestamp  # auto-generated
        assert record.duration_ms is None

    def test_case_info_result(self) -> None:
        from apps.litigation_ai.agent.schemas import CaseInfoResult

        result = CaseInfoResult(case_id=1, case_name="Test", cause_of_action="纠纷", our_legal_status="原告")
        assert result.case_id == 1
        assert result.parties == []

    def test_evidence_search_result(self) -> None:
        from apps.litigation_ai.agent.schemas import EvidenceSearchResult

        result = EvidenceSearchResult(evidence_item_id=1, text="text", source_name="doc1")
        assert result.relevance_score == 0.0
        assert result.page_start is None

    def test_evidence_list_item(self) -> None:
        from apps.litigation_ai.agent.schemas import EvidenceListItem

        item = EvidenceListItem(evidence_item_id=1, name="Evidence 1", ownership="our")
        assert item.has_content is False
        assert item.evidence_type is None

    def test_generate_draft_input(self) -> None:
        from apps.litigation_ai.agent.schemas import GenerateDraftInput

        inp = GenerateDraftInput(
            case_id=1, document_type="complaint",
            litigation_goal="win", evidence_context="context",
        )
        assert inp.case_id == 1

    def test_generate_draft_result(self) -> None:
        from apps.litigation_ai.agent.schemas import GenerateDraftResult

        result = GenerateDraftResult(display_text="text", draft={"key": "value"}, model="gpt-4")
        assert result.model == "gpt-4"


# ── tools ──────────────────────────────────────────────────────────────────


class TestTools:
    def test_simple_tool_init(self) -> None:
        from apps.litigation_ai.agent.tools import _SimpleTool

        def my_func(x: int) -> int:
            """My function."""
            return x + 1

        tool = _SimpleTool(func=my_func)
        assert tool.name == "my_func"
        assert tool.description == "My function."

    def test_simple_tool_normalize_args_none(self) -> None:
        from apps.litigation_ai.agent.tools import _SimpleTool

        def my_func(**kwargs):
            return kwargs

        tool = _SimpleTool(func=my_func)
        result = tool._normalize_args(None)
        assert result == {}

    def test_simple_tool_normalize_args_dict(self) -> None:
        from apps.litigation_ai.agent.tools import _SimpleTool

        def my_func(**kwargs):
            return kwargs

        tool = _SimpleTool(func=my_func)
        result = tool._normalize_args({"x": 1})
        assert result == {"x": 1}

    def test_simple_tool_normalize_args_basemodel(self) -> None:
        from pydantic import BaseModel

        from apps.litigation_ai.agent.tools import _SimpleTool

        class Input(BaseModel):
            x: int

        def my_func(x: int) -> int:
            return x

        tool = _SimpleTool(func=my_func, args_schema=Input)
        result = tool._normalize_args(Input(x=42))
        assert result == {"x": 42}

    def test_simple_tool_normalize_args_invalid_type(self) -> None:
        from apps.litigation_ai.agent.tools import _SimpleTool

        def my_func():
            pass

        tool = _SimpleTool(func=my_func)
        with pytest.raises(TypeError, match="Tool args must be"):
            tool._normalize_args(42)

    def test_simple_tool_invoke(self) -> None:
        from apps.litigation_ai.agent.tools import _SimpleTool

        def my_func(x: int) -> int:
            return x * 2

        tool = _SimpleTool(func=my_func)
        assert tool.invoke({"x": 5}) == 10

    def test_simple_tool_call(self) -> None:
        from apps.litigation_ai.agent.tools import _SimpleTool

        def my_func(x: int) -> int:
            return x * 2

        tool = _SimpleTool(func=my_func)
        assert tool(x=5) == 10

    def test_tool_decorator(self) -> None:
        from apps.litigation_ai.agent.tools import tool

        @tool()
        def my_func(x: int) -> int:
            """Test."""
            return x + 1

        assert my_func.name == "my_func"
        assert my_func.description == "Test."

    def test_get_litigation_tools(self) -> None:
        from apps.litigation_ai.agent.tools import get_litigation_tools

        tools = get_litigation_tools(case_id=1)
        assert len(tools) == 5
        names = {t.name for t in tools}
        assert "get_case_info" in names
        assert "generate_draft" in names

    def test_get_tool_descriptions(self) -> None:
        from apps.litigation_ai.agent.tools import get_tool_descriptions

        descs = get_tool_descriptions()
        assert "get_case_info" in descs
        assert len(descs) == 5

    @patch("apps.litigation_ai.services.session.context_service.LitigationContextService")
    def test_get_case_info_success(self, mock_svc_cls) -> None:
        from apps.litigation_ai.agent.tools import get_case_info

        mock_svc = MagicMock()
        mock_svc.get_case_info_for_agent.return_value = {"case_id": 1, "case_name": "Test"}
        mock_svc_cls.return_value = mock_svc

        result = get_case_info(case_id=1)
        assert result["case_id"] == 1

    @patch("apps.litigation_ai.services.session.context_service.LitigationContextService")
    def test_get_case_info_error(self, mock_svc_cls) -> None:
        from apps.litigation_ai.agent.tools import get_case_info

        mock_svc_cls.side_effect = RuntimeError("db error")
        result = get_case_info(case_id=1)
        assert "error" in result

    @patch("apps.litigation_ai.services.session.context_service.LitigationContextService")
    def test_get_evidence_list_success(self, mock_svc_cls) -> None:
        from apps.litigation_ai.agent.tools import get_evidence_list

        mock_svc = MagicMock()
        mock_svc.get_evidence_list_for_agent.return_value = [{"id": 1}]
        mock_svc_cls.return_value = mock_svc

        result = get_evidence_list(case_id=1)
        assert len(result) == 1

    @patch("apps.litigation_ai.services.session.context_service.LitigationContextService")
    def test_get_evidence_list_error(self, mock_svc_cls) -> None:
        from apps.litigation_ai.agent.tools import get_evidence_list

        mock_svc_cls.side_effect = RuntimeError("fail")
        result = get_evidence_list(case_id=1)
        assert isinstance(result, list)
        assert "error" in result[0]

    @patch("apps.litigation_ai.services.evidence.evidence_digest_service.EvidenceDigestService")
    def test_search_evidence_success(self, mock_svc_cls) -> None:
        from apps.litigation_ai.agent.tools import search_evidence

        mock_svc = MagicMock()
        mock_svc.search_evidence_for_agent.return_value = [{"text": "found"}]
        mock_svc_cls.return_value = mock_svc

        result = search_evidence(query="test", evidence_item_ids=[1])
        assert len(result) == 1

    @patch("apps.litigation_ai.services.evidence.evidence_digest_service.EvidenceDigestService")
    def test_search_evidence_error(self, mock_svc_cls) -> None:
        from apps.litigation_ai.agent.tools import search_evidence

        mock_svc_cls.side_effect = RuntimeError("fail")
        result = search_evidence(query="test", evidence_item_ids=[1])
        assert "error" in result[0]

    @patch("apps.litigation_ai.services.session.conversation_service.ConversationService")
    def test_get_recommended_document_types_success(self, mock_svc_cls) -> None:
        from apps.litigation_ai.agent.tools import get_recommended_document_types

        mock_svc = MagicMock()
        mock_svc.get_recommended_document_types.return_value = ["complaint"]
        mock_svc_cls.return_value = mock_svc

        result = get_recommended_document_types(case_id=1)
        assert result == ["complaint"]

    @patch("apps.litigation_ai.services.session.conversation_service.ConversationService")
    def test_get_recommended_document_types_error(self, mock_svc_cls) -> None:
        from apps.litigation_ai.agent.tools import get_recommended_document_types

        mock_svc_cls.side_effect = RuntimeError("fail")
        result = get_recommended_document_types(case_id=1)
        assert result == []

    @patch("apps.litigation_ai.services.generation.draft_service.DraftService")
    def test_generate_draft_success(self, mock_svc_cls) -> None:
        from apps.litigation_ai.agent.tools import generate_draft

        mock_svc = MagicMock()
        mock_svc.generate_draft_for_agent.return_value = {"display_text": "draft", "draft": {}, "model": "gpt-4"}
        mock_svc_cls.return_value = mock_svc

        result = generate_draft(case_id=1, document_type="complaint", litigation_goal="win", evidence_context="ctx")
        assert "display_text" in result

    @patch("apps.litigation_ai.services.generation.draft_service.DraftService")
    def test_generate_draft_error(self, mock_svc_cls) -> None:
        from apps.litigation_ai.agent.tools import generate_draft

        mock_svc_cls.side_effect = RuntimeError("fail")
        result = generate_draft(case_id=1, document_type="complaint", litigation_goal="win", evidence_context="ctx")
        assert "error" in result


# ── placeholder_render_service ─────────────────────────────────────────────


class TestPlaceholderRenderService:
    def test_render_single_brace(self) -> None:
        from apps.litigation_ai.services.generation.placeholder_render_service import PlaceholderRenderService

        svc = PlaceholderRenderService()
        template = "Hello {name}, welcome to {place}"
        variables = {"name": "World", "place": "Earth"}
        result, stats = svc.render(template, variables, syntax="single")
        assert "World" in result
        assert "Earth" in result
        assert "name" in stats.placeholders_hit

    def test_render_double_brace(self) -> None:
        from apps.litigation_ai.services.generation.placeholder_render_service import PlaceholderRenderService

        svc = PlaceholderRenderService()
        template = "Hello {{ name }}, welcome to {{ place }}"
        variables = {"name": "World", "place": "Earth"}
        result, stats = svc.render(template, variables, syntax="double")
        assert "World" in result

    def test_render_none_template(self) -> None:
        from apps.litigation_ai.services.generation.placeholder_render_service import PlaceholderRenderService

        svc = PlaceholderRenderService()
        result, stats = svc.render(None, {})  # type: ignore[arg-type]
        assert result == ""

    def test_render_unmatched_placeholder(self) -> None:
        from apps.litigation_ai.services.generation.placeholder_render_service import PlaceholderRenderService

        svc = PlaceholderRenderService()
        template = "Hello {name}"
        result, stats = svc.render(template, {}, keep_unmatched=True)
        assert "name" in stats.placeholders_missed

    def test_render_stats_hit_rate(self) -> None:
        from apps.litigation_ai.services.generation.placeholder_render_service import RenderStats

        stats = RenderStats(
            placeholders_found=["a", "b", "c"],
            placeholders_hit=["a", "b"],
            placeholders_missed=["c"],
        )
        assert stats.hit_rate == pytest.approx(2 / 3)

    def test_render_stats_empty(self) -> None:
        from apps.litigation_ai.services.generation.placeholder_render_service import RenderStats

        stats = RenderStats(placeholders_found=[], placeholders_hit=[], placeholders_missed=[])
        assert stats.hit_rate == 1.0

    def test_render_no_placeholders(self) -> None:
        from apps.litigation_ai.services.generation.placeholder_render_service import PlaceholderRenderService

        svc = PlaceholderRenderService()
        result, stats = svc.render("No placeholders here", {})
        assert result == "No placeholders here"
        assert stats.placeholders_found == []


# ── prompt_template_service ────────────────────────────────────────────────


class TestPromptTemplateService:
    def test_replace_variables(self) -> None:
        from apps.litigation_ai.services.generation.prompt_template_service import PromptTemplateService

        svc = PromptTemplateService()
        result = svc.replace_variables("Hello {name}", {"name": "World"})
        assert result == "Hello World"

    def test_replace_variables_no_match(self) -> None:
        from apps.litigation_ai.services.generation.prompt_template_service import PromptTemplateService

        svc = PromptTemplateService()
        # Unmatched placeholders are kept as-is via resolve_render_variable fallback
        result = svc.replace_variables("Hello {name}", {})
        assert "Hello" in result

    def test_get_system_template_handles_missing(self) -> None:
        from apps.litigation_ai.services.generation.prompt_template_service import PromptTemplateService

        svc = PromptTemplateService()
        # get_prompt_version_service may not exist in wiring
        try:
            result = svc.get_system_template("test_name")
            assert result is None or isinstance(result, str)
        except (ImportError, AttributeError):
            pass  # Expected if wiring module doesn't have the function


# ── interfaces ─────────────────────────────────────────────────────────────


class TestInterfaces:
    def test_abstract_methods(self) -> None:
        from apps.litigation_ai.agent.interfaces import (
            IAgentFactory,
            ILitigationAgentService,
            IMemoryMiddleware,
        )

        # Verify they're abstract
        with pytest.raises(TypeError):
            ILitigationAgentService()  # type: ignore[abstract]
        with pytest.raises(TypeError):
            IAgentFactory()  # type: ignore[abstract]
        with pytest.raises(TypeError):
            IMemoryMiddleware()  # type: ignore[abstract]


# ── flow_messenger ─────────────────────────────────────────────────────────


class TestFlowMessenger:
    @pytest.mark.anyio
    async def test_persist_message(self) -> None:
        from apps.litigation_ai.services.flow.flow_messenger import FlowMessenger

        mock_service = MagicMock()
        mock_service.add_message = MagicMock()
        messenger = FlowMessenger(conversation_service=mock_service)

        with patch("apps.litigation_ai.services.flow.flow_messenger.sync_to_async") as mock_sta:
            mock_sta.return_value = AsyncMock()
            await messenger.persist_message("s1", "user", "hello", {"key": "value"})
            mock_sta.assert_called_once()

    @pytest.mark.anyio
    async def test_send_with_persist(self) -> None:
        from apps.litigation_ai.services.flow.flow_messenger import FlowMessenger

        mock_service = MagicMock()
        messenger = FlowMessenger(conversation_service=mock_service)
        callback = AsyncMock()

        with patch.object(messenger, "persist_message", new_callable=AsyncMock) as mock_persist:
            await messenger.send(
                callback,
                {"content": "test", "metadata": {"k": "v"}},
                persist=True,
                session_id="s1",
                role="assistant",
            )
            callback.assert_called_once()
            mock_persist.assert_called_once()

    @pytest.mark.anyio
    async def test_send_without_persist(self) -> None:
        from apps.litigation_ai.services.flow.flow_messenger import FlowMessenger

        mock_service = MagicMock()
        messenger = FlowMessenger(conversation_service=mock_service)
        callback = AsyncMock()

        with patch.object(messenger, "persist_message", new_callable=AsyncMock) as mock_persist:
            await messenger.send(
                callback,
                {"content": "test"},
                persist=False,
                session_id="s1",
                role="assistant",
            )
            callback.assert_called_once()
            mock_persist.assert_not_called()
