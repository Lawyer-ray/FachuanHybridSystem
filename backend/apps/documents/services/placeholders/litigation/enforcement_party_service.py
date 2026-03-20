"""
强制执行申请书当事人信息服务

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 3.1, 8.3, 9.1, 9.2
"""

import logging
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry
from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class EnforcementApplicantPartyService(BasePlaceholderService):
    """强制执行申请书申请人信息服务"""

    name: str = "enforcement_applicant_party_service"
    display_name: str = "诉讼文书-强制执行申请书申请人信息"
    description: str = "生成强制执行申请书模板中的申请人信息占位符"
    category: str = "litigation"
    placeholder_keys: ClassVar = [LitigationPlaceholderKeys.ENFORCEMENT_APPLICANT_PARTY]

    def __init__(self) -> None:
        from .case_details_accessor import LitigationCaseDetailsAccessor
        from .party_formatter import PartyFormatter

        self.formatter = PartyFormatter()
        self.case_details_accessor = LitigationCaseDetailsAccessor()

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        case_id = context_data.get("case_id") or getattr(context_data.get("case"), "id", None)
        if not case_id:
            return {}
        return {LitigationPlaceholderKeys.ENFORCEMENT_APPLICANT_PARTY: self.generate_applicant_info(case_id)}

    def generate_applicant_info(self, case_id: int) -> str:
        """
        生成强制执行申请书申请人信息（支持多个申请人）

        Args:
            case_id: 案件 ID

        Returns:
            str: 格式化后的申请人信息，多个申请人用空行分隔

        Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 8.3, 9.1, 9.2
        """
        from apps.core.enums import LegalStatus

        case_parties = self.case_details_accessor.get_case_parties(case_id=case_id)

        # 筛选原告或申请人作为申请人
        # 支持起诉阶段 (plaintiff) 和执行阶段 (applicant)
        applicants = [
            p for p in case_parties
            if p.get("legal_status") in (LegalStatus.PLAINTIFF, LegalStatus.APPLICANT)
        ]

        if not applicants:
            logger.warning("未找到申请人信息: case_id=%s", case_id)
            return "申请人：\n"

        # 格式化所有申请人
        party_blocks: list[str] = []
        for idx, party_dict in enumerate(applicants):
            if len(applicants) > 1:
                role_label = f"申请人{chr(ord('一') + idx)}"  # 申请人一、申请人二...
            else:
                role_label = "申请人"

            if self.formatter.is_natural_person_from_dict(party_dict):
                party_info = self.formatter.format_natural_person_from_dict(role_label, party_dict)
            else:
                party_info = self.formatter.format_legal_entity_from_dict(role_label, party_dict)
            party_blocks.append(party_info)

        result = "\n\n".join(party_blocks)
        logger.info("生成强制执行申请书申请人信息成功: case_id=%s, 申请人数=%s", case_id, len(applicants))
        return result


@PlaceholderRegistry.register
class EnforcementRespondentPartyService(BasePlaceholderService):
    """强制执行申请书被申请人信息服务"""

    name: str = "enforcement_respondent_party_service"
    display_name: str = "诉讼文书-强制执行申请书被申请人信息"
    description: str = "生成强制执行申请书模板中的被申请人信息占位符"
    category: str = "litigation"
    placeholder_keys: ClassVar = [LitigationPlaceholderKeys.ENFORCEMENT_RESPONDENT_PARTY]

    def __init__(self) -> None:
        from .case_details_accessor import LitigationCaseDetailsAccessor
        from .party_formatter import PartyFormatter

        self.formatter = PartyFormatter()
        self.case_details_accessor = LitigationCaseDetailsAccessor()

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        case_id = context_data.get("case_id") or getattr(context_data.get("case"), "id", None)
        if not case_id:
            return {}
        return {LitigationPlaceholderKeys.ENFORCEMENT_RESPONDENT_PARTY: self.generate_respondent_info(case_id)}

    def generate_respondent_info(self, case_id: int) -> str:
        """
        生成强制执行申请书被申请人信息（支持多个被申请人）

        Args:
            case_id: 案件 ID

        Returns:
            str: 格式化后的被申请人信息，多个被申请人用空行分隔

        Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 8.3, 9.1, 9.2
        """
        from apps.core.enums import LegalStatus

        case_parties = self.case_details_accessor.get_case_parties(case_id=case_id)

        # 筛选被告或被申请人作为被申请人
        # 支持起诉阶段 (defendant) 和执行阶段 (respondent)
        respondents = [
            p for p in case_parties
            if p.get("legal_status") in (LegalStatus.DEFENDANT, LegalStatus.RESPONDENT)
        ]

        if not respondents:
            logger.warning("未找到被申请人信息: case_id=%s", case_id)
            return "被申请人：\n"

        # 格式化所有被申请人
        party_blocks: list[str] = []
        for idx, party_dict in enumerate(respondents):
            if len(respondents) > 1:
                role_label = f"被申请人{chr(ord('一') + idx)}"  # 被申请人一、被申请人二...
            else:
                role_label = "被申请人"

            if self.formatter.is_natural_person_from_dict(party_dict):
                party_info = self.formatter.format_natural_person_from_dict(role_label, party_dict)
            else:
                party_info = self.formatter.format_legal_entity_from_dict(role_label, party_dict)
            party_blocks.append(party_info)

        result = "\n\n".join(party_blocks)
        logger.info("生成强制执行申请书被申请人信息成功: case_id=%s, 被申请人数=%s", case_id, len(respondents))
        return result


@PlaceholderRegistry.register
class EnforcementRespondentNameService(BasePlaceholderService):
    """强制执行申请书被申请人名称服务"""

    name: str = "enforcement_respondent_name_service"
    display_name: str = "诉讼文书-强制执行申请书被申请人名称"
    description: str = "生成强制执行申请书模板中的被申请人名称占位符"
    category: str = "litigation"
    placeholder_keys: ClassVar = [LitigationPlaceholderKeys.ENFORCEMENT_RESPONDENT_NAME]

    def __init__(self) -> None:
        from .case_details_accessor import LitigationCaseDetailsAccessor

        self.case_details_accessor = LitigationCaseDetailsAccessor()

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        case_id = context_data.get("case_id") or getattr(context_data.get("case"), "id", None)
        if not case_id:
            return {}
        return {LitigationPlaceholderKeys.ENFORCEMENT_RESPONDENT_NAME: self.get_respondent_names(case_id)}

    def get_respondent_names(self, case_id: int) -> str:
        """
        获取被申请人名称（支持多个，用顿号分隔）

        Args:
            case_id: 案件 ID

        Returns:
            str: 被申请人名称，多个用"、"分隔
        """
        from apps.core.enums import LegalStatus

        case_parties = self.case_details_accessor.get_case_parties(case_id=case_id)

        # 筛选被告或被申请人
        respondents = [
            p for p in case_parties
            if p.get("legal_status") in (LegalStatus.DEFENDANT, LegalStatus.RESPONDENT)
        ]

        if not respondents:
            logger.warning("未找到被申请人信息: case_id=%s", case_id)
            return ""

        # 获取所有被申请人名称
        names = [p.get("client_name", "") for p in respondents if p.get("client_name")]
        result = "、".join(names)

        logger.info("获取被申请人名称: case_id=%s, names=%s", case_id, result)
        return result
