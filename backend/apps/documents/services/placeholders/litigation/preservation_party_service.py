"""
财产保全申请书当事人信息服务

将原告替换为申请人,被告替换为被申请人,不包含第三人.

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7
"""

import logging
from collections import defaultdict
from typing import Any, ClassVar

from apps.documents.services.placeholders import BasePlaceholderService, PlaceholderRegistry

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class PreservationPartyService(BasePlaceholderService):
    """财产保全申请书当事人信息服务"""

    name: str = "preservation_party_service"
    display_name: str = "财产保全申请书当事人信息服务"
    description: str = "生成财产保全申请书的申请人和被申请人信息,原告替换为申请人,被告替换为被申请人"
    category: str = "litigation"
    placeholder_keys: ClassVar = ["财产保全申请书当事人信息"]
    placeholder_metadata: ClassVar = {
        "财产保全申请书当事人信息": {
            "display_name": "财产保全申请书当事人信息",
            "description": "申请人和被申请人的详细信息,原告替换为申请人,被告替换为被申请人,不包含第三人",
            "example_value": "申请人：张三,男,1980年01月01日出生\n地址：北京市朝阳区\n身份证号码：110101198001011234",
        }
    }

    def __init__(self) -> None:
        from .case_details_accessor import LitigationCaseDetailsAccessor
        from .party_formatter import PartyFormatter

        self.formatter = PartyFormatter()
        self.case_details_accessor = LitigationCaseDetailsAccessor()

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        生成占位符值

        Args:
            context_data: 包含 case 对象的上下文

        Returns:
            包含占位符键值对的字典
        """
        case_id = context_data.get("case_id") or getattr(context_data.get("case"), "id", None)
        if not case_id:
            return {"财产保全申请书当事人信息": ""}
        return {"财产保全申请书当事人信息": self.generate_party_info(case_id)}

    def generate_party_info(self, case_id: int) -> str:
        """
        生成财产保全申请书当事人信息

        将原告替换为申请人,被告替换为被申请人,不包含第三人.

        Args:
            case_id: 案件 ID

        Returns:
            str: 格式化后的当事人信息

        Requirements: 3.1, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7
        """
        from apps.core.models.enums import LegalStatus

        case_parties = self.case_details_accessor.get_case_parties(case_id=case_id)

        # 按法律地位分组
        grouped_parties: dict[str, list[Any]] = defaultdict(list)
        for party in case_parties:
            legal_status = party.get("legal_status")
            if legal_status:
                grouped_parties[legal_status].append(party)

        # 角色映射
        role_mapping: dict[str, str] = {
            LegalStatus.PLAINTIFF: "申请人",
            LegalStatus.DEFENDANT: "被申请人",
        }

        # 按顺序处理:申请人(原告)-> 被申请人(被告),不包含第三人
        result_parts: list[Any] = []

        for legal_status in [LegalStatus.PLAINTIFF, LegalStatus.DEFENDANT]:
            parties_in_group = grouped_parties.get(legal_status, [])

            if not parties_in_group:
                continue

            total = len(parties_in_group)
            role_name = role_mapping.get(legal_status, "")

            for index, party_dict in enumerate(parties_in_group):
                # 生成角色标签
                role_label = self.formatter.get_role_label(role_name, index, total)

                # 格式化当事人信息(使用字典数据)
                if self.formatter.is_natural_person_from_dict(party_dict):
                    party_info = self.formatter.format_natural_person_from_dict(role_label, party_dict)
                else:
                    party_info = self.formatter.format_legal_entity_from_dict(role_label, party_dict)

                result_parts.append(party_info)

        # 用空行分隔各当事人
        result = "\n\n".join(result_parts)

        logger.info("生成财产保全申请书当事人信息成功: case_id=%s, 当事人数=%s", case_id, len(result_parts))

        return result
