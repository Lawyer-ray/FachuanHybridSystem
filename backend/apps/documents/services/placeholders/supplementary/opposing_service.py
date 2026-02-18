"""
补充协议对方当事人信息占位符服务

提供补充协议中对方当事人主体信息条款生成功能.
"""

import logging
from typing import Any, ClassVar

from apps.contracts.models import PartyRole
from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class SupplementaryAgreementOpposingService(BasePlaceholderService):
    """补充协议对方当事人信息服务"""

    name: str = "supplementary_agreement_opposing_service"
    display_name: str = "补充协议对方当事人信息服务"
    description: str = "生成补充协议中的对方当事人主体信息条款"
    category: str = "supplementary_agreement"
    placeholder_keys: ClassVar = [
        "补充协议对方当事人主体信息条款",  # 新增对方当事人条款或空
    ]

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        生成对方当事人相关占位符

        Args:
            context_data: 包含 supplementary_agreement 等数据的上下文

        Returns:
            包含对方当事人占位符的字典
        """
        result: dict[str, Any] = {}

        supplementary_agreement = context_data.get("supplementary_agreement")

        if supplementary_agreement:
            # 获取对方当事人列表
            opposing_parties = self._get_opposing_parties(supplementary_agreement)

            # 生成对方当事人主体信息条款
            result["补充协议对方当事人主体信息条款"] = self.format_opposing_party_clause(opposing_parties)
        else:
            result["补充协议对方当事人主体信息条款"] = ""

        return result

    def _get_opposing_parties(self, supplementary_agreement: Any) -> list[Any]:
        """
        获取补充协议中的对方当事人列表

        Args:
            supplementary_agreement: SupplementaryAgreement 实例

        Returns:
            对方当事人 Client 实例列表
        """
        try:
            opposing_parties: list[Any] = []
            for party in supplementary_agreement.parties.all():
                if party.role == PartyRole.OPPOSING:
                    opposing_parties.append(party.client)
            return opposing_parties
        except Exception:
            logger.exception(
                "get_supplementary_agreement_opposing_parties_failed",
                extra={"supplementary_agreement_id": getattr(supplementary_agreement, "id", None)},
            )
            raise

    def _strip_whitespace(self, text: str) -> str:
        """
        剔除字符串中的所有空格(包括普通空格和特殊空白字符)

        Args:
            text: 输入字符串

        Returns:
            去除空格后的字符串
        """
        import re

        if not text:
            return ""
        cleaned = str(text)
        cleaned = cleaned.translate(
            {
                ord("\u200b"): None,  # zero width space
                ord("\u200c"): None,  # zero width non-joiner
                ord("\u200d"): None,  # zero width joiner
                ord("\ufeff"): None,  # BOM
                ord("\u2060"): None,  # word joiner
                ord("\u200e"): None,  # LRM
                ord("\u200f"): None,  # RLM
            }
        )
        return re.sub(r"\s+", "", cleaned)

    def format_opposing_party_clause(self, opposing_parties: list[Any]) -> str:
        """
        生成对方当事人主体信息条款

        如果没有对方当事人,返回空字符串(删除整段)
        如果有对方当事人,生成详细信息

        格式:
        - 自然人:补充对方当事人信息:姓名:XXX,身份证号码:XXX(签名+指模)
        - 非自然人:补充对方当事人信息:名称:XXX,统一社会信用代码XXX(盖章)

        Args:
            opposing_parties: 对方当事人列表

        Returns:
            对方当事人主体信息条款或空字符串
        """
        if not opposing_parties:
            # 没有对方当事人,返回空字符串(删除整段)
            return ""

        # 生成对方当事人详细信息
        parts: list[Any] = []

        for client in opposing_parties:
            try:
                # 获取并清理名称和证件号
                name = self._strip_whitespace(client.name) if client.name else ""
                id_number = self._strip_whitespace(getattr(client, "id_number", "") or "")

                if hasattr(client, "client_type") and client.client_type == "natural":
                    # 自然人格式:姓名:XXX,身份证号码:XXX(签名+指模)
                    parts.append(f"姓名:{name},身份证号码:{id_number}(签名+指模)")
                else:
                    # 法人或非法人组织格式:名称:XXX,统一社会信用代码XXX
                    parts.append(f"名称:{name},统一社会信用代码{id_number}")

            except Exception as e:
                logger.warning(f"格式化对方当事人信息失败: {e}", extra={"client_id": getattr(client, "id", None)})
                # 提供基本格式,默认为法人
                name = self._strip_whitespace(client.name) if client.name else ""
                parts.append(f"名称:{name}")

        # 用分号连接,最后加句号
        return "补充对方当事人信息:" + ";".join(parts) + "."
