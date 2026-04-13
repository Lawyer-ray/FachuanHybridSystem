"""强制执行申请书申请人财产线索服务"""

import logging
from typing import Any, ClassVar

from apps.core.models.enums import LegalStatus
from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry
from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class EnforcementApplicantPropertyClueService(BasePlaceholderService):
    """强制执行申请书申请人财产线索服务"""

    name: str = "enforcement_applicant_property_clue_service"
    display_name: str = "诉讼文书-强制执行申请书申请人财产线索"
    description: str = "生成申请人的财产线索信息"
    category: str = "litigation"
    placeholder_keys: ClassVar = [LitigationPlaceholderKeys.ENFORCEMENT_APPLICANT_PROPERTY_CLUE]

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        case_id = context_data.get("case_id") or getattr(context_data.get("case"), "id", None)
        if not case_id:
            return {LitigationPlaceholderKeys.ENFORCEMENT_APPLICANT_PROPERTY_CLUE: ""}
        return {
            LitigationPlaceholderKeys.ENFORCEMENT_APPLICANT_PROPERTY_CLUE: self.generate_property_clue_info(case_id)
        }

    def generate_property_clue_info(self, case_id: int) -> str:
        """
        生成申请人的财产线索信息，直接输出PropertyClue.content内容

        Args:
            case_id: 案件 ID

        Returns:
            str: 财产线索内容
        """
        from apps.documents.services.infrastructure.wiring import get_case_service, get_client_service

        client_service = get_client_service()
        case_service = get_case_service()

        # 获取申请人（原告/申请人）
        applicant_party_dtos = case_service.get_case_parties_internal(
            case_id=case_id, legal_status=LegalStatus.PLAINTIFF
        )
        if not applicant_party_dtos:
            applicant_party_dtos = case_service.get_case_parties_internal(
                case_id=case_id, legal_status=LegalStatus.APPLICANT
            )

        if not applicant_party_dtos:
            logger.warning("未找到申请人: case_id=%s", case_id)
            return ""

        lines: list[str] = []

        for party_dto in applicant_party_dtos:
            client_id = party_dto.client_id
            clue_dtos = client_service.get_property_clues_by_client_internal(client_id)
            for clue in clue_dtos:
                content = clue.content or ""
                for line in content.split("\n"):
                    stripped = line.strip()
                    if stripped:
                        lines.append(stripped)

        result = "\a".join(lines)
        logger.info("生成申请人财产线索成功: case_id=%s, 行数=%s", case_id, len(lines))
        return result
