"""Business logic services."""

import logging
from datetime import date
from typing import Any, ClassVar

from apps.documents.models import ProxyMatterRule
from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry

logger = logging.getLogger(__name__)


@PlaceholderRegistry.register
class PowerOfAttorneyPlaceholderService(BasePlaceholderService):
    name: str = "power_of_attorney_placeholder_service"
    display_name: str = "授权委托材料-授权委托书"
    description: str = "生成授权委托书所需占位符"
    category: str = "authorization_material"
    placeholder_keys: ClassVar = [
        "授权委托书_委托人信息",
        "授权委托书_受托人信息",
        "授权委托书_代理事项",
        "授权委托书_委托人签名盖章信息",
    ]
    placeholder_metadata: ClassVar = {
        "授权委托书_委托人信息": {
            "display_name": "授权委托书_委托人信息",
            "description": "按我方当事人生成,区分自然人/法人,多人用空行分隔",
            "example_value": (
                "委托人名称:XX公司\n统一社会信用代码:...\n法定代表人:...\n地址:...\n\n"
                "委托人姓名:张三\n身份证号码:...\n地址:..."
            ),
        },
        "授权委托书_受托人信息": {
            "display_name": "授权委托书_受托人信息",
            "description": "按案件律师生成,主办在前;只有 1 个律师时补一段空白",
            "example_value": (
                "受托人姓名:主办律师A\n工作单位:律所名称\n联系电话:...\n联系地址:...\n\n"
                "受托人姓名:\n工作单位:\n联系电话:\n联系地址:"
            ),
        },
        "授权委托书_代理事项": {
            "display_name": "授权委托书_代理事项",
            "description": "按代理事项规则表匹配生成(无命中则为空,由生成器决定是否允许下载)",
            "example_value": "代为提起诉讼、参与庭审、代收法律文书等",
        },
        "授权委托书_委托人签名盖章信息": {
            "display_name": "授权委托书_委托人签名盖章信息",
            "description": "按我方当事人生成签名盖章区块,日期使用指定日期(为空默认今天)",
            "example_value": "委托人(盖章):AAA公司\n法定代表人(签名):A小线\n日期:2026年01月22日",
        },
    }

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        case = context_data.get("case")
        selected_clients = self._get_selected_clients(context_data)
        specified_date_text = self._get_specified_date_text(context_data, case=case)
        return {
            "授权委托书_委托人信息": self._format_principals(selected_clients),
            "授权委托书_受托人信息": self._format_lawyers(case),
            "授权委托书_代理事项": self._format_proxy_matters(
                context_data, case=case, selected_clients=selected_clients
            ),
            "授权委托书_委托人签名盖章信息": self._format_signatures(
                selected_clients, specified_date_text=specified_date_text
            ),
        }

    def _get_selected_clients(self, context_data: dict[str, Any]) -> list[Any]:
        selected_clients = context_data.get("selected_clients")
        if isinstance(selected_clients, list):
            return [c for c in selected_clients if c]
        client = context_data.get("client")
        if client:
            return [client]
        return []

    def _get_specified_date_text(self, context_data: dict[str, Any], *, case: Any) -> str:
        if context_data.get("指定日期"):
            return str(context_data["指定日期"])
        try:
            from apps.documents.services.placeholders import PlaceholderRegistry as Registry

            service = Registry().get_service("date_service")
            data: dict[str, Any] = {}
            if case:
                data["case"] = case
            contract = getattr(case, "contract", None) if case else None
            if contract:
                data["contract"] = contract
            result = service.generate(data) or {}
            return result.get("指定日期") or self._format_today()
        except Exception:
            logger.exception("操作失败")
            return self._format_today()

    def _format_today(self) -> str:
        d = date.today()
        return f"{d.year}年{d.month:02d}月{d.day:02d}日"

    def _format_principals(self, clients: list[Any]) -> str:
        if not clients:
            return ""
        parts: list[str] = []
        for idx, client in enumerate(clients):
            if idx > 0:
                parts.append("")
            parts.extend(self._format_one_principal(client))
        return "\n".join(parts).strip()

    def _format_one_principal(self, client: Any) -> list[str]:
        client_type = getattr(client, "client_type", "") or ""
        name = getattr(client, "name", "") or ""
        id_number = getattr(client, "id_number", "") or ""
        address = getattr(client, "address", "") or ""
        legal_rep = getattr(client, "legal_representative", "") or ""
        if client_type == "natural":
            return [f"委托人姓名:{name}", f"身份证号码:{id_number}", f"地址:{address}"]
        return [f"委托人名称:{name}", f"统一社会信用代码:{id_number}", f"法定代表人:{legal_rep}", f"地址:{address}"]

    def _format_lawyers(self, case: Any) -> str:
        if not case:
            return self._format_one_lawyer_block(None) + "\n\n" + self._format_one_lawyer_block(None)
        try:
            assignments = list(case.assignments.select_related("lawyer__law_firm").order_by("id"))
        except Exception as e:
            logger.warning("获取案件律师失败", extra={"case_id": getattr(case, "id", None), "error": str(e)})
            assignments: list[Any] = [] # type: ignore
        blocks: list[str] = []
        for assignment in assignments:
            lawyer = getattr(assignment, "lawyer", None)
            blocks.append(self._format_one_lawyer_block(lawyer))
        if len(blocks) == 1:
            blocks.append(self._format_one_lawyer_block(None))
        return "\n\n".join(blocks).strip()

    def _format_one_lawyer_block(self, lawyer: Any | None) -> str:
        if not lawyer:
            return "\n".join(["受托人姓名:", "工作单位:", "联系电话:", "联系地址:"])
        name = getattr(lawyer, "real_name", None) or getattr(lawyer, "username", "") or ""
        phone = getattr(lawyer, "phone", "") or ""
        law_firm = getattr(lawyer, "law_firm", None)
        firm_name = getattr(law_firm, "name", "") or ""
        firm_address = getattr(law_firm, "address", "") or ""
        return "\n".join(
            [f"受托人姓名:{name}", f"工作单位:{firm_name}", f"联系电话:{phone}", f"联系地址:{firm_address}"]
        )

    def _format_proxy_matters(self, context_data: dict[str, Any], *, case: Any, selected_clients: list[Any]) -> str:
        if not case:
            return ""
        party_statuses = self._get_party_legal_statuses(context_data, case=case, selected_clients=selected_clients)
        case_type = getattr(case, "case_type", None)
        case_stage = getattr(case, "current_stage", None)
        rules = self._query_candidate_rules(case_type, case_stage)
        matched = self._filter_matching_rules(rules, case_type, case_stage, party_statuses)
        if not matched:
            return ""
        chosen = self._pick_best_rule(matched)
        return (chosen.items_text or "").strip()

    def _query_candidate_rules(self, case_type: Any, case_stage: Any) -> list[Any]:
        candidates = ProxyMatterRule.objects.filter(is_active=True)
        if case_type:
            candidates = candidates.filter(case_type__in=[None, case_type])
        if case_stage:
            candidates = candidates.filter(case_stage__in=[None, case_stage])
        return list(candidates)

    def _filter_matching_rules(self, rules: Any, case_type: Any, case_stage: Any, party_statuses: Any) -> list[Any]:
        matched: list[Any] = []
        for rule in rules:
            if rule.case_type and case_type and (rule.case_type != case_type):
                continue
            if rule.case_stage and case_stage and (rule.case_stage != case_stage):
                continue
            if not self._match_legal_statuses(rule, party_statuses):
                continue
            matched.append(rule)
        return matched

    def _pick_best_rule(self, matched: Any) -> Any:

        def mode_rank(mode: str) -> int:
            if mode == ProxyMatterRule.LegalStatusMatchMode.EXACT:
                return 3
            if mode == ProxyMatterRule.LegalStatusMatchMode.ALL:
                return 2
            return 1

        matched.sort(
            key=lambda r: (
                -int(bool(r.case_type)),
                -int(bool(r.case_stage)),
                -int(bool(r.legal_statuses)),
                -mode_rank(getattr(r, "legal_status_match_mode", "")),
                int(getattr(r, "priority", 100)),
                int(getattr(r, "id", 0)),
            )
        )
        return matched[0]

    def _get_party_legal_statuses(
        self, context_data: dict[str, Any], *, case: Any, selected_clients: list[Any]
    ) -> set[str]:
        selected_party_statuses = context_data.get("selected_party_statuses")
        if isinstance(selected_party_statuses, (set, list, tuple)):
            return {str(x) for x in selected_party_statuses if x}
        selected_ids = {getattr(c, "id", None) for c in selected_clients if c}
        statuses: set[str] = set()
        try:
            parties = list(case.parties.select_related("client").all())
        except Exception:
            logger.exception("操作失败")
            parties: list[Any] = [] # type: ignore
        for party in parties:
            client = getattr(party, "client", None)
            if not client or not getattr(client, "is_our_client", False):
                continue
            if selected_ids and getattr(client, "id", None) not in selected_ids:
                continue
            status = getattr(party, "legal_status", None)
            if status:
                statuses.add(str(status))
        return statuses

    def _match_legal_statuses(self, rule: ProxyMatterRule, party_statuses: set[str]) -> bool:
        rule_statuses = set(rule.legal_statuses or [])
        if not rule_statuses:
            return True
        if not party_statuses:
            return False
        mode = getattr(rule, "legal_status_match_mode", ProxyMatterRule.LegalStatusMatchMode.ANY)
        if mode == ProxyMatterRule.LegalStatusMatchMode.EXACT:
            return rule_statuses == party_statuses
        if mode == ProxyMatterRule.LegalStatusMatchMode.ALL:
            return rule_statuses.issubset(party_statuses)
        return bool(rule_statuses & party_statuses)

    def _format_signatures(self, clients: list[Any], *, specified_date_text: str) -> str:
        if not clients:
            return ""
        blocks: list[str] = []
        for idx, client in enumerate(clients):
            if idx > 0:
                blocks.append("")
            blocks.extend(self._format_one_signature(client, specified_date_text=specified_date_text))
        return "\n".join(blocks).strip()

    def _format_one_signature(self, client: Any, *, specified_date_text: str) -> list[str]:
        client_type = getattr(client, "client_type", "") or ""
        name = getattr(client, "name", "") or ""
        legal_rep = getattr(client, "legal_representative", "") or ""
        if client_type == "natural":
            return [f"委托人(签名+指模):{name}", f"日期:{specified_date_text}"]
        return [f"委托人(盖章):{name}", f"法定代表人(签名):{legal_rep}", f"日期:{specified_date_text}"]
