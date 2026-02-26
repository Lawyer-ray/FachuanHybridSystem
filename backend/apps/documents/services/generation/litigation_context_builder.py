"""Business logic services."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.documents.services.generation.outputs import ComplaintOutput, DefenseOutput

from apps.core.enums import LegalStatus
from apps.documents.services.placeholders import EnhancedContextBuilder
from apps.documents.services.infrastructure.wiring import get_case_service
from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys

logger = logging.getLogger("apps.documents.generation")


class LitigationContextBuilder:
    def __init__(self, enhanced_context_builder: EnhancedContextBuilder | None = None) -> None:
        self._enhanced_context_builder = enhanced_context_builder

    @property
    def enhanced_context_builder(self) -> EnhancedContextBuilder:
        if self._enhanced_context_builder is None:
            self._enhanced_context_builder = EnhancedContextBuilder()
        return self._enhanced_context_builder

    def convert_to_paragraphs(self, text: str) -> str:
        if not text:
            return ""
        return text.replace("\r\n", "\a").replace("\n", "\a")

    def _get_party_name_for_prompt(self, *, case_id: int, legal_status: str) -> Any:
        case_service = get_case_service()
        party_names = case_service.get_case_parties_by_legal_status_internal(case_id=case_id, legal_status=legal_status)
        if party_names:
            return party_names[0]
        return "未指定"

    def extract_complaint_prompt_data(self, case_dto: Any) -> dict[str, Any]:
        case_id = case_dto.id
        plaintiff = self._get_party_name_for_prompt(case_id=case_id, legal_status=LegalStatus.PLAINTIFF)
        defendant = self._get_party_name_for_prompt(case_id=case_id, legal_status=LegalStatus.DEFENDANT)
        return {
            "cause_of_action": case_dto.cause_of_action or "民事纠纷",
            "plaintiff": plaintiff,
            "defendant": defendant,
            "litigation_request": "请求依法判决",
            "facts_and_reasons": "事实与理由待补充",
        }

    def extract_defense_prompt_data(self, case_dto: Any) -> dict[str, Any]:
        case_id = case_dto.id
        plaintiff = self._get_party_name_for_prompt(case_id=case_id, legal_status=LegalStatus.PLAINTIFF)
        defendant = self._get_party_name_for_prompt(case_id=case_id, legal_status=LegalStatus.DEFENDANT)
        return {
            "cause_of_action": case_dto.cause_of_action or "民事纠纷",
            "plaintiff": plaintiff,
            "defendant": defendant,
            "defense_opinion": "不同意原告的诉讼请求",
            "defense_reasons": "答辩理由待补充",
        }

    def build_complaint_context(self, *, case_dto: Any, llm_result: ComplaintOutput) -> dict[str, Any]:
        context_data = {"case_id": case_dto.id, "case_dto": case_dto}
        required = [
            LitigationPlaceholderKeys.PLAINTIFF,
            LitigationPlaceholderKeys.DEFENDANT,
            LitigationPlaceholderKeys.CAUSE_OF_ACTION,
            LitigationPlaceholderKeys.DATE,
            LitigationPlaceholderKeys.COMPLAINT_PARTY,
            LitigationPlaceholderKeys.COURT,
            LitigationPlaceholderKeys.COMPLAINT_SIGNATURE,
        ]
        context = self.enhanced_context_builder.build_context(context_data, required_placeholders=required) # type: ignore[no-any-return]
        context.update(
            {
                LitigationPlaceholderKeys.VARIABLE_LITIGATION_REQUEST: self.convert_to_paragraphs(
                    llm_result.litigation_request
                ),
                LitigationPlaceholderKeys.VARIABLE_FACTS_AND_REASONS: self.convert_to_paragraphs(
                    llm_result.facts_and_reasons
                ),
            }
        )
        return context

    def build_defense_context(self, *, case_dto: Any, llm_result: DefenseOutput) -> dict[str, Any]:
        context_data = {"case_id": case_dto.id, "case_dto": case_dto}
        required = [
            LitigationPlaceholderKeys.PLAINTIFF,
            LitigationPlaceholderKeys.DEFENDANT,
            LitigationPlaceholderKeys.RESPONDENT,
            LitigationPlaceholderKeys.CAUSE_OF_ACTION,
            LitigationPlaceholderKeys.DATE,
            LitigationPlaceholderKeys.DEFENSE_PARTY,
            LitigationPlaceholderKeys.COURT,
            LitigationPlaceholderKeys.DEFENSE_SIGNATURE,
        ]
        context = self.enhanced_context_builder.build_context(context_data, required_placeholders=required) # type: ignore[no-any-return]
        context.update(
            {
                LitigationPlaceholderKeys.VARIABLE_DEFENSE_OPINION: llm_result.defense_opinion,
                LitigationPlaceholderKeys.VARIABLE_DEFENSE_REASONS: self.convert_to_paragraphs(
                    llm_result.defense_reasons
                ),
            }
        )
        return context
