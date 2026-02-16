"""
答辩状当事人信息服务

Requirements: 3.1, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 8.3
"""

import logging
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry
from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class DefensePartyService(BasePlaceholderService):
    """答辩状当事人信息服务"""

    name: str = "litigation_defense_party_service"
    display_name: str = "诉讼文书-答辩状当事人信息"
    description: str = "生成答辩状模板中的当事人信息占位符"
    category: str = "litigation"
    placeholder_keys: ClassVar = [LitigationPlaceholderKeys.DEFENSE_PARTY]

    def __init__(self) -> None:
        from .case_details_accessor import LitigationCaseDetailsAccessor
        from .party_formatter import PartyFormatter

        self.formatter = PartyFormatter()
        self.case_details_accessor = LitigationCaseDetailsAccessor()

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        case_id = context_data.get("case_id") or getattr(context_data.get("case"), "id", None)
        if not case_id:
            return {}
        return {LitigationPlaceholderKeys.DEFENSE_PARTY: self.generate_party_info(case_id)}

    def _determine_scenario_from_dict(self, parties: list[dict[str, Any]]) -> str:
        """
        确定答辩状场景(从字典数据)

        Args:
            parties: 当事人字典列表

        Returns:
            str: 场景类型 (defendant_only, third_party_only, both)

        Requirements: 3.1, 5.1, 5.2, 5.3
        """
        from apps.core.enums import LegalStatus

        # 识别我方当事人的角色
        has_our_defendant = False
        has_our_third_party = False

        for party in parties:
            is_our = party.get("is_our_client", False)
            legal_status = party.get("legal_status")
            if is_our:
                if legal_status == LegalStatus.DEFENDANT:
                    has_our_defendant = True
                elif legal_status == LegalStatus.THIRD:
                    has_our_third_party = True

        # 确定场景
        if has_our_defendant and has_our_third_party:
            return "both"
        elif has_our_defendant:
            return "defendant_only"
        elif has_our_third_party:
            return "third_party_only"
        else:
            # 默认场景
            return "defendant_only"

    def _map_roles_from_dict(self, parties: list[dict[str, Any]], scenario: str) -> dict[str, list[dict[str, Any]]]:
        """
        根据场景映射角色(从字典数据)

        Args:
            parties: 当事人字典列表
            scenario: 场景类型

        Returns:
            Dict[str, List[dict]]: 映射后的角色字典

        Requirements: 3.1, 5.1, 5.2, 5.3
        """
        from apps.core.enums import LegalStatus

        role_map = {"答辩人": [], "被答辩人": [], "第三人": [], "被告": []}  # type: ignore[var-annotated]

        scenario_handlers = {
            "defendant_only": self._map_defendant_only,
            "third_party_only": self._map_third_party_only,
            "both": self._map_both,
        }
        handler = scenario_handlers.get(scenario, self._map_defendant_only)

        for party in parties:
            handler(party, role_map, LegalStatus)

        return role_map

    def _map_defendant_only(self, party: dict[str, Any], role_map: dict[str, Any], LegalStatus: Any) -> None:
        is_our = party.get("is_our_client", False)
        legal_status = party.get("legal_status")
        if is_our and legal_status == LegalStatus.DEFENDANT:
            role_map["答辩人"].append(party)
        elif legal_status == LegalStatus.PLAINTIFF:
            role_map["被答辩人"].append(party)
        elif legal_status == LegalStatus.THIRD:
            role_map["第三人"].append(party)

    def _map_third_party_only(self, party: dict[str, Any], role_map: dict[str, Any], LegalStatus: Any) -> None:
        is_our = party.get("is_our_client", False)
        legal_status = party.get("legal_status")
        if is_our and legal_status == LegalStatus.THIRD:
            role_map["答辩人"].append(party)
        elif legal_status == LegalStatus.PLAINTIFF:
            role_map["被答辩人"].append(party)
        elif legal_status == LegalStatus.DEFENDANT:
            role_map["被告"].append(party)

    def _map_both(self, party: dict[str, Any], role_map: dict[str, Any], LegalStatus: Any) -> None:
        is_our = party.get("is_our_client", False)
        legal_status = party.get("legal_status")
        if is_our and legal_status in [LegalStatus.DEFENDANT, LegalStatus.THIRD]:
            role_map["答辩人"].append(party)
        elif legal_status == LegalStatus.PLAINTIFF:
            role_map["被答辩人"].append(party)

    def generate_party_info(self, case_id: int) -> str:
        """
        生成答辩状当事人信息

        Args:
            case_id: 案件 ID

        Returns:
            str: 格式化后的当事人信息

        Requirements: 3.1, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 8.3
        """
        parties = self.case_details_accessor.get_case_parties(case_id=case_id)
        scenario = self._determine_scenario_from_dict(parties)
        role_map = self._map_roles_from_dict(parties, scenario)

        result_parts: list[str] = []
        self._format_respondents(result_parts, role_map["答辩人"], parties)
        self._format_plaintiffs(result_parts, role_map["被答辩人"])
        self._format_other_roles(result_parts, role_map)

        result = "\n\n".join(result_parts)
        logger.info(f"生成答辩状当事人信息成功: case_id={case_id}, 场景={scenario}, 当事人数={len(result_parts)}")
        return result

    def _format_respondents(
        self, result_parts: list[str], respondents: list[dict[str, Any]], parties: list[dict[str, Any]]
    ) -> None:
        """格式化答辩人信息"""
        from apps.core.enums import LegalStatus

        legal_status_map = {
            LegalStatus.PLAINTIFF: "原告",
            LegalStatus.DEFENDANT: "被告",
            LegalStatus.THIRD: "第三人",
        }
        total = len(respondents)

        for index, party_dict in enumerate(respondents):
            respondent_label = self._numbered_label("答辩人", index, total)
            original_role = party_dict.get("legal_status")
            chinese_role = legal_status_map.get(original_role, original_role)  # type: ignore[arg-type, arg-type]

            if total > 1:
                original_parties = [p for p in parties if p.get("legal_status") == original_role]
                original_index = original_parties.index(party_dict)
                original_total = len(original_parties)
                original_label = self.formatter.get_role_label(chinese_role, original_index, original_total)
                role_with_original = f"{respondent_label}({original_label})"
            else:
                role_with_original = f"{respondent_label}({chinese_role})"

            result_parts.append(self._format_party_block(role_with_original, party_dict))

    def _format_plaintiffs(self, result_parts: list[str], plaintiffs: list[dict[str, Any]]) -> None:
        """格式化被答辩人信息"""
        chinese_numbers = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
        total = len(plaintiffs)

        for index, party_dict in enumerate(plaintiffs):
            plaintiff_label = self._numbered_label("被答辩人", index, total)
            if total > 1:
                num = chinese_numbers[index] if index < len(chinese_numbers) else str(index + 1)
                role_with_original = f"{plaintiff_label}(原告{num})"
            else:
                role_with_original = f"{plaintiff_label}(原告)"

            result_parts.append(self._format_party_block(role_with_original, party_dict))

    def _format_other_roles(self, result_parts: list[str], role_map: dict[str, list[dict[str, Any]]]) -> None:
        """格式化第三人、被告等其他角色"""
        for role_name in ["第三人", "被告"]:
            for party_dict in role_map[role_name]:
                result_parts.append(self._format_party_block(role_name, party_dict))

    def _format_party_block(self, role_label: str, party_dict: dict[str, Any]) -> str:
        """格式化单个当事人信息块"""
        if self.formatter.is_natural_person_from_dict(party_dict):
            name = party_dict.get("client_name") or ""
            id_number = party_dict.get("id_number") or ""
            address = party_dict.get("address") or ""
            return f"{role_label}:{name}\n身份证号码:{id_number}\n地址:{address}"

        company_name = party_dict.get("client_name") or ""
        address = party_dict.get("address") or ""
        credit_code = party_dict.get("id_number") or ""
        legal_rep = party_dict.get("legal_representative") or ""
        phone = party_dict.get("phone") or ""

        # 答辩人格式:信用代码在前;被答辩人/其他格式:地址在前
        if role_label.startswith("答辩人"):
            return (
                f"{role_label}:{company_name}\n统一社会信用代码:{credit_code}\n法定代表人:{legal_rep}\n地址:{address}"
            )
        return (
            f"{role_label}:{company_name}\n"
            f"地址:{address}\n"
            f"统一社会信用代码:{credit_code}\n"
            f"法定代表人:{legal_rep}\n"
            f"{'电话' if role_label.startswith('被答辩人') else '联系电话'}:{phone}"
        )

    def _numbered_label(self, base: str, index: int, total: int) -> str:
        """生成带序号的标签"""
        if total == 1:
            return base
        chinese_numbers = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
        if index < len(chinese_numbers):
            return f"{base}{chinese_numbers[index]}"
        return f"{base}{index + 1}"
