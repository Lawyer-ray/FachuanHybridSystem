import pytest

from apps.litigation_ai.chains.litigation_draft_chain import LitigationDraftChain


class _FakeResponse:
    def __init__(self, content: str):
        self.content = content
        self.response_metadata = {"token_usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}}


class _FakeLLM:
    async def ainvoke(self, messages):
        return _FakeResponse('{"litigation_request":"一、支付货款。","facts_and_reasons":"双方签订合同。","evidence_citations":[{"evidence_item_id":123,"evidence_name":"合同","pages":"1-2","used_in":"事实与理由"}]}')


@pytest.mark.anyio
async def test_litigation_draft_chain_returns_structured_draft(monkeypatch):
    class _FakeLLMService:
        def get_langchain_llm(self, **kwargs):
            return _FakeLLM()

    monkeypatch.setattr("apps.core.interfaces.ServiceLocator.get_llm_service", lambda: _FakeLLMService())
    monkeypatch.setattr(
        "apps.litigation_ai.services.prompt_template_service.PromptTemplateService.get_system_template",
        lambda self, name: None,
    )

    chain = LitigationDraftChain()
    result = await chain.arun(
        case_info={"case_name": "测试案件", "cause_of_action": "合同纠纷"},
        document_type="complaint",
        litigation_goal="追回欠款",
        evidence_text="1. 合同（证明合同关系）",
        stream_callback=None,
    )

    assert "诉讼请求" in result.display_text
    assert "事实与理由" in result.display_text
    assert result.draft["litigation_request"] == "一、支付货款。"
    assert result.draft["facts_and_reasons"] == "双方签订合同。"
    assert result.draft["evidence_citations"][0]["evidence_item_id"] == 123
    assert result.token_usage["total_tokens"] == 3


class _FakeDefenseLLM:
    async def ainvoke(self, messages):
        return _FakeResponse('{"defense_opinion":"不同意。","defense_reason":"合同已解除。","rebuttal_to_opponent_evidence":["对方证据1与事实不符"],"evidence_citations":[]}')


@pytest.mark.anyio
async def test_litigation_draft_chain_defense(monkeypatch):
    class _FakeLLMService:
        def get_langchain_llm(self, **kwargs):
            return _FakeDefenseLLM()

    monkeypatch.setattr("apps.core.interfaces.ServiceLocator.get_llm_service", lambda: _FakeLLMService())
    monkeypatch.setattr(
        "apps.litigation_ai.services.prompt_template_service.PromptTemplateService.get_system_template",
        lambda self, name: None,
    )

    chain = LitigationDraftChain()
    result = await chain.arun(
        case_info={"case_name": "测试案件", "cause_of_action": "合同纠纷"},
        document_type="defense",
        litigation_goal="驳回诉请",
        evidence_text="",
        stream_callback=None,
    )

    assert "答辩意见" in result.display_text
    assert result.draft["defense_opinion"] == "不同意。"
    assert result.draft["defense_reason"] == "合同已解除。"
