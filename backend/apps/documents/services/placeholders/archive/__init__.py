"""
归档占位符服务

提供归档文书所需的占位符生成,包括案件基本信息、合同信息、
日期信息和日志汇总等.
"""

import logging
from datetime import date
from typing import Any, ClassVar

from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class ArchivePlaceholderService(BasePlaceholderService):
    """归档文书占位符服务"""

    name: str = "archive_placeholder_service"
    display_name: str = "归档文书占位符服务"
    description: str = "提供归档文书所需的占位符(案件/合同/日期/日志信息)"
    category: str = "archive"
    placeholder_keys: ClassVar = [
        "主办律师姓名",
        "合同名称",
        "合同我方当事人名称",
        "合同对方当事人名称",
        "合同类型",
        "律所OA案件编号",
        "案件案号",
        "管辖法院",
        "归档日期",
        "生成日期",
    ]
    placeholder_metadata: ClassVar[dict[str, dict[str, Any]]] = {
        "主办律师姓名": {
            "display_name": "主办律师姓名",
            "description": "案件主办律师的真实姓名",
            "example_value": "房长波",
        },
        "合同名称": {
            "display_name": "合同名称",
            "description": "关联合同的名称",
            "example_value": "兴业银行诉升平百货金融借款合同纠纷",
        },
        "合同我方当事人名称": {
            "display_name": "合同我方当事人名称",
            "description": "合同中我方(委托方)当事人名称,顿号分隔",
            "example_value": "佛山市升平百货有限公司、陈达明",
        },
        "合同对方当事人名称": {
            "display_name": "合同对方当事人名称",
            "description": "合同中对方当事人名称,顿号分隔",
            "example_value": "广东顺德农村商业银行股份有限公司",
        },
        "合同类型": {
            "display_name": "合同类型",
            "description": "合同类型的中文显示名",
            "example_value": "民商事",
        },
        "律所OA案件编号": {
            "display_name": "律所OA案件编号",
            "description": "律所OA系统中的案件编号",
            "example_value": "2026GZM0077",
        },
        "案件案号": {
            "display_name": "案件案号",
            "description": "案件在法院的案号(首个生效案号)",
            "example_value": "(2026)粤0606民初1234号",
        },
        "管辖法院": {
            "display_name": "管辖法院",
            "description": "案件审理法院名称",
            "example_value": "佛山市顺德区人民法院",
        },
        "归档日期": {
            "display_name": "归档日期",
            "description": "归档操作日期(中文格式)",
            "example_value": "2026年04月19日",
        },
        "生成日期": {
            "display_name": "生成日期",
            "description": "文档生成日期(中文格式)",
            "example_value": "2026年04月19日",
        },
    }

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        生成归档文书占位符

        Args:
            context_data: 包含 case/contract 等数据的上下文

        Returns:
            包含归档占位符键值对的字典
        """
        result: dict[str, Any] = {}
        case = context_data.get("case")
        contract = context_data.get("contract")

        today_str = self._format_chinese_date(date.today())

        # {{归档日期}} / {{生成日期}} — 当前日期
        result["归档日期"] = today_str
        result["生成日期"] = today_str

        # 从 contract 获取合同相关字段
        if contract:
            result["合同名称"] = self._get_contract_name(contract)
            result["合同类型"] = self._get_contract_type(contract)
            result["合同我方当事人名称"] = self._get_our_party_names(contract)
            result["合同对方当事人名称"] = self._get_opposing_party_names(contract)
            result["律所OA案件编号"] = self._get_oa_case_number(contract)

        # 从 case 获取案件相关字段
        if case:
            result["主办律师姓名"] = self._get_lead_lawyer_name(case)
            result["案件案号"] = self._get_case_number(case)
            result["管辖法院"] = self._get_court_name(case)

        return result

    @staticmethod
    def _format_chinese_date(d: date) -> str:
        """格式化为中文日期"""
        return f"{d.year}年{d.month:02d}月{d.day:02d}日"

    @staticmethod
    def _get_contract_name(contract: Any) -> str:
        """获取合同名称"""
        return str(getattr(contract, "name", "") or "")

    @staticmethod
    def _get_contract_type(contract: Any) -> str:
        """获取合同类型中文显示名"""
        try:
            return contract.get_case_type_display() or ""
        except Exception:
            return str(getattr(contract, "case_type", "") or "")

    @staticmethod
    def _get_our_party_names(contract: Any) -> str:
        """获取合同我方当事人名称(顿号分隔)"""
        try:
            parties = contract.contract_parties.select_related("client").all()
        except Exception:
            logger.warning("获取合同当事人失败", extra={"contract_id": getattr(contract, "id", None)})
            return ""

        names: list[str] = []
        seen: set[str] = set()
        for party in parties:
            if getattr(party, "role", None) != "PRINCIPAL":
                continue
            client = getattr(party, "client", None)
            if not client:
                continue
            name = str(getattr(client, "name", "") or "").strip()
            if name and name not in seen:
                seen.add(name)
                names.append(name)
        return "、".join(names)

    @staticmethod
    def _get_opposing_party_names(contract: Any) -> str:
        """获取合同对方当事人名称(顿号分隔)"""
        try:
            parties = contract.contract_parties.select_related("client").all()
        except Exception:
            logger.warning("获取合同当事人失败", extra={"contract_id": getattr(contract, "id", None)})
            return ""

        names: list[str] = []
        seen: set[str] = set()
        for party in parties:
            if getattr(party, "role", None) != "OPPOSING":
                continue
            client = getattr(party, "client", None)
            if not client:
                continue
            name = str(getattr(client, "name", "") or "").strip()
            if name and name not in seen:
                seen.add(name)
                names.append(name)
        return "、".join(names)

    @staticmethod
    def _get_oa_case_number(contract: Any) -> str:
        """获取律所OA案件编号"""
        return str(getattr(contract, "law_firm_oa_case_number", "") or "")

    @staticmethod
    def _get_lead_lawyer_name(case: Any) -> str:
        """获取主办律师姓名(is_primary=True 的第一个)"""
        try:
            assignment = case.assignments.select_related("lawyer").filter(is_primary=True).first()
        except Exception:
            # 兼容旧字段: role='lead'
            try:
                assignment = case.assignments.select_related("lawyer").filter(role="lead").first()
            except Exception:
                assignment = None

        if not assignment:
            # 兜底: 取第一个指派
            try:
                assignment = case.assignments.select_related("lawyer").first()
            except Exception:
                logger.warning("获取主办律师失败", extra={"case_id": getattr(case, "id", None)})
                return ""

        if not assignment:
            return ""

        lawyer = getattr(assignment, "lawyer", None)
        if not lawyer:
            return ""

        return str(getattr(lawyer, "real_name", None) or getattr(lawyer, "username", "") or "")

    @staticmethod
    def _get_case_number(case: Any) -> str:
        """获取首个案件案号"""
        try:
            cn = case.case_numbers.filter(is_active=True).first()
            if cn:
                return str(getattr(cn, "number", "") or "")
        except Exception:
            logger.warning("获取案件案号失败", extra={"case_id": getattr(case, "id", None)})
        return ""

    @staticmethod
    def _get_court_name(case: Any) -> str:
        """获取管辖法院名称(审理机构)"""
        try:
            authorities = case.supervising_authorities.filter(authority_type="trial")
            names: list[str] = []
            seen: set[str] = set()
            for auth in authorities:
                name = str(getattr(auth, "name", "") or "").strip()
                if name and name not in seen:
                    seen.add(name)
                    names.append(name)
            return "、".join(names)
        except Exception:
            logger.warning("获取管辖法院失败", extra={"case_id": getattr(case, "id", None)})
            return ""
