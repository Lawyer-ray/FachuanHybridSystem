"""
诉讼文书生成上下文服务

提供案件信息、证据列表等上下文数据的获取功能.

Requirements: 2.1, 2.2
"""

import logging
from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import NotFoundError

logger = logging.getLogger("apps.litigation_ai")


class LitigationContextService:
    """
    诉讼文书生成上下文服务

    负责获取案件信息、证据列表等上下文数据,供 Agent 工具调用.
    """

    def get_case_info_for_agent(self, case_id: int) -> dict[str, Any]:
        """
        获取案件信息(供 Agent 工具调用)

        Args:
            case_id: 案件 ID

        Returns:
            案件信息字典,包含 case_id, case_name, cause_of_action,
            target_amount, our_legal_status, parties, court_info 等字段

        Raises:
            NotFoundError: 案件不存在时抛出
        """
        from ..wiring import get_case_service

        case_service = get_case_service()
        details = case_service.get_case_with_details_internal(case_id)
        if not details:
            raise NotFoundError(message=_("案件不存在"), code="CASE_NOT_FOUND", errors={"case_id": case_id})

        parties = []
        for party in details.get("case_parties", []) or []:
            parties.append(
                {
                    "name": party.get("client_name") or "",
                    "party_type": party.get("client_type") or "",
                    "legal_status": party.get("legal_status") or "",
                    "is_our_side": bool(party.get("is_our_client")),
                }
            )
        court_info = None

        return {
            "case_id": case_id,
            "case_name": details.get("name") or "",
            "cause_of_action": details.get("cause_of_action") or "",
            "target_amount": str(details.get("target_amount")) if details.get("target_amount") is not None else None,
            "our_legal_status": None,
            "parties": parties,
            "court_info": court_info,
            "case_stage": details.get("current_stage") or "",
            "case_status": details.get("status") or "",
        }

    def _get_parties_for_agent(self, case: Any) -> list[dict[str, Any]]:
        """
        获取案件当事人信息

        Args:
            case: Case 模型实例

        Returns:
            当事人列表
        """
        parties = []

        # 尝试从 CaseParty 关联获取
        if hasattr(case, "parties"):
            for party in case.parties.all():
                parties.append(
                    {
                        "name": getattr(party, "name", "") or "",
                        "party_type": getattr(party, "party_type", "") or "",
                        "legal_status": getattr(party, "legal_status", "") or "",
                        "is_our_side": getattr(party, "is_our_side", False),
                    }
                )

        return parties

    def get_evidence_list_for_agent(
        self,
        case_id: int,
        ownership: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        获取案件证据列表(供 Agent 工具调用)

        Args:
            case_id: 案件 ID
            ownership: 证据归属过滤,'our'(我方), 'opponent'(对方), None(全部)

        Returns:
            证据项列表
        """
        from ..wiring import get_evidence_query_service

        items = get_evidence_query_service().list_evidence_items_for_case_internal(case_id)
        evidence_list = []
        for item in items:
            evidence_list.append(
                {
                    "evidence_item_id": item.id,
                    "name": item.name or "",
                    "evidence_type": None,
                    "ownership": ownership,
                    "description": item.purpose or "",
                    "has_content": bool(item.file_path),
                }
            )

        return evidence_list

    def build_case_info(self, case_id: int, document_type: str) -> dict[str, Any]:
        from ..wiring import get_case_service

        case_dto = get_case_service().get_case_internal(case_id)
        if not case_dto:
            raise NotFoundError(message=_("案件不存在"), code="CASE_NOT_FOUND", errors={"case_id": case_id})

        from apps.litigation_ai.placeholders import LitigationPlaceholderContextService, LitigationPlaceholderKeys

        fixed_blocks = LitigationPlaceholderContextService().build_fixed_blocks(case_id, document_type)

        return {
            "case_id": case_id,
            "case_name": case_dto.name or "",
            "cause_of_action": case_dto.cause_of_action or "",
            "target_amount": case_dto.target_amount,
            "system_generated_party_block": fixed_blocks.get(LitigationPlaceholderKeys.COMPLAINT_PARTY)
            or fixed_blocks.get(LitigationPlaceholderKeys.DEFENSE_PARTY, ""),
            "system_generated_signature_block": fixed_blocks.get(LitigationPlaceholderKeys.COMPLAINT_SIGNATURE)
            or fixed_blocks.get(LitigationPlaceholderKeys.DEFENSE_SIGNATURE, ""),
            "system_generated_court_block": fixed_blocks.get(LitigationPlaceholderKeys.COURT, ""),
            "system_generated_fixed_blocks": fixed_blocks,
        }
