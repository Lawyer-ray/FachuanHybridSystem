"""Business logic services."""

import logging
from typing import Any, ClassVar

from apps.core.enums import LegalStatus
from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry
from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class LitigationDatePlaceholderService(BasePlaceholderService):
    name: str = "litigation_date_placeholder_service"
    display_name: str = "诉讼文书-日期"
    description: str = "生成诉讼文书模板中的日期占位符"
    category: str = "litigation"
    placeholder_keys: ClassVar = [LitigationPlaceholderKeys.DATE]

    def __init__(self) -> None:
        from .case_details_accessor import LitigationCaseDetailsAccessor

        self.case_details_accessor = LitigationCaseDetailsAccessor()

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        case_id = context_data.get("case_id") or getattr(context_data.get("case"), "id", None)
        if not case_id:
            return {}
        return {LitigationPlaceholderKeys.DATE: self.case_details_accessor.get_formatted_date(case_id=case_id)}


class _LitigationPartyNameBase(BasePlaceholderService):
    legal_status: str = ""
    placeholder_key: str = ""

    def __init__(self) -> None:
        from .case_details_accessor import LitigationCaseDetailsAccessor

        self.case_details_accessor = LitigationCaseDetailsAccessor()

    def _get_first_party_name(self, *, case_id: int, legal_status: str) -> str:
        parties = self.case_details_accessor.get_case_parties(case_id=case_id)
        for party in parties:
            if party.get("legal_status") == legal_status:
                name = party.get("client_name") or ""
                if name:
                    return name
        return "未指定"

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        case_id = context_data.get("case_id") or getattr(context_data.get("case"), "id", None)
        if not case_id:
            return {}
        return {self.placeholder_key: self._get_first_party_name(case_id=case_id, legal_status=self.legal_status)}


@PlaceholderRegistry.register
class LitigationPlaintiffNamePlaceholderService(_LitigationPartyNameBase):
    name: str = "litigation_plaintiff_name_placeholder_service"
    display_name: str = "诉讼文书-原告"
    description: str = "生成诉讼文书模板中的原告占位符"
    category: str = "litigation"
    placeholder_key = LitigationPlaceholderKeys.PLAINTIFF
    placeholder_keys: ClassVar = [LitigationPlaceholderKeys.PLAINTIFF]
    legal_status = LegalStatus.PLAINTIFF


@PlaceholderRegistry.register
class LitigationDefendantNamePlaceholderService(_LitigationPartyNameBase):
    name: str = "litigation_defendant_name_placeholder_service"
    display_name: str = "诉讼文书-被告"
    description: str = "生成诉讼文书模板中的被告占位符"
    category: str = "litigation"
    placeholder_key = LitigationPlaceholderKeys.DEFENDANT
    placeholder_keys: ClassVar = [LitigationPlaceholderKeys.DEFENDANT]
    legal_status = LegalStatus.DEFENDANT


@PlaceholderRegistry.register
class LitigationRespondentNamePlaceholderService(_LitigationPartyNameBase):
    name: str = "litigation_respondent_name_placeholder_service"
    display_name: str = "诉讼文书-答辩人"
    description: str = "生成诉讼文书模板中的答辩人占位符(默认取被告)"
    category: str = "litigation"
    placeholder_key = LitigationPlaceholderKeys.RESPONDENT
    placeholder_keys: ClassVar = [LitigationPlaceholderKeys.RESPONDENT]
    legal_status = LegalStatus.DEFENDANT


@PlaceholderRegistry.register
class LitigationCauseOfActionPlaceholderService(BasePlaceholderService):
    name: str = "litigation_cause_of_action_placeholder_service"
    display_name: str = "诉讼文书-案由"
    description: str = "生成诉讼文书模板中的案由占位符"
    category: str = "litigation"
    placeholder_keys: ClassVar = [LitigationPlaceholderKeys.CAUSE_OF_ACTION]

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        case_dto = context_data.get("case_dto")
        cause_of_action = getattr(case_dto, "cause_of_action", None) or "民事纠纷"
        return {LitigationPlaceholderKeys.CAUSE_OF_ACTION: cause_of_action}
