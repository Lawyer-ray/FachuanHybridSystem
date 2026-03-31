"""
起诉状签名盖章信息服务

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 8.3
"""

import logging
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry
from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class ComplaintSignatureService(BasePlaceholderService):
    """起诉状签名盖章信息服务"""

    name: str = "litigation_complaint_signature_service"
    display_name: str = "诉讼文书-起诉状签名盖章信息"
    description: str = "生成起诉状模板中的签名盖章信息占位符"
    category: str = "litigation"
    placeholder_keys: ClassVar = [LitigationPlaceholderKeys.COMPLAINT_SIGNATURE]

    def __init__(self) -> None:
        from .case_details_accessor import LitigationCaseDetailsAccessor
        from .party_formatter import PartyFormatter

        self.formatter = PartyFormatter()
        self.case_details_accessor = LitigationCaseDetailsAccessor()

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        case_id = context_data.get("case_id") or getattr(context_data.get("case"), "id", None)
        if not case_id:
            return {}
        return {LitigationPlaceholderKeys.COMPLAINT_SIGNATURE: self.generate_signature_info(case_id)}

    def _format_date(self, case_id: int) -> str:
        """
        格式化日期为 YYYY年MM月DD日

        Args:
            case_id: 案件 ID

        Returns:
            str: 格式化后的日期

        Requirements: 3.1, 4.5, 4.6
        """
        return self.case_details_accessor.get_formatted_date(case_id=case_id)

    def generate_signature_info(self, case_id: int) -> str:
        """
        生成起诉状签名盖章信息

        Args:
            case_id: 案件 ID

        Returns:
            str: 格式化后的签名盖章信息

        Requirements: 3.1, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 8.3
        """
        from apps.core.models.enums import LegalStatus

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

        # 法律地位的中文映射
        legal_status_map = {LegalStatus.PLAINTIFF: "原告", LegalStatus.DEFENDANT: "被告", LegalStatus.THIRD: "第三人"}

        # 生成签名块
        signature_blocks: list[Any] = []

        for party_dict in parties:
            # 使用中文角色名
            role = legal_status_map.get(party_dict.get("legal_status"), party_dict.get("legal_status"))

            if self.formatter.is_natural_person_from_dict(party_dict):
                # 自然人签名格式
                name = party_dict.get("client_name") or ""
                signature_block = f"{role}（签名+指模）：{name}\n日期：{date_str}"
            else:
                # 法人签名格式
                company_name = party_dict.get("client_name") or ""
                legal_rep = party_dict.get("legal_representative") or ""
                signature_block = f"{role}（盖章）：{company_name}\n法定代表人（签名）：{legal_rep}\n日期：{date_str}"

            signature_blocks.append(signature_block)

        # 用空行分隔各签名块
        result = "\n\n".join(signature_blocks)

        logger.info("生成起诉状签名盖章信息成功: case_id=%s, 签名主体数=%s", case_id, len(signature_blocks))

        return result
