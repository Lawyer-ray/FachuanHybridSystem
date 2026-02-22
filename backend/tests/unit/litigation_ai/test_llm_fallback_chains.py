import pytest

from apps.litigation_ai.chains.document_type_parse_chain import DocumentTypeParseChain
from apps.litigation_ai.chains.litigation_goal_intake_chain import LitigationGoalIntakeChain
from apps.litigation_ai.chains.user_choice_parse_chain import UserChoiceParseChain


@pytest.mark.anyio
async def test_document_type_parse_chain_fallback_without_api_key(monkeypatch):
    monkeypatch.setattr("apps.core.llm.config.LLMConfig.get_api_key", lambda: "")
    chain = DocumentTypeParseChain()
    result = await chain.arun(user_input="起诉状", allowed_types=["complaint", "defense"])
    assert result.document_type == "complaint"


@pytest.mark.anyio
async def test_user_choice_parse_chain_fallback_all(monkeypatch):
    monkeypatch.setattr("apps.core.llm.config.LLMConfig.get_api_key", lambda: "")
    chain = UserChoiceParseChain()
    result = await chain.arun(
        user_input="都要",
        primary_document_type="complaint",
        optional_document_types=["counterclaim_defense"],
    )
    assert result.primary_document_type == "complaint"
    assert "counterclaim_defense" in result.pending_document_types


@pytest.mark.anyio
async def test_goal_intake_chain_fallback_clarifies_when_too_short(monkeypatch):
    monkeypatch.setattr("apps.core.llm.config.LLMConfig.get_api_key", lambda: "")
    chain = LitigationGoalIntakeChain()
    result = await chain.arun(case_info={}, document_type="complaint", user_input="追回钱")
    assert result.need_clarification is True
    assert result.clarifying_question
