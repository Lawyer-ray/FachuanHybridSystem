"""
财产保全申请书签名盖章信息服务

将原告替换为申请人,只包含我方当事人且法律地位为原告或第三人.

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
"""

import logging
from typing import Any, ClassVar

from apps.documents.services.placeholders import BasePlaceholderService, PlaceholderRegistry

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class PreservationSignatureService(BasePlaceholderService):
    """财产保全申请书签名盖章信息服务"""

    name: str = "preservation_signature_service"
    display_name: str = "财产保全申请书签名盖章信息服务"
    description: str = "生成财产保全申请书的签名盖章信息,原告替换为申请人"
    category: str = "litigation"
    placeholder_keys: ClassVar = ["财产保全申请书签名盖章信息"]
    placeholder_metadata: ClassVar = {
        "财产保全申请书签名盖章信息": {
            "display_name": "财产保全申请书签名盖章信息",
            "description": "申请人的签名盖章信息,原告替换为申请人,只包含我方当事人",
            "example_value": "申请人(签名+指模):张三\n日期:2025年01月27日",
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
            return {"财产保全申请书签名盖章信息": ""}
        return {"财产保全申请书签名盖章信息": self.generate_signature_info(case_id)}

    def _format_date(self, case_id: int) -> str:
        """
        格式化日期为 YYYY年MM月DD日

        优先使用案件的 specified_date,否则使用当前日期.

        Args:
            case_id: 案件 ID

        Returns:
            str: 格式化后的日期

        Requirements: 3.1, 7.5, 7.6
        """
        return self.case_details_accessor.get_formatted_date(case_id=case_id)

    def generate_signature_info(self, case_id: int) -> str:
        """
        生成财产保全申请书签名盖章信息

        将原告替换为申请人,只包含我方当事人且法律地位为原告或第三人.

        Args:
            case_id: 案件 ID

        Returns:
            str: 格式化后的签名盖章信息

        Requirements: 3.1, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
        """
        from apps.core.enums import LegalStatus

        case_parties = self.case_details_accessor.get_case_parties(case_id=case_id)

        # 筛选:is_our_client=True 且 legal_status in [原告, 第三人]
        parties = [
            p
            for p in case_parties
            if p.get("is_our_client") and p.get("legal_status") in [LegalStatus.PLAINTIFF, LegalStatus.THIRD]
        ]

        if not parties:
            logger.warning("未找到符合条件的签名主体: case_id=%s", case_id)
            return ""

        # 格式化日期
        date_str = self._format_date(case_id)

        # 角色映射
        role_mapping: dict[str, str] = {
            LegalStatus.PLAINTIFF: "申请人",
            LegalStatus.DEFENDANT: "被申请人",
            LegalStatus.THIRD: "第三人",
        }

        # 生成签名块
        signature_blocks: list[Any] = []

        for party_dict in parties:
            # 使用映射后的角色名
            role = role_mapping.get(party_dict.get("legal_status"), party_dict.get("legal_status"))

            if self.formatter.is_natural_person_from_dict(party_dict):
                # 自然人签名格式
                name = party_dict.get("client_name") or ""
                signature_block = f"{role}(签名+指模):{name}\n日期:{date_str}"
            else:
                # 法人签名格式
                company_name = party_dict.get("client_name") or ""
                legal_rep = party_dict.get("legal_representative") or ""
                signature_block = f"{role}(盖章):{company_name}\n法定代表人(签名):{legal_rep}\n日期:{date_str}"

            signature_blocks.append(signature_block)

        # 用空行分隔各签名块
        result = "\n\n".join(signature_blocks)

        logger.info("生成财产保全申请书签名盖章信息成功: case_id=%s, 签名主体数=%s", case_id, len(signature_blocks))

        return result
