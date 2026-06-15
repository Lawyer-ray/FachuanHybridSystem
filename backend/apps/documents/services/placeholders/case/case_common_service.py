"""Business logic services."""

import logging
import re
from datetime import date, datetime
from typing import Any, ClassVar

from django.utils import timezone

from apps.core.models.enums import AuthorityType, LegalStatus
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
        "案件我方当事人名称",
        "案件我方当事人ID",
        "案件我方当事人电话",
        "案件我方当事人地址",
        "我方当事人签名盖章信息",
        "律师签名信息",
        "案件律师姓名",
        "案件对方当事人名称",
        "案件对方当事人信息",
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
            "example_value": "某科技有限公司、张某",
        },
        "案件我方当事人名称": {
            "display_name": "案件我方当事人名称",
            "description": "本案我方当事人名称(顿号分隔)",
            "example_value": "某建材有限公司、李某、王某",
        },
        "案件我方当事人ID": {
            "display_name": "案件我方当事人ID",
            "description": "本案我方当事人证件号或统一社会信用代码(顿号分隔)",
            "example_value": "91***************B、44************014",
        },
        "案件我方当事人电话": {
            "display_name": "案件我方当事人电话",
            "description": "本案我方当事人联系电话(顿号分隔,全部为空则返回空)",
            "example_value": "138****8000、139****9000",
        },
        "案件我方当事人地址": {
            "display_name": "案件我方当事人地址",
            "description": "本案我方当事人名称与地址配对信息(全角分号分隔)",
            "example_value": "某建材有限公司：某省某市某区某路XX号；李某：某省某市某区某街XX号；王某：某省某市某区某小区XX栋XX室。",
        },
        "我方当事人签名盖章信息": {
            "display_name": "我方当事人签名盖章信息",
            "description": "按我方当事人的诉讼地位输出签名盖章块(自然人签名+指模,法人盖章+法定代表人签名)",
            "example_value": "被告（盖章）：某某有限公司\n法定代表人（签名）：张某\n日期：2026年4月6日",
        },
        "律师签名信息": {
            "display_name": "律师签名信息",
            "description": "按主办优先顺序输出代理律师签名块",
            "example_value": "代理律师（签名）：张律师\n日期：2026年4月6日",
        },
        "案件律师姓名": {
            "display_name": "案件律师姓名",
            "description": "本案律师姓名(顿号分隔,主办在前)",
            "example_value": "张律师、王律师",
        },
        "案件对方当事人名称": {
            "display_name": "案件对方当事人名称",
            "description": "本案非我方当事人名称(顿号分隔)",
            "example_value": "赵某",
        },
        "案件对方当事人信息": {
            "display_name": "案件对方当事人信息",
            "description": "本案非我方当事人完整信息(姓名、证件号、地址、电话等)",
            "example_value": "赵某\n身份证号码：44************1234\n地址：某省某市某区\n电话：13*********",
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

        our_party_names = self._get_party_names(case, is_our_client=True)
        return {
            "案件审理机构": self._get_trial_authorities(case),
            "案件委托人名称": our_party_names,
            "案件我方当事人名称": our_party_names,
            "案件我方当事人ID": self._get_party_values(case, is_our_client=True, field_name="id_number"),
            "案件我方当事人电话": self._get_party_values(case, is_our_client=True, field_name="phone"),
            "案件我方当事人地址": self._get_our_party_addresses(case),
            "我方当事人签名盖章信息": self._get_our_party_signature_info(case),
            "律师签名信息": self._get_lawyer_signature_info(case),
            "案件律师姓名": self._get_lawyer_names(case),
            "案件对方当事人名称": self._get_party_names(case, is_our_client=False),
            "案件对方当事人信息": self._get_opposing_party_info(case),
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

    def _get_party_values(self, case: Any, *, is_our_client: bool, field_name: str) -> str:
        parties: list[Any]
        try:
            parties = list(case.parties.select_related("client").all().order_by("id"))
        except Exception:
            logger.exception("操作失败")
            parties = []

        values: list[str] = []
        seen: set[str] = set()
        for party in parties:
            client = getattr(party, "client", None)
            if not client:
                continue
            if bool(getattr(client, "is_our_client", False)) != bool(is_our_client):
                continue
            value = str(getattr(client, field_name, "") or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            values.append(value)
        return "、".join(values)

    def _get_our_party_addresses(self, case: Any) -> str:
        parties: list[Any]
        try:
            parties = list(case.parties.select_related("client").all().order_by("id"))
        except Exception:
            logger.exception("操作失败")
            parties = []

        parts: list[str] = []
        seen: set[str] = set()
        for party in parties:
            client = getattr(party, "client", None)
            if not client or not bool(getattr(client, "is_our_client", False)):
                continue
            name = str(getattr(client, "name", "") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            address = str(getattr(client, "address", "") or "").strip()
            parts.append(f"{name}：{address}")

        if not parts:
            return ""
        return f"{'；'.join(parts)}。"

    def _get_our_party_signature_info(self, case: Any) -> str:
        parties: list[Any]
        try:
            parties = list(case.parties.select_related("client").all().order_by("id"))
        except Exception:
            logger.exception("操作失败")
            parties = []

        our_parties: list[Any] = []
        seen: set[str] = set()
        for party in parties:
            client = getattr(party, "client", None)
            if not client or not bool(getattr(client, "is_our_client", False)):
                continue
            name = str(getattr(client, "name", "") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            our_parties.append(party)

        if not our_parties:
            return ""

        date_str = self._get_signature_date(case)
        role_totals: dict[str, int] = {}
        for party in our_parties:
            role = self._resolve_party_role(party)
            role_totals[role] = role_totals.get(role, 0) + 1

        role_indexes: dict[str, int] = {}
        blocks: list[str] = []
        for party in our_parties:
            client = getattr(party, "client", None)
            if not client:
                continue
            role = self._resolve_party_role(party)
            role_indexes[role] = role_indexes.get(role, 0) + 1
            role_label = self._format_role_label(role, role_indexes[role], role_totals.get(role, 1))
            blocks.append(self._format_signature_block(role_label, client, date_str=date_str))

        return "\n\n".join([b for b in blocks if b.strip()])

    def _get_lawyer_signature_info(self, case: Any) -> str:
        lawyer_names = self._get_ordered_lawyer_names(case)
        if not lawyer_names:
            return ""

        date_str = self._get_signature_date(case)
        total = len(lawyer_names)
        blocks: list[str] = []
        for index, name in enumerate(lawyer_names, start=1):
            title = "代理律师" if total == 1 else f"代理律师{self._format_index_suffix(index)}"
            blocks.append(f"{title}（签名）：{name}\n日期：{date_str}")
        return "\n\n".join(blocks)

    def _get_signature_date(self, case: Any) -> str:
        value = getattr(case, "specified_date", None)
        date_obj = self._coerce_to_date(value) or timezone.localdate()
        return f"{date_obj.year}年{date_obj.month}月{date_obj.day}日"

    def _coerce_to_date(self, value: Any) -> date | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value).date()
            except ValueError:
                return None
        return None

    def _format_signature_block(self, role_label: str, client: Any, *, date_str: str) -> str:
        name = str(getattr(client, "name", "") or "").strip()
        client_type = str(getattr(client, "client_type", "") or "").strip()
        legal_representative = str(getattr(client, "legal_representative", "") or "").strip()

        if client_type == "natural":
            return f"{role_label}（签名+指模）：{name}\n日期：{date_str}"

        return f"{role_label}（盖章）：{name}\n法定代表人（签名）：{legal_representative}\n日期：{date_str}"

    def _get_opposing_party_info(self, case: Any) -> str:
        parties: list[Any]
        try:
            parties = list(case.parties.select_related("client").all().order_by("id"))
        except Exception:
            logger.exception("操作失败")
            parties = []

        opposing_parties: list[Any] = []
        seen: set[str] = set()
        for party in parties:
            client = getattr(party, "client", None)
            if not client or bool(getattr(client, "is_our_client", False)):
                continue
            name = str(getattr(client, "name", "") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            opposing_parties.append(party)

        role_totals: dict[str, int] = {}
        for party in opposing_parties:
            role = self._resolve_party_role(party)
            role_totals[role] = role_totals.get(role, 0) + 1

        role_indexes: dict[str, int] = {}
        blocks: list[str] = []
        for party in opposing_parties:
            role = self._resolve_party_role(party)
            role_indexes[role] = role_indexes.get(role, 0) + 1
            role_label = self._format_role_label(role, role_indexes[role], role_totals.get(role, 1))
            blocks.append(self._format_client_info(role_label, getattr(party, "client", None)))

        return "\n\n".join([b for b in blocks if b.strip()])

    def _resolve_party_role(self, party: Any) -> str:
        legal_status = getattr(party, "legal_status", None)
        role_map: dict[str, str] = {
            LegalStatus.PLAINTIFF: "原告",
            LegalStatus.DEFENDANT: "被告",
            LegalStatus.THIRD: "第三人",
            LegalStatus.APPELLANT: "上诉人",
            LegalStatus.APPELLEE: "被上诉人",
        }
        if legal_status in role_map:
            return role_map[legal_status]
        try:
            display = str(party.get_legal_status_display() or "").strip()
        except Exception:
            logger.exception("操作失败")
            display = ""
        return display or "当事人"

    def _format_role_label(self, role: str, index: int, total: int) -> str:
        if total <= 1:
            return role
        return f"{role}{self._format_index_suffix(index)}"

    def _format_index_suffix(self, index: int) -> str:
        chinese_numbers = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
        if 1 <= index <= len(chinese_numbers):
            return chinese_numbers[index - 1]
        return str(index)

    def _format_client_info(self, role_label: str, client: Any) -> str:
        if not client:
            return f"{role_label}："

        name = str(getattr(client, "name", "") or "").strip()
        client_type = str(getattr(client, "client_type", "") or "").strip()
        id_number = str(getattr(client, "id_number", "") or "").strip()
        legal_representative = str(getattr(client, "legal_representative", "") or "").strip()
        address = str(getattr(client, "address", "") or "").strip()
        phone = str(getattr(client, "phone", "") or "").strip()

        lines: list[str] = [f"{role_label}：{name}"]
        if client_type == "natural":
            lines.append(f"身份证号码：{id_number}")
        else:
            lines.append(f"统一社会信用代码：{id_number}")
            lines.append(f"法定代表人：{legal_representative}")
        lines.append(f"地址：{address}")
        lines.append(f"联系电话：{phone}")
        return "\n".join(lines)

    def _get_ordered_lawyer_names(self, case: Any) -> list[str]:
        assignments: list[Any]
        try:
            assignments = list(case.assignments.select_related("lawyer").all().order_by("id"))
        except Exception:
            logger.exception("操作失败")
            assignments = []

        def sort_key(a: Any) -> tuple[Any, ...]:
            return (0 if getattr(a, "is_primary", False) else 1, getattr(a, "id", 0))

        assignments = sorted(assignments, key=sort_key)

        names: list[str] = []
        seen: set[str] = set()
        for assignment in assignments:
            lawyer = getattr(assignment, "lawyer", None)
            if not lawyer:
                continue
            name = str(getattr(lawyer, "real_name", None) or getattr(lawyer, "username", "") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            names.append(name)
        return names

    def _get_lawyer_names(self, case: Any) -> str:
        return "、".join(self._get_ordered_lawyer_names(case))

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
