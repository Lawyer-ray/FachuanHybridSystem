"""Additional coverage tests for automation.api.court_guarantee_helpers.

Covers: _get_case_number, _has_case_number, _get_case_court_name,
_normalize_insurance_company, _parse_preserve_amount, _normalize_consultant_code,
_normalize_property_clue_content, _normalize_property_value, _build_property_clue_info,
_extract_quote_company_options, _resolve_insurance_company_defaults,
_build_cause_candidates, _normalize_party_type, _build_party_payload_from_case_party,
_list_party_payloads, _pick_party_payload, _normalize_selected_party_ids,
_list_opponent_case_parties, _list_opponent_party_payloads, _build_respondent_options,
_build_plaintiff_agent_payload, _build_session_status_payload, _update_session_task.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
try:
    from plugins.court_automation import filing  # noqa: F401
except ImportError:
    pytest.skip("court_automation plugin not installed", allow_module_level=True)



# ---------------------------------------------------------------------------
# _get_case_number / _has_case_number
# ---------------------------------------------------------------------------


class TestCaseNumberHelpers:
    def test_get_case_number_from_table(self):
        from plugins.court_automation.guarantee.helpers import _get_case_number

        case = MagicMock()
        case.case_numbers.exclude.return_value.exclude.return_value.values_list.return_value.first.return_value = "CN001"
        assert _get_case_number(case) == "CN001"

    def test_get_case_number_from_filing(self):
        from plugins.court_automation.guarantee.helpers import _get_case_number

        case = MagicMock()
        case.case_numbers.exclude.return_value.exclude.return_value.values_list.return_value.first.return_value = None
        case.filing_number = "FL001"
        assert _get_case_number(case) == "FL001"

    def test_has_case_number_true(self):
        from plugins.court_automation.guarantee.helpers import _has_case_number

        case = MagicMock()
        case.case_numbers.exclude.return_value.exclude.return_value.values_list.return_value.first.return_value = "CN001"
        assert _has_case_number(case) is True

    def test_has_case_number_false(self):
        from plugins.court_automation.guarantee.helpers import _has_case_number

        case = MagicMock()
        case.case_numbers.exclude.return_value.exclude.return_value.values_list.return_value.first.return_value = None
        case.filing_number = ""
        assert _has_case_number(case) is False


# ---------------------------------------------------------------------------
# _get_case_court_name
# ---------------------------------------------------------------------------


class TestGetCaseCourtName:
    def test_trial_authority(self):
        from plugins.court_automation.guarantee.helpers import _get_case_court_name

        authority = MagicMock()
        authority.name = "天河区人民法院"
        authority.authority_type = "trial"
        case = MagicMock()
        case.supervising_authorities.all.return_value.order_by.return_value.filter.return_value.first.return_value = authority

        with patch(
            "plugins.court_automation.guarantee.helpers._resolve_court_name",
            return_value="天河区人民法院",
        ):
            result = _get_case_court_name(case)
        assert result == "天河区人民法院"

    def test_no_authority(self):
        from plugins.court_automation.guarantee.helpers import _get_case_court_name

        case = MagicMock()
        qs = MagicMock()
        qs.filter.return_value.first.return_value = None
        qs.exclude.return_value.exclude.return_value.first.return_value = None
        case.supervising_authorities.all.return_value.order_by.return_value = qs
        assert _get_case_court_name(case) is None


# ---------------------------------------------------------------------------
# _normalize_insurance_company
# ---------------------------------------------------------------------------


class TestNormalizeInsuranceCompany:
    def test_empty_name_with_options(self):
        from plugins.court_automation.guarantee.helpers import _normalize_insurance_company
        result = _normalize_insurance_company("", allowed_options=["A", "B"])
        assert result == "A"

    def test_empty_name_no_options(self):
        from plugins.court_automation.guarantee.helpers import _normalize_insurance_company
        result = _normalize_insurance_company("")
        assert result == "中国平安财产保险股份有限公司"

    def test_valid_name_in_options(self):
        from plugins.court_automation.guarantee.helpers import _normalize_insurance_company
        result = _normalize_insurance_company("B", allowed_options=["A", "B", "C"])
        assert result == "B"

    def test_name_not_in_options(self):
        from plugins.court_automation.guarantee.helpers import _normalize_insurance_company
        result = _normalize_insurance_company("D", allowed_options=["A", "B"])
        assert result == "A"

    def test_name_in_global_options(self):
        from plugins.court_automation.guarantee.helpers import _normalize_insurance_company
        result = _normalize_insurance_company("中国平安财产保险股份有限公司")
        assert result == "中国平安财产保险股份有限公司"


# ---------------------------------------------------------------------------
# _parse_preserve_amount
# ---------------------------------------------------------------------------


class TestParsePreserveAmount:
    def test_none(self):
        from plugins.court_automation.guarantee.helpers import _parse_preserve_amount
        assert _parse_preserve_amount(None) is None

    def test_decimal_passthrough(self):
        from plugins.court_automation.guarantee.helpers import _parse_preserve_amount
        assert _parse_preserve_amount(Decimal("100")) == Decimal("100")

    def test_string_value(self):
        from plugins.court_automation.guarantee.helpers import _parse_preserve_amount
        assert _parse_preserve_amount("500.50") == Decimal("500.50")

    def test_invalid_string(self):
        from plugins.court_automation.guarantee.helpers import _parse_preserve_amount
        assert _parse_preserve_amount("abc") is None


# ---------------------------------------------------------------------------
# _normalize_consultant_code
# ---------------------------------------------------------------------------


class TestNormalizeConsultantCode:
    def test_sunshine_without_code(self):
        from plugins.court_automation.guarantee.helpers import _normalize_consultant_code
        result = _normalize_consultant_code(
            insurance_company_name="阳光财产保险股份有限公司", consultant_code=None
        )
        assert result == "08740007"

    def test_sunshine_with_code(self):
        from plugins.court_automation.guarantee.helpers import _normalize_consultant_code
        result = _normalize_consultant_code(
            insurance_company_name="阳光财产保险股份有限公司", consultant_code="12345"
        )
        assert result == "12345"

    def test_non_sunshine(self):
        from plugins.court_automation.guarantee.helpers import _normalize_consultant_code
        result = _normalize_consultant_code(
            insurance_company_name="平安", consultant_code=None
        )
        assert result == ""


# ---------------------------------------------------------------------------
# _normalize_property_clue_content
# ---------------------------------------------------------------------------


class TestNormalizePropertyClueContent:
    def test_empty(self):
        from plugins.court_automation.guarantee.helpers import _normalize_property_clue_content
        assert _normalize_property_clue_content("") == ""

    def test_multiline(self):
        from plugins.court_automation.guarantee.helpers import _normalize_property_clue_content
        result = _normalize_property_clue_content("线索1\n线索2\n线索3")
        assert result == "线索1；线索2；线索3"

    def test_whitespace_only_lines(self):
        from plugins.court_automation.guarantee.helpers import _normalize_property_clue_content
        assert _normalize_property_clue_content("\n  \n") == ""


# ---------------------------------------------------------------------------
# _normalize_property_value
# ---------------------------------------------------------------------------


class TestNormalizePropertyValue:
    def test_none(self):
        from plugins.court_automation.guarantee.helpers import _normalize_property_value
        assert _normalize_property_value(None) == ""

    def test_with_commas(self):
        from plugins.court_automation.guarantee.helpers import _normalize_property_value
        assert _normalize_property_value("1,000,000") == "1000000"

    def test_trailing_zeros(self):
        from plugins.court_automation.guarantee.helpers import _normalize_property_value
        assert _normalize_property_value("100.500") == "100.5"

    def test_integer_string(self):
        from plugins.court_automation.guarantee.helpers import _normalize_property_value
        assert _normalize_property_value("500") == "500"


# ---------------------------------------------------------------------------
# _build_property_clue_info
# ---------------------------------------------------------------------------


class TestBuildPropertyClueInfo:
    def test_known_type(self):
        from plugins.court_automation.guarantee.helpers import _build_property_clue_info
        result = _build_property_clue_info(clue_type="bank", raw_content="工商银行账户")
        assert "银行账户" in result
        assert "工商银行账户" in result

    def test_unknown_type(self):
        from plugins.court_automation.guarantee.helpers import _build_property_clue_info
        result = _build_property_clue_info(clue_type="unknown", raw_content="内容")
        assert "unknown" in result

    def test_empty_content(self):
        from plugins.court_automation.guarantee.helpers import _build_property_clue_info
        result = _build_property_clue_info(clue_type="bank", raw_content="")
        assert result == "银行账户"


# ---------------------------------------------------------------------------
# _extract_quote_company_options
# ---------------------------------------------------------------------------


class TestExtractQuoteCompanyOptions:
    def test_none_context(self):
        from plugins.court_automation.guarantee.helpers import _extract_quote_company_options
        assert _extract_quote_company_options(quote_context=None) == []

    def test_no_items(self):
        from plugins.court_automation.guarantee.helpers import _extract_quote_company_options
        assert _extract_quote_company_options(quote_context={}) == []

    def test_with_items(self):
        from plugins.court_automation.guarantee.helpers import _extract_quote_company_options
        ctx = {
            "items": [
                {"company_name": "平安", "status": "success"},
                {"company_name": "人保", "status": "failed"},
                {"company_name": "平安", "status": "success"},  # duplicate
            ]
        }
        result = _extract_quote_company_options(quote_context=ctx)
        assert result[0] == "平安"  # preferred first
        assert "人保" in result
        assert len(result) == 2  # deduplicated

    def test_non_dict_item_skipped(self):
        from plugins.court_automation.guarantee.helpers import _extract_quote_company_options
        ctx = {"items": ["not_a_dict", {"company_name": "平安", "status": "success"}]}
        result = _extract_quote_company_options(quote_context=ctx)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _resolve_insurance_company_defaults
# ---------------------------------------------------------------------------


class TestResolveInsuranceCompanyDefaults:
    def test_with_recommended(self):
        from plugins.court_automation.guarantee.helpers import _resolve_insurance_company_defaults
        ctx = {
            "recommended_company": "人保",
            "items": [
                {"company_name": "平安", "status": "success"},
                {"company_name": "人保", "status": "success"},
            ],
        }
        default, options = _resolve_insurance_company_defaults(quote_context=ctx)
        assert default == "人保"

    def test_no_quote_options(self):
        from plugins.court_automation.guarantee.helpers import _resolve_insurance_company_defaults
        default, options = _resolve_insurance_company_defaults(quote_context=None)
        assert default == "中国平安财产保险股份有限公司"


# ---------------------------------------------------------------------------
# _build_cause_candidates
# ---------------------------------------------------------------------------


class TestBuildCauseCandidates:
    def test_empty(self):
        from plugins.court_automation.guarantee.helpers import _build_cause_candidates
        assert _build_cause_candidates("") == []

    def test_with_jiufen(self):
        from plugins.court_automation.guarantee.helpers import _build_cause_candidates
        result = _build_cause_candidates("买卖合同纠纷")
        assert "买卖合同纠纷" in result
        assert "买卖合同" in result

    def test_multiple_causes(self):
        from plugins.court_automation.guarantee.helpers import _build_cause_candidates
        result = _build_cause_candidates("买卖合同纠纷、借款合同纠纷")
        assert len(result) >= 2


# ---------------------------------------------------------------------------
# _normalize_party_type
# ---------------------------------------------------------------------------


class TestNormalizePartyType:
    def test_natural_variants(self):
        from plugins.court_automation.guarantee.helpers import _normalize_party_type
        assert _normalize_party_type("person") == "natural"
        assert _normalize_party_type("individual") == "natural"

    def test_legal_variants(self):
        from plugins.court_automation.guarantee.helpers import _normalize_party_type
        assert _normalize_party_type("corp") == "legal"
        assert _normalize_party_type("company") == "legal"
        assert _normalize_party_type("enterprise") == "legal"
        assert _normalize_party_type("organization") == "legal"
        assert _normalize_party_type("org") == "legal"

    def test_non_legal_org(self):
        from plugins.court_automation.guarantee.helpers import _normalize_party_type
        assert _normalize_party_type("non_legal_org") == "non_legal_org"

    def test_unknown_defaults_to_natural(self):
        from plugins.court_automation.guarantee.helpers import _normalize_party_type
        assert _normalize_party_type("unknown") == "natural"
        assert _normalize_party_type(None) == "natural"


# ---------------------------------------------------------------------------
# _build_party_payload_from_case_party
# ---------------------------------------------------------------------------


class TestBuildPartyPayloadFromCaseParty:
    def test_natural_person(self):
        from plugins.court_automation.guarantee.helpers import _build_party_payload_from_case_party

        party = MagicMock()
        party.id = 1
        party.client.client_type = "natural"
        party.client.name = "张三"
        party.client.id_number = "110101199003077715"
        party.client.phone = "13800138000"
        party.client.address = "北京市"
        party.client.legal_representative = ""
        party.client.legal_representative_id_number = ""

        result = _build_party_payload_from_case_party(party=party)
        assert result["party_type"] == "natural"
        assert result["name"] == "张三"

    def test_legal_person_defaults(self):
        from plugins.court_automation.guarantee.helpers import _build_party_payload_from_case_party

        party = MagicMock()
        party.id = 2
        party.client.client_type = "legal"
        party.client.name = "Test Corp"
        party.client.id_number = ""
        party.client.phone = ""
        party.client.address = ""
        party.client.legal_representative = "李四"
        party.client.legal_representative_id_number = ""

        result = _build_party_payload_from_case_party(party=party)
        assert result["party_type"] == "legal"
        assert result["id_number"] == "91440101MA59TEST8X"

    def test_none_party(self):
        from plugins.court_automation.guarantee.helpers import _build_party_payload_from_case_party

        result = _build_party_payload_from_case_party(party=None)
        assert result["name"] == "张三"


# ---------------------------------------------------------------------------
# _list_party_payloads / _pick_party_payload
# ---------------------------------------------------------------------------


class TestListAndPickPartyPayloads:
    def test_list_with_preferred_status(self):
        from plugins.court_automation.guarantee.helpers import _list_party_payloads

        party = MagicMock()
        party.legal_status = "plaintiff"
        party.id = 1
        party.client.client_type = "natural"
        party.client.name = "张三"
        party.client.id_number = "110101199003077715"
        party.client.phone = ""
        party.client.address = ""
        party.client.is_our_client = True
        party.client.legal_representative = ""
        party.client.legal_representative_id_number = ""

        result = _list_party_payloads(
            case_parties=[party],
            preferred_statuses={"plaintiff"},
            prefer_our=True,
        )
        assert len(result) == 1

    def test_pick_fallback(self):
        from plugins.court_automation.guarantee.helpers import _pick_party_payload

        result = _pick_party_payload(
            case_parties=[],
            preferred_statuses={"plaintiff"},
            prefer_our=True,
        )
        assert result["name"] == "张三"  # fallback


# ---------------------------------------------------------------------------
# _normalize_selected_party_ids
# ---------------------------------------------------------------------------


class TestNormalizeSelectedPartyIds:
    def test_none(self):
        from plugins.court_automation.guarantee.helpers import _normalize_selected_party_ids
        assert _normalize_selected_party_ids(None) is None

    def test_valid_ids(self):
        from plugins.court_automation.guarantee.helpers import _normalize_selected_party_ids
        assert _normalize_selected_party_ids([1, 2, 3]) == {1, 2, 3}

    def test_filters_invalid(self):
        from plugins.court_automation.guarantee.helpers import _normalize_selected_party_ids
        assert _normalize_selected_party_ids([0, -1, "abc", 5]) == {5}


# ---------------------------------------------------------------------------
# _list_opponent_case_parties
# ---------------------------------------------------------------------------


class TestListOpponentCaseParties:
    def test_with_non_our_client(self):
        from plugins.court_automation.guarantee.helpers import _list_opponent_case_parties

        party = MagicMock()
        party.client.is_our_client = False
        result = _list_opponent_case_parties(case_parties=[party])
        assert len(result) == 1

    def test_fallback_to_respondent_status(self):
        from plugins.court_automation.guarantee.helpers import _list_opponent_case_parties

        party = MagicMock()
        party.client.is_our_client = True
        party.legal_status = "defendant"
        result = _list_opponent_case_parties(case_parties=[party])
        assert len(result) == 1

    def test_fallback_to_all(self):
        from plugins.court_automation.guarantee.helpers import _list_opponent_case_parties

        party = MagicMock()
        party.client.is_our_client = True
        party.legal_status = "unknown"
        result = _list_opponent_case_parties(case_parties=[party])
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _list_opponent_party_payloads
# ---------------------------------------------------------------------------


class TestListOpponentPartyPayloads:
    def test_returns_payloads(self):
        from plugins.court_automation.guarantee.helpers import _list_opponent_party_payloads

        party = MagicMock()
        party.client.is_our_client = False
        party.id = 1
        party.client.client_type = "natural"
        party.client.name = "被告"
        party.client.id_number = ""
        party.client.phone = ""
        party.client.address = ""
        party.client.legal_representative = ""
        party.client.legal_representative_id_number = ""

        result = _list_opponent_party_payloads(case_parties=[party])
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _build_respondent_options
# ---------------------------------------------------------------------------


class TestBuildRespondentOptions:
    def test_returns_options(self):
        from plugins.court_automation.guarantee.helpers import _build_respondent_options

        party = MagicMock()
        party.client.is_our_client = False
        party.id = 1
        party.legal_status = "defendant"
        party.client.name = "被告公司"
        party.get_legal_status_display.return_value = "被告"

        result = _build_respondent_options(case_parties=[party])
        assert len(result) == 1
        assert result[0]["name"] == "被告公司"


# ---------------------------------------------------------------------------
# _build_plaintiff_agent_payload
# ---------------------------------------------------------------------------


class TestBuildPlaintiffAgentPayload:
    def test_no_lawyer(self):
        from plugins.court_automation.guarantee.helpers import _build_plaintiff_agent_payload

        case = MagicMock()
        case.assignments.select_related.return_value.order_by.return_value.first.return_value = None

        with patch("apps.organization.models.Lawyer") as MockLawyer:
            MockLawyer.objects.select_related.return_value.filter.return_value.first.return_value = None
            result = _build_plaintiff_agent_payload(
                case=case, requester_id=None, fallback_party={"name": "张三", "phone": "13800138000"}
            )
        assert result["name"] == "张三"

    def test_with_lawyer(self):
        from plugins.court_automation.guarantee.helpers import _build_plaintiff_agent_payload

        lawyer = MagicMock()
        lawyer.real_name = "李律师"
        lawyer.username = "lls"
        lawyer.id_card = "110101199003077715"
        lawyer.phone = "13900139000"
        lawyer.license_no = "A20201234"
        lawyer.law_firm = MagicMock()
        lawyer.law_firm.name = "Test Firm"

        case = MagicMock()
        case.assignments.select_related.return_value.order_by.return_value.first.return_value = None

        with patch("apps.organization.models.Lawyer") as MockLawyer:
            MockLawyer.objects.select_related.return_value.filter.return_value.first.return_value = lawyer
            result = _build_plaintiff_agent_payload(
                case=case, requester_id=1, fallback_party={"name": "张三", "phone": ""}
            )
        assert result["name"] == "李律师"
        assert result["law_firm"] == "Test Firm"


# ---------------------------------------------------------------------------
# _build_session_status_payload (guarantee version)
# ---------------------------------------------------------------------------


class TestGuaranteeSessionStatusPayload:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _build_session_status_payload
        return _build_session_status_payload

    def test_pending(self):
        task = MagicMock()
        task.status = "pending"
        task.id = 1
        task.result = {"message": "执行中", "timing": {"start": 1.0}}
        result = self._fn()(task=task)
        assert result["status"] == "in_progress"

    def test_success(self):
        task = MagicMock()
        task.status = "success"
        task.id = 2
        task.result = {"message": "完成"}
        result = self._fn()(task=task)
        assert result["status"] == "completed"

    def test_failed_no_messages(self):
        task = MagicMock()
        task.status = "failed"
        task.id = 3
        task.error_message = ""
        task.result = {}
        result = self._fn()(task=task)
        assert result["message"] == "担保失败"


# ---------------------------------------------------------------------------
# _update_session_task (guarantee version)
# ---------------------------------------------------------------------------


class TestGuaranteeUpdateSessionTask:
    def test_none_session_id(self):
        from plugins.court_automation.guarantee.helpers import _update_session_task
        _update_session_task(session_id=None, status="running")
