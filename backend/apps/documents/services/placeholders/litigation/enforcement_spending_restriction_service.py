"""强制执行申请书 - 限制高消费事项占位符服务."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry
from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class EnforcementSpendingRestrictionRequestService(BasePlaceholderService):
    """生成强制执行申请书中的“限制高消费事项”占位符."""

    name: str = "enforcement_spending_restriction_request_service"
    display_name: str = "诉讼文书-强制执行申请书限制高消费事项"
    description: str = "根据被申请人信息生成限制高消费事项"
    category: str = "litigation"
    placeholder_keys: ClassVar = [LitigationPlaceholderKeys.ENFORCEMENT_SPENDING_RESTRICTION_REQUEST]

    def __init__(self) -> None:
        from .case_details_accessor import LitigationCaseDetailsAccessor

        self.case_details_accessor = LitigationCaseDetailsAccessor()

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        case_id = context_data.get("case_id") or getattr(context_data.get("case"), "id", None)
        if not case_id:
            return {}

        target_text = self._build_target_text(case_id=int(case_id))
        if not target_text:
            logger.warning("未找到被申请人信息，限制高消费事项为空: case_id=%s", case_id)
            return {LitigationPlaceholderKeys.ENFORCEMENT_SPENDING_RESTRICTION_REQUEST: ""}

        text = f"请求贵院依法对被申请人{target_text}采取高消费限制令。"
        return {LitigationPlaceholderKeys.ENFORCEMENT_SPENDING_RESTRICTION_REQUEST: text}

    def _build_target_text(self, *, case_id: int) -> str:
        from apps.core.models.enums import LegalStatus

        case_parties = self.case_details_accessor.get_case_parties(case_id=case_id)
        respondents = [
            p for p in case_parties if p.get("legal_status") in (LegalStatus.DEFENDANT, LegalStatus.RESPONDENT)
        ]
        if not respondents:
            return ""

        segments: list[str] = []
        seen_segments: set[str] = set()
        covered_natural_names: set[str] = set()

        # 先处理法人，把法定代表人并入对应法人条目
        for party in respondents:
            client_type = str(party.get("client_type") or "").strip()
            if client_type == "natural":
                continue

            company_name = str(party.get("client_name") or "").strip()
            if not company_name:
                continue

            legal_representative = str(party.get("legal_representative") or "").strip()
            if legal_representative:
                segment = f"{company_name}及其法定代表人{legal_representative}"
                covered_natural_names.add(legal_representative)
            else:
                segment = company_name

            if segment not in seen_segments:
                seen_segments.add(segment)
                segments.append(segment)

        # 再处理自然人，避免重复写入已作为法人法代出现的人名
        for party in respondents:
            client_type = str(party.get("client_type") or "").strip()
            if client_type != "natural":
                continue

            name = str(party.get("client_name") or "").strip()
            if not name or name in covered_natural_names:
                continue
            if name in seen_segments:
                continue
            seen_segments.add(name)
            segments.append(name)

        return "、".join(segments)
