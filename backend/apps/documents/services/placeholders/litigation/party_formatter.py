"""
当事人格式化工具类

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 9.3, 9.4, 9.5, 9.6
"""

import logging
from typing import Any

from apps.core.utils.id_card_utils import IdCardUtils

logger = logging.getLogger(__name__)


class PartyFormatter:
    """当事人格式化工具类"""

    def is_natural_person(self, party: Any) -> Any:
        """
        判断是否为自然人

        Args:
            party: CaseParty 实例

        Returns:
            bool: 是否为自然人

        Requirements: 9.3
        """
        if not party or not party.client:
            return False

        return party.client.client_type == "natural"

    def is_natural_person_from_dict(self, party_dict: dict[str, Any]) -> bool:
        """
        判断是否为自然人(从字典数据)

        Args:
            party_dict: 当事人字典数据(来自 get_case_with_details_internal)

        Returns:
            bool: 是否为自然人

        Requirements: 3.1, 9.3
        """
        if not party_dict:
            return False

        return party_dict.get("client_type") == "natural"

    def get_role_label(self, legal_status: str, index: int, total: int) -> str:
        """
        生成角色标签

        Args:
            legal_status: 法律地位(原告/被告/第三人)
            index: 序号(从0开始)
            total: 该角色总数

        Returns:
            str: 角色标签

        Requirements: 2.1, 2.2, 2.3
        """
        if total == 1:
            return legal_status

        # 中文数字映射
        chinese_numbers = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]

        if index < len(chinese_numbers):
            return f"{legal_status}{chinese_numbers[index]}"
        else:
            # 超过10个使用阿拉伯数字
            return f"{legal_status}{index + 1}"

    def _format_natural_person_info(
        self,
        role: str,
        name: str,
        id_number: str,
        address: str,
        phone: str = "",
    ) -> str:
        id_info = IdCardUtils.parse_id_card_info(id_number)

        if id_info.gender and id_info.birth_date:
            lines = [
                f"{role}：{name}，{id_info.gender}，{id_info.birth_date}出生",
                f"地址：{address}",
                f"身份证号码：{id_number}",
            ]
        else:
            lines = [
                f"{role}：{name}",
                f"地址：{address}",
                f"身份证号码：{id_number}",
            ]
        if phone:
            lines.append(f"联系电话：{phone}")

        return "\n".join(lines)

    def _format_legal_entity_info(
        self,
        role: str,
        company_name: str,
        address: str,
        unified_social_credit_code: str,
        legal_representative: str,
        contact_phone: str,
    ) -> str:
        lines = [
            f"{role}：{company_name}",
            f"地址：{address}",
            f"统一社会信用代码：{unified_social_credit_code}",
            f"法定代表人：{legal_representative}",
            f"联系电话：{contact_phone}",
        ]
        return "\n".join(lines)

    def format_natural_person(self, role: str, party: Any) -> str:
        """
        格式化自然人信息

        Args:
            role: 角色标签(如"原告"、"被告一")
            party: CaseParty 实例

        Returns:
            str: 格式化后的自然人信息

        Requirements: 2.4, 9.4, 9.6
        """
        if not party or not party.client:
            return f"{role}：\n"

        client = party.client
        return self._format_natural_person_info(
            role=role,
            name=client.name or "",
            id_number=client.id_number or "",
            address=client.address or "",
            phone=getattr(client, "phone", "") or "",
        )

    def format_legal_entity(self, role: str, party: Any) -> str:
        """
        格式化法人信息

        Args:
            role: 角色标签(如"原告"、"被告一")
            party: CaseParty 实例

        Returns:
            str: 格式化后的法人信息

        Requirements: 2.5, 9.5, 9.6
        """
        if not party or not party.client:
            return f"{role}：\n"

        client = party.client
        return self._format_legal_entity_info(
            role=role,
            company_name=client.name or "",
            address=client.address or "",
            unified_social_credit_code=client.id_number or "",
            legal_representative=getattr(client, "legal_representative", "") or "",
            contact_phone=getattr(client, "phone", "") or "",
        )

    def format_natural_person_from_dict(self, role: str, party_dict: dict[str, Any]) -> str:
        """
        格式化自然人信息(从字典数据)

        Args:
            role: 角色标签(如"原告"、"被告一")
            party_dict: 当事人字典数据(来自 get_case_with_details_internal)

        Returns:
            str: 格式化后的自然人信息

        Requirements: 2.4, 3.1, 9.4, 9.6
        """
        if not party_dict:
            return f"{role}：\n"

        return self._format_natural_person_info(
            role=role,
            name=party_dict.get("client_name") or "",
            id_number=party_dict.get("id_number") or "",
            address=party_dict.get("address") or "",
            phone=party_dict.get("phone") or "",
        )

    def format_legal_entity_from_dict(self, role: str, party_dict: dict[str, Any]) -> str:
        """
        格式化法人信息(从字典数据)

        Args:
            role: 角色标签(如"原告"、"被告一")
            party_dict: 当事人字典数据(来自 get_case_with_details_internal)

        Returns:
            str: 格式化后的法人信息

        Requirements: 2.5, 3.1, 9.5, 9.6
        """
        if not party_dict:
            return f"{role}：\n"

        return self._format_legal_entity_info(
            role=role,
            company_name=party_dict.get("client_name") or "",
            address=party_dict.get("address") or "",
            unified_social_credit_code=party_dict.get("id_number") or "",
            legal_representative=party_dict.get("legal_representative") or "",
            contact_phone=party_dict.get("phone") or "",
        )
