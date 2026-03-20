"""
强制执行申请书签名盖章信息服务

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 8.3
"""

import logging
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry
from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys

logger = logging.getLogger(__name__)


class EnforcementSignatureKeys:
    """强制执行申请书签名盖章占位符键"""
    ENFORCEMENT_SIGNATURE = "强制执行申请书签名盖章信息"
    ENFORCEMENT_SIGNATURE_PARTY = "强制执行申请书申请人签章"


@PlaceholderRegistry.register
class EnforcementSignatureService(BasePlaceholderService):
    """强制执行申请书签名盖章信息服务"""

    name: str = "enforcement_signature_service"
    display_name: str = "诉讼文书-强制执行申请书签名盖章信息"
    description: str = "生成强制执行申请书模板中的签名盖章信息占位符"
    category: str = "litigation"
    placeholder_keys: ClassVar = [EnforcementSignatureKeys.ENFORCEMENT_SIGNATURE]

    def __init__(self) -> None:
        from .case_details_accessor import LitigationCaseDetailsAccessor
        from .party_formatter import PartyFormatter

        self.formatter = PartyFormatter()
        self.case_details_accessor = LitigationCaseDetailsAccessor()

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        case_id = context_data.get("case_id") or getattr(context_data.get("case"), "id", None)
        if not case_id:
            return {}
        return {EnforcementSignatureKeys.ENFORCEMENT_SIGNATURE: self.generate_signature_info(case_id)}

    def _format_date(self, case_id: int) -> str:
        """格式化日期为 YYYY年MM月DD日"""
        return self.case_details_accessor.get_formatted_date(case_id=case_id)

    def generate_signature_info(self, case_id: int) -> str:
        """
        生成强制执行申请书签名盖章信息

        Args:
            case_id: 案件 ID

        Returns:
            str: 格式化后的签名盖章信息

        Requirements: 3.1, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 8.3
        """
        from apps.core.enums import LegalStatus

        case_parties = self.case_details_accessor.get_case_parties(case_id=case_id)

        # 筛选申请人（支持 plaintiff 和 applicant）
        parties = [
            p
            for p in case_parties
            if p.get("legal_status") in [LegalStatus.PLAINTIFF, LegalStatus.APPLICANT]
        ]

        if not parties:
            logger.warning("未找到申请人签名主体: case_id=%s", case_id)
            return ""

        # 格式化日期
        date_str = self._format_date(case_id)

        # 生成签名块
        signature_blocks: list[str] = []

        for party_dict in parties:
            if self.formatter.is_natural_person_from_dict(party_dict):
                # 自然人签名格式
                name = party_dict.get("client_name") or ""
                signature_block = f"申请人（签名+指模）：{name}\n日期：{date_str}"
            else:
                # 法人签名格式
                company_name = party_dict.get("client_name") or ""
                legal_rep = party_dict.get("legal_representative") or ""
                signature_block = f"申请人（盖章）：{company_name}\n法定代表人（签名）：{legal_rep}\n日期：{date_str}"

            signature_blocks.append(signature_block)

        # 用空行分隔各签名块
        result = "\n\n".join(signature_blocks)

        logger.info("生成强制执行申请书签名盖章信息成功: case_id=%s, 签名主体数=%s", case_id, len(signature_blocks))

        return result
