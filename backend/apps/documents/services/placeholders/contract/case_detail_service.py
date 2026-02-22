"""
案件详情占位符服务

生成案件详细信息列表,包括对方当事人、案由、审理机关和案件金额.
"""

import logging
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class CaseDetailService(BasePlaceholderService):
    """案件详情服务"""

    name: str = "case_detail_service"
    display_name: str = "案件详情服务"
    description: str = "生成案件详细信息列表"
    category: str = "contract"
    placeholder_keys: ClassVar = ["案件详情"]

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        生成案件详情占位符

        Args:
            context_data: 包含 contract 的上下文字典

        Returns:
            {"案件详情": "格式化的案件详情字符串"}
        """
        try:
            contract = context_data.get("contract")
            if not contract:
                logger.warning("合同对象为空")
                return {"案件详情": ""}
            try:
                cases = list(
                    contract.cases.select_related("contract")
                    .prefetch_related("parties__client", "supervising_authorities")
                    .all()
                )
            except AttributeError:
                logger.warning("合同对象没有 cases 属性")
                cases: list[Any] = [] # type: ignore
            if not cases:
                return {"案件详情": ""}
            else:
                result = self._format_with_cases(cases)
            return {"案件详情": result}
        except Exception as e:
            logger.warning(
                "生成案件详情占位符失败: %s", e,
                extra={"contract_id": getattr(context_data.get("contract"), "id", None)},
                exc_info=True,
            )
            return {"案件详情": ""}

    def _format_without_cases(self, contract: Any) -> str:
        """
        格式化无案件情况的输出

        Args:
            contract: Contract 实例

        Returns:
            格式化的基础案件详情字符串
        """
        try:
            opposing_parties: list[Any] = []
            for cp in contract.contract_parties.all():
                if cp.role == "OPPOSING":
                    opposing_parties.append(cp.client)
            opposing_names = "、".join([c.name for c in opposing_parties if hasattr(c, "name") and c.name])
            lines = [f"对方当事人名称:{opposing_names}", "案由:", "审理机关:", "案件金额:"]
            return "\n".join(lines)
        except Exception as e:
            logger.warning("格式化无案件详情失败: %s", e, extra={"contract_id": getattr(contract, "id", None)})
            return "对方当事人名称:\n案由:\n审理机关:\n案件金额:"

    def _format_with_cases(self, cases: list[Any]) -> str:
        """
        格式化有案件情况的输出

        Args:
            cases: 案件列表

        Returns:
            格式化的案件详情字符串
        """
        try:
            if not cases:
                return ""
            case_details: list[Any] = []
            for index, case in enumerate(cases, start=1):
                detail = self._format_single_case_detail(index, case)
                if detail:
                    case_details.append(detail)
            return "\x07".join(case_details)
        except Exception as e:
            logger.warning("格式化有案件详情失败: %s", e)
            return ""

    def _format_single_case_detail(self, case_index: int, case: Any) -> str:
        """
        格式化单个案件的详情

        Args:
            case_index: 案件序号(从1开始)
            case: Case 实例

        Returns:
            格式化的案件详情字符串
        """
        try:
            title = self._format_case_number(case_index)
            opposing_parties = self._extract_opposing_parties_from_case(case)
            opposing_names = "、".join(opposing_parties) if opposing_parties else ""
            cause = self._extract_cause_of_action(case)
            authority = self._extract_supervising_authority(case)
            amount = self._format_target_amount(case)
            lines = [
                title,
                f"\u3000\u3000\u3000\u3000对方当事人名称:{opposing_names}",
                f"\u3000\u3000\u3000\u3000案由:{cause}",
                f"\u3000\u3000\u3000\u3000审理机关:{authority}",
                f"\u3000\u3000\u3000\u3000案件金额:{amount}",
            ]
            return "\n".join(lines)
        except Exception as e:
            logger.warning("格式化案件详情失败: %s", e, extra={"case_id": getattr(case, "id", None)})
            return ""

    def _format_case_number(self, num: int) -> str:
        """
        格式化案件序号(案件一、案件二等)

        Args:
            num: 案件序号

        Returns:
            中文格式的案件标题
        """
        try:
            chinese_numbers = {
                1: "一",
                2: "二",
                3: "三",
                4: "四",
                5: "五",
                6: "六",
                7: "七",
                8: "八",
                9: "九",
                10: "十",
            }
            chinese_num = chinese_numbers.get(num, str(num))
            return f"案件{chinese_num}:"
        except Exception as e:
            logger.warning("格式化案件序号失败: %s", e, extra={"num": num})
            return "案件:"

    def _extract_opposing_parties_from_case(self, case: Any) -> list[str]:
        """
        从案件中提取对方当事人名称列表

        Args:
            case: Case 实例

        Returns:
            对方当事人名称列表
        """
        try:
            from apps.core.enums import LegalStatus

            our_statuses = {
                LegalStatus.PLAINTIFF,
                LegalStatus.APPLICANT,
                LegalStatus.APPELLANT,
                LegalStatus.ORIGINAL_PLAINTIFF,
            }
            opposing_names: list[Any] = []
            for party in case.parties.all():
                if party.legal_status not in our_statuses and hasattr(party.client, "name") and party.client.name:
                    opposing_names.append(party.client.name)
            return opposing_names
        except Exception:
            logger.exception("extract_case_opposing_parties_failed", extra={"case_id": getattr(case, "id", None)})
            raise

    def _extract_cause_of_action(self, case: Any) -> Any:
        """
        提取并清理案由

        Args:
            case: Case 实例

        Returns:
            清理后的案由字符串
        """
        try:
            cause = getattr(case, "cause_of_action", None)
            if not cause:
                return ""
            if "-" in cause:
                return cause.split("-")[0].strip()
            return cause.strip()
        except Exception as e:
            logger.warning("提取案由失败: %s", e, extra={"case_id": getattr(case, "id", None)})
            return ""

    def _extract_supervising_authority(self, case: Any) -> str:
        """
        提取审理机关/仲裁机构

        Args:
            case: Case 实例

        Returns:
            审理机关名称
        """
        try:
            from apps.core.enums import AuthorityType

            for authority in case.supervising_authorities.all():
                if authority.authority_type == AuthorityType.TRIAL:
                    return authority.name or ""
            return ""
        except Exception as e:
            logger.warning("提取审理机关失败: %s", e, extra={"case_id": getattr(case, "id", None)})
            return ""

    def _format_target_amount(self, case: Any) -> str:
        """
        格式化案件金额

        Args:
            case: Case 实例

        Returns:
            格式化的金额字符串
        """
        try:
            amount = getattr(case, "target_amount", None)
            if amount is None:
                return ""
            return f"{amount:.2f}元"
        except Exception as e:
            logger.warning("格式化案件金额失败: %s", e, extra={"case_id": getattr(case, "id", None)})
            return ""
