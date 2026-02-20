"""Business logic services."""

import logging
import re
from typing import Any, ClassVar

from apps.core.enums import AuthorityType
from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class CaseCommonPlaceholderService(BasePlaceholderService):
    name: str = "case_common_placeholder_service"
    display_name: str = "案件通用信息"
    description: str = "提供案件文档通用占位符(当事人/律师/阶段/案由等)"
    category: str = "case"
    placeholder_keys: ClassVar = [
        "案件审理机构",
        "案件委托人名称",
        "案件律师姓名",
        "案件对方当事人名称",
        "案件案由",
        "案件当前阶段",
    ]
    placeholder_metadata: ClassVar = {
        "案件审理机构": {
            "display_name": "案件审理机构",
            "description": "主管机关中性质为“审理机构”的名称(多个用顿号分隔)",
            "example_value": "北京市朝阳区人民法院",
        },
        "案件委托人名称": {
            "display_name": "案件委托人名称",
            "description": "本案我方当事人名称(顿号分隔)",
            "example_value": "广东小王八实业科技有限公司、张三",
        },
        "案件律师姓名": {
            "display_name": "案件律师姓名",
            "description": "本案律师姓名(顿号分隔,主办在前)",
            "example_value": "李四、王五",
        },
        "案件对方当事人名称": {
            "display_name": "案件对方当事人名称",
            "description": "本案非我方当事人名称(顿号分隔)",
            "example_value": "谢大虾",
        },
        "案件案由": {
            "display_name": "案件案由",
            "description": "案件案由(去掉中划线及其后内容)",
            "example_value": "买卖合同纠纷",
        },
        "案件当前阶段": {
            "display_name": "案件当前阶段",
            "description": "案件当前阶段(显示值)",
            "example_value": "一审",
        },
    }

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        case = context_data.get("case")
        if not case:
            return dict.fromkeys(self.placeholder_keys, "")

        return {
            "案件审理机构": self._get_trial_authorities(case),
            "案件委托人名称": self._get_party_names(case, is_our_client=True),
            "案件律师姓名": self._get_lawyer_names(case),
            "案件对方当事人名称": self._get_party_names(case, is_our_client=False),
            "案件案由": self._format_cause_of_action(getattr(case, "cause_of_action", None)),
            "案件当前阶段": self._get_case_stage(case),
        }

    def _get_trial_authorities(self, case: Any) -> str:
        authorities: list[Any]
        try:
            authorities = list(case.supervising_authorities.all().order_by("id"))
        except Exception:
            logger.exception("操作失败")
            authorities = []

        names: list[str] = []
        seen = set()
        for authority in authorities:
            if getattr(authority, "authority_type", None) != AuthorityType.TRIAL:
                continue
            name = getattr(authority, "name", "") or ""
            if not name or name in seen:
                continue
            seen.add(name)
            names.append(name)
        return "、".join(names)

    def _get_party_names(self, case: Any, *, is_our_client: bool) -> str:
        parties: list[Any]
        try:
            parties = list(case.parties.select_related("client").all().order_by("id"))
        except Exception:
            logger.exception("操作失败")
            parties = []

        names: list[str] = []
        seen = set()
        for party in parties:
            client = getattr(party, "client", None)
            if not client:
                continue
            if bool(getattr(client, "is_our_client", False)) != bool(is_our_client):
                continue
            name = getattr(client, "name", "") or ""
            if not name or name in seen:
                continue
            seen.add(name)
            names.append(name)
        return "、".join(names)

    def _get_lawyer_names(self, case: Any) -> str:
        assignments: list[Any]
        try:
            assignments = list(case.assignments.select_related("lawyer").all().order_by("id"))
        except Exception:
            logger.exception("操作失败")
            assignments = []

        def sort_key(a) -> tuple[Any, ...]: # type: ignore
            return (0 if getattr(a, "is_primary", False) else 1, getattr(a, "id", 0))

        assignments = sorted(assignments, key=sort_key)

        names: list[str] = []
        seen = set()
        for assignment in assignments:
            lawyer = getattr(assignment, "lawyer", None)
            if not lawyer:
                continue
            name = getattr(lawyer, "real_name", None) or getattr(lawyer, "username", "") or ""
            if not name or name in seen:
                continue
            seen.add(name)
            names.append(name)
        return "、".join(names)

    def _format_cause_of_action(self, cause_of_action: Any) -> str:
        if not cause_of_action:
            return ""
        text = str(cause_of_action).strip()
        parts = re.split(r"\s*[-—–－]\s*", text, maxsplit=1)
        return (parts[0] or "").strip()

    def _get_case_stage(self, case: Any) -> str:
        if not getattr(case, "current_stage", None):
            return ""
        try:
            return case.get_current_stage_display() or ""
        except Exception:
            logger.exception("操作失败")

            return str(getattr(case, "current_stage", "") or "")
