"""
起诉状当事人信息服务

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 8.3, 9.1, 9.2
"""

import logging
from collections import defaultdict
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry
from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class ComplaintPartyService(BasePlaceholderService):
    """起诉状当事人信息服务"""

    name: str = "litigation_complaint_party_service"
    display_name: str = "诉讼文书-起诉状当事人信息"
    description: str = "生成起诉状模板中的当事人信息占位符"
    category: str = "litigation"
    placeholder_keys: ClassVar = [LitigationPlaceholderKeys.COMPLAINT_PARTY]

    def __init__(self) -> None:
        from .case_details_accessor import LitigationCaseDetailsAccessor
        from .party_formatter import PartyFormatter

        self.formatter = PartyFormatter()
        self.case_details_accessor = LitigationCaseDetailsAccessor()

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        case_id = context_data.get("case_id") or getattr(context_data.get("case"), "id", None)
        if not case_id:
            return {}
        return {LitigationPlaceholderKeys.COMPLAINT_PARTY: self.generate_party_info(case_id)}

    def generate_party_info(self, case_id: int) -> str:
        """
        生成起诉状当事人信息

        Args:
            case_id: 案件 ID

        Returns:
            str: 格式化后的当事人信息

        Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 3.1, 8.3, 9.1, 9.2
        """
        from apps.core.models.enums import LegalStatus

        case_parties = self.case_details_accessor.get_case_parties(case_id=case_id)

        # 按法律地位分组
        grouped_parties: dict[str, list[Any]] = defaultdict(list)
        for party in case_parties:
            legal_status = party.get("legal_status")
            if legal_status:
                grouped_parties[legal_status].append(party)

        # 按顺序处理
        result_parts: list[Any] = []

        # 法律地位的中文映射
        legal_status_map = {LegalStatus.PLAINTIFF: "原告", LegalStatus.DEFENDANT: "被告", LegalStatus.THIRD: "第三人"}

        for legal_status in [LegalStatus.PLAINTIFF, LegalStatus.DEFENDANT, LegalStatus.THIRD]:
            parties_in_group = grouped_parties.get(legal_status, [])

            if not parties_in_group:
                continue

            total = len(parties_in_group)

            for index, party_dict in enumerate(parties_in_group):
                # 生成角色标签(使用中文)
                chinese_legal_status = legal_status_map.get(legal_status, legal_status)
                role_label = self.formatter.get_role_label(chinese_legal_status, index, total)

                # 格式化当事人信息(使用字典数据)
                if self.formatter.is_natural_person_from_dict(party_dict):
                    party_info = self.formatter.format_natural_person_from_dict(role_label, party_dict)
                else:
                    party_info = self.formatter.format_legal_entity_from_dict(role_label, party_dict)

                result_parts.append(party_info)

        # 用空行分隔各当事人
        result = "\n\n".join(result_parts)

        logger.info("生成起诉状当事人信息成功: case_id=%s, 当事人数=%s", case_id, len(result_parts))

        return result
