import pytest
from unittest.mock import Mock, patch


class TestLitigationGenerationService:
    def test_generate_complaint_delegates_to_generator(self):
        from apps.documents.services.generation.litigation_generation_service import LitigationGenerationService
        from apps.documents.services.generation.outputs import ComplaintOutput, PartyInfo

        expected = ComplaintOutput(
            title="民事起诉状",
            parties=[PartyInfo(name="张三", role="原告")],
            litigation_request="请求",
            facts_and_reasons="事实",
            evidence=[],
        )

        mock_generator = Mock()
        mock_generator.generate_complaint.return_value = expected

        service = LitigationGenerationService(llm_generator=mock_generator)
        result = service.generate_complaint({"k": "v"})

        assert result == expected
        mock_generator.generate_complaint.assert_called_once()

    def test_generate_defense_delegates_to_generator(self):
        from apps.documents.services.generation.litigation_generation_service import LitigationGenerationService
        from apps.documents.services.generation.outputs import DefenseOutput, PartyInfo

        expected = DefenseOutput(
            title="民事答辩状",
            parties=[PartyInfo(name="李四", role="被告")],
            defense_opinion="意见",
            defense_reasons="理由",
            evidence=[],
        )

        mock_generator = Mock()
        mock_generator.generate_defense.return_value = expected

        service = LitigationGenerationService(llm_generator=mock_generator)
        result = service.generate_defense({"k": "v"})

        assert result == expected
        mock_generator.generate_defense.assert_called_once()


@pytest.mark.django_db
def test_litigation_llm_generator_uses_llm_service_structured_llm():
    from apps.documents.services.generation.litigation_llm_generator import LitigationLLMGenerator
    from apps.documents.services.generation.outputs import ComplaintOutput, PartyInfo

    llm_service = Mock()
    structured_llm = Mock()
    llm_service.get_structured_llm.return_value = structured_llm

    mock_prompt = Mock()
    mock_chain = Mock()
    mock_chain_with_retry = Mock()
    mock_chain.with_retry.return_value = mock_chain_with_retry

    expected = ComplaintOutput(
        title="民事起诉状",
        parties=[PartyInfo(name="张三", role="原告")],
        litigation_request="请求",
        facts_and_reasons="事实",
        evidence=[],
    )
    mock_chain_with_retry.invoke.return_value = expected

    mock_prompt.__or__ = Mock(return_value=mock_chain)

    with patch("apps.documents.services.generation.litigation_llm_generator.PromptTemplateFactory") as mock_factory:
        mock_factory.get_complaint_prompt.return_value = mock_prompt

        generator = LitigationLLMGenerator(llm_service=llm_service)
        result = generator.generate_complaint({"k": "v"})

        assert result == expected
        llm_service.get_structured_llm.assert_called_once_with(ComplaintOutput, method="json_mode")
        mock_chain.with_retry.assert_called_once()
