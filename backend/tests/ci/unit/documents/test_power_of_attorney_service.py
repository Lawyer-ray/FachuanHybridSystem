"""
Unit tests for PowerOfAttorneyPlaceholderService.

Covers:
  - generate (basic, with selected_clients, with client fallback)
  - _get_selected_clients (from list, from client, empty)
  - _get_specified_date_text (from context, from date service, fallback)
  - _format_principals / _format_one_principal (natural, legal, empty)
  - _format_lawyers (no case, single lawyer, two lawyers, exception)
  - _format_proxy_matters (no case, matched rules, no match)
  - _filter_matching_rules (case_type filter, stage filter, legal status filter)
  - _match_legal_statuses (EXACT, ALL, ANY, empty)
  - _pick_best_rule (sorting by specificity)
  - _get_party_legal_statuses (from context, from parties)
  - _format_signatures / _format_one_signature (natural, legal, empty)
  - _get_rule_case_types (with case_types list, with legacy, empty)
  - _format_today
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.documents.models.choices import LegalStatusMatchMode
from apps.documents.services.placeholders.authorization_materials.power_of_attorney_service import (
    PowerOfAttorneyPlaceholderService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service() -> PowerOfAttorneyPlaceholderService:
    return PowerOfAttorneyPlaceholderService()


def _make_client(client_type: str = "legal", name: str = "TestCorp", **kwargs: Any) -> MagicMock:
    client = MagicMock()
    client.client_type = client_type
    client.name = name
    client.id_number = kwargs.get("id_number", "91110000XXXX")
    client.address = kwargs.get("address", "Beijing")
    client.legal_representative = kwargs.get("legal_representative", "Zhang San")
    client.is_our_client = kwargs.get("is_our_client", True)
    client.id = kwargs.get("id", 1)
    return client


def _make_case(lawyers: list[MagicMock] | None = None, **kwargs: Any) -> MagicMock:
    case = MagicMock()
    case.id = kwargs.get("id", 1)
    case.case_type = kwargs.get("case_type", "civil")
    case.current_stage = kwargs.get("current_stage", "litigation")
    case.specified_date = kwargs.get("specified_date", None)

    # Set up parties
    parties = kwargs.get("parties", [])
    if not parties:
        client = _make_client()
        party = MagicMock()
        party.client = client
        party.legal_status = "plaintiff"
        parties = [party]
    mock_related = MagicMock()
    mock_related.all.return_value = parties
    case.parties = MagicMock()
    case.parties.select_related.return_value = mock_related

    # Set up assignments
    if lawyers is None:
        lawyers = []
    assignments = []
    for lawyer in lawyers:
        assignment = MagicMock()
        assignment.lawyer = lawyer
        assignments.append(assignment)
    case.assignments = MagicMock()
    case.assignments.select_related.return_value.order_by.return_value = assignments

    return case


def _make_lawyer(name: str = "Lawyer A", phone: str = "13800138000", firm_name: str = "Test Firm") -> MagicMock:  # pragma: allowlist secret
    lawyer = MagicMock()
    lawyer.real_name = name
    lawyer.username = "lawyer_a"
    lawyer.phone = phone
    lawyer.law_firm = MagicMock()
    lawyer.law_firm.name = firm_name
    lawyer.law_firm.address = "Firm Address"
    return lawyer


def _make_rule(**kwargs: Any) -> MagicMock:
    rule = MagicMock()
    rule.is_active = kwargs.get("is_active", True)
    rule.case_types = kwargs.get("case_types", [])
    rule.case_type = kwargs.get("case_type", None)
    rule.case_stage = kwargs.get("case_stage", None)
    rule.legal_statuses = kwargs.get("legal_statuses", None)
    rule.legal_status_match_mode = kwargs.get("legal_status_match_mode", LegalStatusMatchMode.ANY)
    rule.items_text = kwargs.get("items_text", "代为提起诉讼、参与庭审")
    rule.priority = kwargs.get("priority", 100)
    rule.id = kwargs.get("id", 1)
    return rule


# ===========================================================================
# Tests
# ===========================================================================


class TestGenerate:
    def test_basic_generate(self) -> None:
        svc = _make_service()
        case = _make_case(lawyers=[_make_lawyer()])
        context_data = {"case": case, "selected_clients": [_make_client()]}

        with patch.object(svc, "_get_specified_date_text", return_value="2026年01月01日"), \
             patch.object(svc, "_format_proxy_matters", return_value="代为提起诉讼"):
            result = svc.generate(context_data)

        assert "授权委托书_委托人信息" in result
        assert "授权委托书_受托人信息" in result
        assert "授权委托书_代理事项" in result
        assert "授权委托书_委托人签名盖章信息" in result

    def test_generate_with_client_fallback(self) -> None:
        svc = _make_service()
        case = _make_case(lawyers=[_make_lawyer()])
        context_data = {"case": case, "client": _make_client()}

        with patch.object(svc, "_get_specified_date_text", return_value="2026年01月01日"), \
             patch.object(svc, "_format_proxy_matters", return_value=""):
            result = svc.generate(context_data)

        assert result["授权委托书_委托人信息"] != ""


class TestGetSelectedClients:
    def test_from_selected_clients_list(self) -> None:
        svc = _make_service()
        clients = [_make_client(name="A"), _make_client(name="B")]
        result = svc._get_selected_clients({"selected_clients": clients})
        assert len(result) == 2

    def test_from_client_key(self) -> None:
        svc = _make_service()
        client = _make_client(name="Single")
        result = svc._get_selected_clients({"client": client})
        assert len(result) == 1
        assert result[0].name == "Single"

    def test_empty_context(self) -> None:
        svc = _make_service()
        result = svc._get_selected_clients({})
        assert result == []

    def test_filters_none_values(self) -> None:
        svc = _make_service()
        result = svc._get_selected_clients({"selected_clients": [None, _make_client()]})
        assert len(result) == 1


class TestGetSpecifiedDateText:
    def test_from_context(self) -> None:
        svc = _make_service()
        result = svc._get_specified_date_text({"指定日期": "2026年06月08日"}, case=None)
        assert result == "2026年06月08日"

    def test_fallback_to_today(self) -> None:
        svc = _make_service()
        with patch("apps.documents.services.placeholders.registry.PlaceholderRegistry"):
            result = svc._get_specified_date_text({}, case=None)
        d = date.today()
        expected = f"{d.year}年{d.month:02d}月{d.day:02d}日"
        assert result == expected


class TestFormatPrincipals:
    def test_legal_entity(self) -> None:
        svc = _make_service()
        client = _make_client(client_type="legal", name="TestCorp", id_number="91110000", legal_representative="Li Si")
        result = svc._format_principals([client])
        assert "委托人名称：TestCorp" in result
        assert "统一社会信用代码：91110000" in result
        assert "法定代表人：Li Si" in result

    def test_natural_person(self) -> None:
        svc = _make_service()
        client = _make_client(client_type="natural", name="Zhang San", id_number="110101199001011234")  # pragma: allowlist secret
        result = svc._format_principals([client])
        assert "委托人姓名：Zhang San" in result
        assert "身份证号码：110101199001011234" in result  # pragma: allowlist secret

    def test_empty_clients(self) -> None:
        svc = _make_service()
        result = svc._format_principals([])
        assert result == ""

    def test_multiple_clients(self) -> None:
        svc = _make_service()
        c1 = _make_client(name="A", client_type="legal")
        c2 = _make_client(name="B", client_type="natural")
        result = svc._format_principals([c1, c2])
        assert "A" in result
        assert "B" in result

    def test_empty_fields(self) -> None:
        svc = _make_service()
        client = MagicMock()
        client.client_type = ""
        client.name = ""
        client.id_number = ""
        client.address = ""
        client.legal_representative = ""
        result = svc._format_principals([client])
        assert "委托人" in result


class TestFormatLawyers:
    def test_no_case(self) -> None:
        svc = _make_service()
        result = svc._format_lawyers(None)
        assert "受托人姓名：" in result
        # Should have two blank blocks
        blocks = result.split("\n\n")
        assert len(blocks) == 2

    def test_single_lawyer(self) -> None:
        svc = _make_service()
        case = _make_case(lawyers=[_make_lawyer("Zhang Lvshi")])
        result = svc._format_lawyers(case)
        assert "Zhang Lvshi" in result
        blocks = result.split("\n\n")
        assert len(blocks) == 2  # single lawyer + blank block

    def test_two_lawyers(self) -> None:
        svc = _make_service()
        case = _make_case(lawyers=[_make_lawyer("A"), _make_lawyer("B")])
        result = svc._format_lawyers(case)
        assert "A" in result
        assert "B" in result

    def test_exception_fallback(self) -> None:
        """Exception during assignment fetch falls back to empty assignments."""
        svc = _make_service()
        case = MagicMock()
        # Make assignments.select_related().order_by() raise when iterated
        mock_chain = MagicMock()
        mock_chain.__iter__ = MagicMock(side_effect=Exception("db error"))
        case.assignments = MagicMock()
        case.assignments.select_related.return_value.order_by.return_value = mock_chain
        result = svc._format_lawyers(case)
        # Exception causes empty assignments list, result is empty string
        assert result == ""


class TestFormatOneLawyerBlock:
    def test_with_lawyer(self) -> None:
        svc = _make_service()
        lawyer = _make_lawyer("TestLawyer", "13900139000", "TestFirm")  # pragma: allowlist secret
        result = svc._format_one_lawyer_block(lawyer)
        assert "受托人姓名：TestLawyer" in result
        assert "工作单位：TestFirm" in result
        assert "联系电话：13900139000" in result  # pragma: allowlist secret

    def test_none_lawyer(self) -> None:
        svc = _make_service()
        result = svc._format_one_lawyer_block(None)
        assert "受托人姓名：" in result
        assert "工作单位：" in result

    def test_no_law_firm(self) -> None:
        svc = _make_service()
        lawyer = MagicMock()
        lawyer.real_name = "A"
        lawyer.username = "a"
        lawyer.phone = ""
        lawyer.law_firm = None
        result = svc._format_one_lawyer_block(lawyer)
        assert "工作单位：" in result


class TestFormatProxyMatters:
    def test_no_case(self) -> None:
        svc = _make_service()
        result = svc._format_proxy_matters({}, case=None, selected_clients=[])
        assert result == ""

    def test_no_matching_rules(self) -> None:
        svc = _make_service()
        case = _make_case()
        with patch.object(svc, "_get_party_legal_statuses", return_value=set()), \
             patch.object(svc, "_query_candidate_rules", return_value=[]):
            result = svc._format_proxy_matters({}, case=case, selected_clients=[_make_client()])
        assert result == ""

    def test_with_matching_rules(self) -> None:
        svc = _make_service()
        case = _make_case()
        rule = _make_rule(items_text="代为提起诉讼、参与庭审", legal_statuses=None)
        with patch.object(svc, "_get_party_legal_statuses", return_value={"plaintiff"}), \
             patch.object(svc, "_query_candidate_rules", return_value=[rule]):
            result = svc._format_proxy_matters({}, case=case, selected_clients=[_make_client()])
        assert "代为提起诉讼" in result


class TestFilterMatchingRules:
    def test_case_type_filter_match(self) -> None:
        svc = _make_service()
        rule = _make_rule(case_types=["civil"], case_stage=None, legal_statuses=None)
        result = svc._filter_matching_rules([rule], "civil", None, set())
        assert len(result) == 1

    def test_case_type_filter_no_match(self) -> None:
        svc = _make_service()
        rule = _make_rule(case_types=["criminal"], case_stage=None, legal_statuses=None)
        result = svc._filter_matching_rules([rule], "civil", None, set())
        assert len(result) == 0

    def test_stage_filter_match(self) -> None:
        svc = _make_service()
        rule = _make_rule(case_types=[], case_stage="litigation", legal_statuses=None)
        result = svc._filter_matching_rules([rule], "civil", "litigation", set())
        assert len(result) == 1

    def test_stage_filter_no_match(self) -> None:
        svc = _make_service()
        rule = _make_rule(case_types=[], case_stage="litigation", legal_statuses=None)
        result = svc._filter_matching_rules([rule], "civil", "arbitration", set())
        assert len(result) == 0


class TestMatchLegalStatuses:
    def test_empty_rule_statuses_always_match(self) -> None:
        svc = _make_service()
        rule = _make_rule(legal_statuses=[])
        assert svc._match_legal_statuses(rule, {"plaintiff"}) is True

    def test_empty_party_statuses_no_match(self) -> None:
        svc = _make_service()
        rule = _make_rule(legal_statuses=["plaintiff"])
        assert svc._match_legal_statuses(rule, set()) is False

    def test_exact_match(self) -> None:
        svc = _make_service()
        rule = _make_rule(legal_statuses=["plaintiff"], legal_status_match_mode=LegalStatusMatchMode.EXACT)
        assert svc._match_legal_statuses(rule, {"plaintiff"}) is True
        assert svc._match_legal_statuses(rule, {"plaintiff", "defendant"}) is False

    def test_all_match(self) -> None:
        svc = _make_service()
        rule = _make_rule(legal_statuses=["plaintiff", "defendant"], legal_status_match_mode=LegalStatusMatchMode.ALL)
        assert svc._match_legal_statuses(rule, {"plaintiff", "defendant", "third_party"}) is True
        assert svc._match_legal_statuses(rule, {"plaintiff"}) is False

    def test_any_match(self) -> None:
        svc = _make_service()
        rule = _make_rule(legal_statuses=["plaintiff"], legal_status_match_mode=LegalStatusMatchMode.ANY)
        assert svc._match_legal_statuses(rule, {"plaintiff", "defendant"}) is True
        assert svc._match_legal_statuses(rule, {"defendant"}) is False


class TestPickBestRule:
    def test_prefers_specific_case_type(self) -> None:
        svc = _make_service()
        r1 = _make_rule(case_types=["civil"], id=1)
        r2 = _make_rule(case_types=[], id=2)
        result = svc._pick_best_rule([r1, r2])
        assert result.id == 1

    def test_prefers_higher_priority(self) -> None:
        svc = _make_service()
        r1 = _make_rule(case_types=[], case_stage=None, legal_statuses=None, priority=50, id=1)
        r2 = _make_rule(case_types=[], case_stage=None, legal_statuses=None, priority=10, id=2)
        result = svc._pick_best_rule([r1, r2])
        assert result.id == 2  # lower priority number = higher priority


class TestGetPartyLegalStatuses:
    def test_from_context(self) -> None:
        svc = _make_service()
        context = {"selected_party_statuses": {"plaintiff", "defendant"}}
        result = svc._get_party_legal_statuses(context, case=None, selected_clients=[])
        assert result == {"plaintiff", "defendant"}

    def test_from_parties(self) -> None:
        svc = _make_service()
        client = _make_client(id=1)
        party = MagicMock()
        party.client = client
        party.legal_status = "plaintiff"
        case = MagicMock()
        case.parties = MagicMock()
        case.parties.select_related.return_value.all.return_value = [party]
        result = svc._get_party_legal_statuses({}, case=case, selected_clients=[client])
        assert "plaintiff" in result

    def test_excludes_opposing_parties(self) -> None:
        svc = _make_service()
        client = _make_client(id=1, is_our_client=False)
        party = MagicMock()
        party.client = client
        party.legal_status = "defendant"
        case = MagicMock()
        case.parties = MagicMock()
        case.parties.select_related.return_value.all.return_value = [party]
        result = svc._get_party_legal_statuses({}, case=case, selected_clients=[client])
        assert "defendant" not in result


class TestFormatSignatures:
    def test_empty(self) -> None:
        svc = _make_service()
        assert svc._format_signatures([], specified_date_text="2026年01月01日") == ""

    def test_legal_entity(self) -> None:
        svc = _make_service()
        client = _make_client(client_type="legal", name="Corp", legal_rep="Zhang")
        result = svc._format_signatures([client], specified_date_text="2026年01月01日")
        assert "委托人（盖章）：Corp" in result
        assert "法定代表人（签名）：Zhang" in result
        assert "日期：2026年01月01日" in result

    def test_natural_person(self) -> None:
        svc = _make_service()
        client = _make_client(client_type="natural", name="Zhang")
        result = svc._format_signatures([client], specified_date_text="2026年01月01日")
        assert "委托人（签名+指模）：Zhang" in result


class TestGetRuleCaseTypes:
    def test_with_case_types_list(self) -> None:
        svc = _make_service()
        rule = _make_rule(case_types=["civil", "criminal"])
        result = svc._get_rule_case_types(rule)
        assert "civil" in result
        assert "criminal" in result

    def test_with_legacy_case_type(self) -> None:
        svc = _make_service()
        rule = _make_rule(case_types=[], case_type="civil")
        result = svc._get_rule_case_types(rule)
        assert "civil" in result

    def test_empty(self) -> None:
        svc = _make_service()
        rule = _make_rule(case_types=[], case_type=None)
        result = svc._get_rule_case_types(rule)
        assert len(result) == 0


class TestFormatToday:
    def test_format(self) -> None:
        svc = _make_service()
        d = date.today()
        expected = f"{d.year}年{d.month:02d}月{d.day:02d}日"
        assert svc._format_today() == expected


class TestServiceMetadata:
    def test_name(self) -> None:
        svc = _make_service()
        assert svc.name == "power_of_attorney_placeholder_service"

    def test_category(self) -> None:
        svc = _make_service()
        assert svc.category == "authorization_material"

    def test_placeholder_keys(self) -> None:
        svc = _make_service()
        keys = svc.get_placeholder_keys()
        assert "授权委托书_委托人信息" in keys
        assert "授权委托书_受托人信息" in keys
        assert "授权委托书_代理事项" in keys
        assert "授权委托书_委托人签名盖章信息" in keys

    def test_placeholder_metadata(self) -> None:
        svc = _make_service()
        meta = svc.get_placeholder_metadata()
        assert "授权委托书_委托人信息" in meta
        assert "display_name" in meta["授权委托书_委托人信息"]

    def test_str(self) -> None:
        svc = _make_service()
        assert "power_of_attorney" in str(svc)

    def test_repr(self) -> None:
        svc = _make_service()
        assert "PowerOfAttorneyPlaceholderService" in repr(svc)


class TestQueryCandidateRules:
    @pytest.mark.django_db
    def test_filters_by_stage(self) -> None:
        svc = _make_service()
        with patch("apps.documents.models.ProxyMatterRule") as mock_model:
            mock_model.objects.filter.return_value.filter.return_value = []
            result = svc._query_candidate_rules("civil", "litigation")
        assert result == []

    @pytest.mark.django_db
    def test_no_stage_filter(self) -> None:
        svc = _make_service()
        with patch("apps.documents.models.ProxyMatterRule") as mock_model:
            mock_model.objects.filter.return_value = []
            result = svc._query_candidate_rules("civil", None)
        assert result == []


class TestModeRank:
    def test_exact_rank(self) -> None:
        svc = _make_service()
        r = _make_rule(legal_status_match_mode=LegalStatusMatchMode.EXACT)
        # Just call _pick_best_rule to exercise mode_rank indirectly
        result = svc._pick_best_rule([r])
        assert result is r

    def test_all_rank(self) -> None:
        svc = _make_service()
        r1 = _make_rule(legal_status_match_mode=LegalStatusMatchMode.EXACT, id=1)
        r2 = _make_rule(legal_status_match_mode=LegalStatusMatchMode.ALL, id=2)
        result = svc._pick_best_rule([r1, r2])
        assert result.id == 1  # EXACT ranks higher

    def test_any_rank_lowest(self) -> None:
        svc = _make_service()
        r1 = _make_rule(legal_status_match_mode=LegalStatusMatchMode.ALL, id=1)
        r2 = _make_rule(legal_status_match_mode=LegalStatusMatchMode.ANY, id=2)
        result = svc._pick_best_rule([r1, r2])
        assert result.id == 1  # ALL ranks higher than ANY
