"""Comprehensive tests for automation.api.court_guarantee_helpers.

Covers all branches: get_case_number, has_case_number, get_case_court_name,
resolve_court_name, normalize_insurance_company, parse_preserve_amount,
normalize_consultant_code, normalize_property_clue_content, normalize_property_value,
build_property_clue_info, build_selected_respondent_property_clues,
build_primary_respondent_property_clue, build_case_quote_context,
build_reusable_quote_options, extract_quote_company_options,
resolve_insurance_company_defaults, build_guarantee_material_paths,
build_cause_candidates, normalize_party_type, build_party_payload_from_case_party,
list_party_payloads, pick_party_payload, normalize_selected_party_ids,
list_opponent_case_parties, list_opponent_party_payloads, build_respondent_options,
build_plaintiff_agent_payload, build_session_status_payload, update_session_task.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, PropertyMock, call, patch

import pytest

try:
    from plugins.court_automation import filing
except ImportError:
    pytest.skip("court_automation plugin not installed", allow_module_level=True)



# ---------------------------------------------------------------------------
# _get_case_number / _has_case_number
# ---------------------------------------------------------------------------


class TestCaseNumberHelpers:
    def test_get_case_number_from_table(self):
        from plugins.court_automation.guarantee.helpers import _get_case_number

        case = MagicMock()
        qs = MagicMock()
        qs.exclude.return_value.exclude.return_value.values_list.return_value.first.return_value = "(2025)粤01民初1号"
        case.case_numbers = qs
        assert _get_case_number(case) == "(2025)粤01民初1号"

    def test_get_case_number_fallback_to_filing(self):
        from plugins.court_automation.guarantee.helpers import _get_case_number

        case = MagicMock()
        qs = MagicMock()
        qs.exclude.return_value.exclude.return_value.values_list.return_value.first.return_value = None
        case.case_numbers = qs
        case.filing_number = "FN-001"
        assert _get_case_number(case) == "FN-001"

    def test_get_case_number_empty(self):
        from plugins.court_automation.guarantee.helpers import _get_case_number

        case = MagicMock()
        qs = MagicMock()
        qs.exclude.return_value.exclude.return_value.values_list.return_value.first.return_value = None
        case.case_numbers = qs
        case.filing_number = ""
        assert _get_case_number(case) == ""

    def test_has_case_number_true(self):
        from plugins.court_automation.guarantee.helpers import _has_case_number

        case = MagicMock()
        qs = MagicMock()
        qs.exclude.return_value.exclude.return_value.values_list.return_value.first.return_value = "123"
        case.case_numbers = qs
        assert _has_case_number(case) is True

    def test_has_case_number_false(self):
        from plugins.court_automation.guarantee.helpers import _has_case_number

        case = MagicMock()
        qs = MagicMock()
        qs.exclude.return_value.exclude.return_value.values_list.return_value.first.return_value = None
        case.case_numbers = qs
        case.filing_number = ""
        assert _has_case_number(case) is False


# ---------------------------------------------------------------------------
# _resolve_court_name (guarantee version)
# ---------------------------------------------------------------------------


class TestGuaranteeResolveCourtName:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _resolve_court_name
        return _resolve_court_name

    def test_none_input(self):
        assert self._fn()(None) is None

    def test_empty_input(self):
        assert self._fn()("") is None

    def test_whitespace_only(self):
        assert self._fn()("   ") is None

    def test_already_has_renmfy(self):
        assert self._fn()("广州市天河区人民法院") == "广州市天河区人民法院"

    @pytest.mark.django_db
    def test_not_found_appends_suffix(self):
        assert self._fn()("不存在的法院") == "不存在的法院人民法院"


# ---------------------------------------------------------------------------
# _get_case_court_name
# ---------------------------------------------------------------------------


class TestGetCaseCourtName:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _get_case_court_name
        return _get_case_court_name

    def test_trial_authority_found(self):
        case = MagicMock()
        authority = MagicMock()
        authority.name = "天河区"
        authority.authority_type = "trial"
        qs = MagicMock()
        qs.filter.return_value.first.return_value = authority
        case.supervising_authorities.all.return_value.order_by.return_value = qs

        with patch("apps.core.models.enums.AuthorityType") as mock_at:
            mock_at.TRIAL = "trial"
            with patch("plugins.court_automation.guarantee.helpers._resolve_court_name", return_value="广州市天河区人民法院"):
                result = self._fn()(case)
        assert result == "广州市天河区人民法院"

    def test_no_trial_authority_uses_any_named(self):
        case = MagicMock()
        qs = MagicMock()
        qs.filter.return_value.first.return_value = None
        named = MagicMock()
        named.name = "海珠区"
        qs.exclude.return_value.exclude.return_value.first.return_value = named
        case.supervising_authorities.all.return_value.order_by.return_value = qs

        with patch("apps.core.models.enums.AuthorityType") as mock_at:
            mock_at.TRIAL = "trial"
            with patch("plugins.court_automation.guarantee.helpers._resolve_court_name", return_value="广州市海珠区人民法院"):
                result = self._fn()(case)
        assert result == "广州市海珠区人民法院"

    def test_no_authorities_returns_none(self):
        case = MagicMock()
        qs = MagicMock()
        qs.filter.return_value.first.return_value = None
        qs.exclude.return_value.exclude.return_value.first.return_value = None
        case.supervising_authorities.all.return_value.order_by.return_value = qs

        with patch("apps.core.models.enums.AuthorityType") as mock_at:
            mock_at.TRIAL = "trial"
            result = self._fn()(case)
        assert result is None


# ---------------------------------------------------------------------------
# _normalize_insurance_company
# ---------------------------------------------------------------------------


class TestNormalizeInsuranceCompany:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _normalize_insurance_company
        return _normalize_insurance_company

    def test_empty_with_allowed_options(self):
        assert self._fn()("", allowed_options=["A公司", "B公司"]) == "A公司"

    def test_empty_without_allowed_options(self):
        from plugins.court_automation.guarantee.schemas import _DEFAULT_INSURANCE_COMPANY
        assert self._fn()("") == _DEFAULT_INSURANCE_COMPANY

    def test_in_allowed_options(self):
        assert self._fn()("B公司", allowed_options=["A公司", "B公司"]) == "B公司"

    def test_not_in_allowed_options(self):
        assert self._fn()("C公司", allowed_options=["A公司", "B公司"]) == "A公司"

    def test_in_default_options(self):
        from plugins.court_automation.guarantee.schemas import _GUARANTEE_INSURANCE_COMPANY_OPTIONS
        company = _GUARANTEE_INSURANCE_COMPANY_OPTIONS[0]
        assert self._fn()(company) == company

    def test_not_in_default_options(self):
        from plugins.court_automation.guarantee.schemas import _DEFAULT_INSURANCE_COMPANY
        assert self._fn()("不存在的公司") == _DEFAULT_INSURANCE_COMPANY


# ---------------------------------------------------------------------------
# _parse_preserve_amount
# ---------------------------------------------------------------------------


class TestParsePreserveAmount:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _parse_preserve_amount
        return _parse_preserve_amount

    def test_none(self):
        assert self._fn()(None) is None

    def test_decimal_input(self):
        assert self._fn()(Decimal("100.50")) == Decimal("100.50")

    def test_string_number(self):
        assert self._fn()("123.45") == Decimal("123.45")

    def test_int_input(self):
        assert self._fn()(100) == Decimal("100")

    def test_invalid_string(self):
        assert self._fn()("abc") is None

    def test_empty_string(self):
        assert self._fn()("") is None


# ---------------------------------------------------------------------------
# _normalize_consultant_code
# ---------------------------------------------------------------------------


class TestNormalizeConsultantCode:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _normalize_consultant_code
        return _normalize_consultant_code

    def test_sunshine_company_no_code(self):
        from plugins.court_automation.guarantee.schemas import _SUNSHINE_DEFAULT_CONSULTANT_CODE
        result = self._fn()(insurance_company_name="阳光财产保险股份有限公司", consultant_code=None)
        assert result == _SUNSHINE_DEFAULT_CONSULTANT_CODE

    def test_sunshine_company_with_code(self):
        result = self._fn()(insurance_company_name="阳光财产保险股份有限公司", consultant_code="12345")
        assert result == "12345"

    def test_other_company(self):
        result = self._fn()(insurance_company_name="中国平安", consultant_code=None)
        assert result == ""

    def test_empty_company(self):
        result = self._fn()(insurance_company_name="", consultant_code="12345")
        assert result == "12345"


# ---------------------------------------------------------------------------
# _normalize_property_clue_content
# ---------------------------------------------------------------------------


class TestNormalizePropertyClueContent:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _normalize_property_clue_content
        return _normalize_property_clue_content

    def test_empty(self):
        assert self._fn()("") == ""

    def test_none(self):
        assert self._fn()(None) == ""

    def test_single_line(self):
        assert self._fn()("账号123") == "账号123"

    def test_multiple_lines(self):
        assert self._fn()("line1\nline2\nline3") == "line1；line2；line3"

    def test_blank_lines_filtered(self):
        assert self._fn()("line1\n\nline2\n  \nline3") == "line1；line2；line3"

    def test_whitespace_lines_only(self):
        assert self._fn()("  \n  \n  ") == ""


# ---------------------------------------------------------------------------
# _normalize_property_value
# ---------------------------------------------------------------------------


class TestNormalizePropertyValue:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _normalize_property_value
        return _normalize_property_value

    def test_none(self):
        assert self._fn()(None) == ""

    def test_integer_string(self):
        assert self._fn()("100000") == "100000"

    def test_with_commas(self):
        assert self._fn()("100,000.00") == "100000"

    def test_decimal_trailing_zeros(self):
        assert self._fn()("100.50") == "100.5"

    def test_integer_no_decimal(self):
        assert self._fn()("100000.00") == "100000"


# ---------------------------------------------------------------------------
# _build_property_clue_info
# ---------------------------------------------------------------------------


class TestBuildPropertyClueInfo:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _build_property_clue_info
        return _build_property_clue_info

    def test_with_known_type(self):
        result = self._fn()(clue_type="bank", raw_content="招商银行\n工商银行")
        assert result.startswith("银行账户")
        assert "招商银行" in result
        assert "工商银行" in result

    def test_with_unknown_type(self):
        result = self._fn()(clue_type="custom_type", raw_content="内容")
        assert "custom_type" in result

    def test_empty_content(self):
        result = self._fn()(clue_type="bank", raw_content="")
        assert result == "银行账户"

    def test_empty_type_and_content(self):
        from plugins.court_automation.guarantee.schemas import _PROPERTY_CLUE_TYPE_DISPLAY
        result = self._fn()(clue_type="", raw_content="")
        assert "财产线索" in result


# ---------------------------------------------------------------------------
# _build_selected_respondent_property_clues
# ---------------------------------------------------------------------------


class TestBuildSelectedRespondentPropertyClues:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _build_selected_respondent_property_clues
        return _build_selected_respondent_property_clues

    def _make_party(self, party_id=1, client_id=10, name="张三", address="地址A", is_our=False):
        party = MagicMock()
        party.id = party_id
        client = MagicMock()
        client.id = client_id
        client.name = name
        client.address = address
        client.is_our_client = is_our
        party.client = client
        return party

    @patch("plugins.court_automation.guarantee.helpers._get_client_service")
    def test_selected_parties_with_clues(self, mock_svc_fn):
        party = self._make_party()
        clue = MagicMock()
        clue.clue_type = "bank"
        clue.content = "招商银行"
        mock_svc = MagicMock()
        mock_svc.get_property_clues_by_client_internal.return_value = [clue]
        mock_svc_fn.return_value = mock_svc

        result = self._fn()(
            case_parties=[party],
            selected_respondents=[{"party_id": 1}],
            preserve_amount=Decimal("10000"),
        )
        assert len(result) == 1
        assert "银行账户" in result[0]["property_info"]

    @patch("plugins.court_automation.guarantee.helpers._get_client_service")
    def test_no_clues_gets_default_entry(self, mock_svc_fn):
        party = self._make_party()
        mock_svc = MagicMock()
        mock_svc.get_property_clues_by_client_internal.return_value = []
        mock_svc_fn.return_value = mock_svc

        result = self._fn()(
            case_parties=[party],
            selected_respondents=[{"party_id": 1}],
            preserve_amount=Decimal("10000"),
        )
        assert len(result) == 1
        assert "张三名下财产线索" in result[0]["property_info"]

    @patch("plugins.court_automation.guarantee.helpers._get_client_service")
    @patch("plugins.court_automation.guarantee.helpers._list_opponent_case_parties")
    def test_fallback_to_opponents(self, mock_opponents, mock_svc_fn):
        party = self._make_party(party_id=999)
        mock_opponents.return_value = [party]
        mock_svc = MagicMock()
        mock_svc.get_property_clues_by_client_internal.return_value = []
        mock_svc_fn.return_value = mock_svc

        result = self._fn()(
            case_parties=[party],
            selected_respondents=[{"party_id": 0}],
            preserve_amount=Decimal("10000"),
        )
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _build_primary_respondent_property_clue
# ---------------------------------------------------------------------------


class TestBuildPrimaryRespondentPropertyClue:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _build_primary_respondent_property_clue
        return _build_primary_respondent_property_clue

    @patch("plugins.court_automation.guarantee.helpers._build_selected_respondent_property_clues")
    def test_returns_first_clue(self, mock_build):
        mock_build.return_value = [{"owner_name": "张三", "property_type": "其他"}]
        result = self._fn()(case_parties=[], selected_respondents=[], preserve_amount=None)
        assert result["owner_name"] == "张三"

    @patch("plugins.court_automation.guarantee.helpers._build_selected_respondent_property_clues")
    def test_empty_clues_returns_default(self, mock_build):
        mock_build.return_value = []
        result = self._fn()(case_parties=[], selected_respondents=[], preserve_amount=Decimal("50000"))
        assert result["owner_name"] == "被申请人"
        assert result["property_value"] == "50000"


# ---------------------------------------------------------------------------
# _build_case_quote_context
# ---------------------------------------------------------------------------


class TestBuildCaseQuoteContext:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _build_case_quote_context
        return _build_case_quote_context

    def test_no_preserve_amount(self):
        case = MagicMock()
        case.preservation_amount = None
        assert self._fn()(case=case) is None

    @patch("plugins.court_automation.guarantee.helpers._find_reusable_binding")
    def test_no_binding(self, mock_find):
        case = MagicMock()
        case.preservation_amount = Decimal("100000")
        case.id = 1
        mock_find.return_value = None

        with patch("apps.automation.models.CasePreservationQuoteBinding") as mock_binding_cls:
            mock_binding_cls.objects.select_related.return_value.filter.return_value.order_by.return_value.first.return_value = None
            result = self._fn()(case=case)
        assert result is None

    @patch("plugins.court_automation.guarantee.helpers._find_reusable_binding")
    def test_with_binding_and_items(self, mock_find):
        case = MagicMock()
        case.preservation_amount = Decimal("100000")
        case.id = 1

        item = MagicMock()
        item.id = 10
        item.company_name = "平安"
        item.premium = Decimal("500")
        item.min_amount = Decimal("10000")
        item.max_amount = Decimal("500000")
        item.max_apply_amount = Decimal("500000")
        item.status = "success"
        item.error_message = ""

        quote = MagicMock()
        quote.id = 20
        quote.status = "success"
        quote.error_message = ""
        quote.created_at = datetime(2025, 1, 1)
        quote.finished_at = datetime(2025, 1, 2)
        quote.success_count = 1
        quote.failed_count = 0
        quote.total_companies = 1
        quote.quotes.filter.return_value.order_by.return_value = [item]

        binding = MagicMock()
        binding.id = 30
        binding.preservation_quote = quote
        binding.preserve_amount_snapshot = Decimal("100000")
        mock_find.return_value = binding

        result = self._fn()(case=case)
        assert result is not None
        assert result["binding_id"] == 30
        assert result["quote_id"] == 20
        assert len(result["items"]) == 1
        assert result["items"][0]["is_recommended"] is True


# ---------------------------------------------------------------------------
# _build_reusable_quote_options
# ---------------------------------------------------------------------------


class TestBuildReusableQuoteOptions:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _build_reusable_quote_options
        return _build_reusable_quote_options

    def test_no_preserve_amount(self):
        case = MagicMock()
        case.preservation_amount = None
        assert self._fn()(case=case) == []

    def test_zero_preserve_amount(self):
        case = MagicMock()
        case.preservation_amount = Decimal("0")
        assert self._fn()(case=case) == []

    @patch("apps.automation.models.PreservationQuote")
    @patch("apps.automation.models.CasePreservationQuoteBinding")
    @patch("apps.automation.models.QuoteStatus")
    def test_with_quotes(self, mock_status, mock_binding_cls, mock_quote_cls):
        case = MagicMock()
        case.preservation_amount = Decimal("100000")
        case.id = 1

        mock_binding_cls.objects.filter.return_value.values_list.return_value = [1]
        mock_status.SUCCESS = "success"
        mock_status.PARTIAL_SUCCESS = "partial_success"
        mock_status.RUNNING = "running"
        mock_status.PENDING = "pending"

        quote = MagicMock()
        quote.id = 1
        quote.status = "success"
        quote.success_count = 1
        quote.total_companies = 1
        quote.created_at = datetime(2025, 1, 1)
        quote.preserve_amount = Decimal("100000")
        mock_quote_cls.objects.filter.return_value.filter.return_value.order_by.return_value.__getitem__ = MagicMock(
            return_value=[quote]
        )

        with patch("django.utils.timezone.localtime") as mock_lt:
            mock_lt.return_value.strftime.return_value = "2025-01-01 00:00"
            result = self._fn()(case=case)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# _extract_quote_company_options
# ---------------------------------------------------------------------------


class TestExtractQuoteCompanyOptions:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _extract_quote_company_options
        return _extract_quote_company_options

    def test_none_context(self):
        assert self._fn()(quote_context=None) == []

    def test_empty_dict(self):
        assert self._fn()(quote_context={}) == []

    def test_non_list_items(self):
        assert self._fn()(quote_context={"items": "not a list"}) == []

    def test_success_items_preferred(self):
        ctx = {
            "items": [
                {"company_name": "A", "status": "success"},
                {"company_name": "B", "status": "failed"},
                {"company_name": "C", "status": "success"},
            ]
        }
        result = self._fn()(quote_context=ctx)
        assert result[0] == "A"
        assert result[1] == "C"
        assert result[2] == "B"

    def test_dedup(self):
        ctx = {
            "items": [
                {"company_name": "A", "status": "success"},
                {"company_name": "A", "status": "failed"},
            ]
        }
        result = self._fn()(quote_context=ctx)
        assert result == ["A"]

    def test_empty_company_name_skipped(self):
        ctx = {"items": [{"company_name": "", "status": "success"}]}
        assert self._fn()(quote_context=ctx) == []

    def test_non_dict_item_skipped(self):
        ctx = {"items": ["not a dict", {"company_name": "A", "status": "success"}]}
        result = self._fn()(quote_context=ctx)
        assert result == ["A"]


# ---------------------------------------------------------------------------
# _resolve_insurance_company_defaults
# ---------------------------------------------------------------------------


class TestResolveInsuranceCompanyDefaults:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _resolve_insurance_company_defaults
        return _resolve_insurance_company_defaults

    @patch("plugins.court_automation.guarantee.helpers._extract_quote_company_options")
    def test_with_options_and_recommended(self, mock_extract):
        mock_extract.return_value = ["A", "B"]
        ctx = {"recommended_company": "B"}
        company, options = self._fn()(quote_context=ctx)
        assert company == "B"
        assert options == ["A", "B"]

    @patch("plugins.court_automation.guarantee.helpers._extract_quote_company_options")
    def test_with_options_no_recommended(self, mock_extract):
        mock_extract.return_value = ["A", "B"]
        ctx = {}
        company, options = self._fn()(quote_context=ctx)
        assert company == "A"

    @patch("plugins.court_automation.guarantee.helpers._extract_quote_company_options")
    def test_no_options(self, mock_extract):
        mock_extract.return_value = []
        from plugins.court_automation.guarantee.schemas import (
            _DEFAULT_INSURANCE_COMPANY,
            _GUARANTEE_INSURANCE_COMPANY_OPTIONS,
        )
        company, options = self._fn()(quote_context=None)
        assert company == _DEFAULT_INSURANCE_COMPANY
        assert options == _GUARANTEE_INSURANCE_COMPANY_OPTIONS


# ---------------------------------------------------------------------------
# _build_cause_candidates
# ---------------------------------------------------------------------------


class TestBuildCauseCandidates:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _build_cause_candidates
        return _build_cause_candidates

    def test_empty(self):
        assert self._fn()("") == []

    def test_none(self):
        assert self._fn()(None) == []

    def test_single_cause(self):
        result = self._fn()("借款合同纠纷")
        assert "借款合同纠纷" in result
        assert "借款合同" in result  # removesuffix("纠纷")

    def test_multiple_causes(self):
        result = self._fn()("借款合同纠纷、买卖合同纠纷")
        assert "借款合同纠纷" in result
        assert "买卖合同纠纷" in result

    def test_max_8(self):
        causes = "、".join([f"原因{i}纠纷" for i in range(20)])
        result = self._fn()(causes)
        assert len(result) <= 8

    def test_full_width_space(self):
        result = self._fn()("借款合同纠纷　买卖合同纠纷")
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# _normalize_party_type
# ---------------------------------------------------------------------------


class TestNormalizePartyType:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _normalize_party_type
        return _normalize_party_type

    def test_natural(self):
        assert self._fn()("natural") == "natural"

    def test_person(self):
        assert self._fn()("person") == "natural"

    def test_individual(self):
        assert self._fn()("individual") == "natural"

    def test_legal(self):
        assert self._fn()("legal") == "legal"

    def test_corp(self):
        assert self._fn()("corp") == "legal"

    def test_company(self):
        assert self._fn()("company") == "legal"

    def test_non_legal_org(self):
        assert self._fn()("non_legal_org") == "non_legal_org"

    def test_unknown_defaults_natural(self):
        assert self._fn()("unknown") == "natural"

    def test_none(self):
        assert self._fn()(None) == "natural"


# ---------------------------------------------------------------------------
# _build_party_payload_from_case_party
# ---------------------------------------------------------------------------


class TestBuildPartyPayloadFromCaseParty:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _build_party_payload_from_case_party
        return _build_party_payload_from_case_party

    def test_natural_party(self):
        party = MagicMock()
        party.id = 1
        party.client.client_type = "natural"
        party.client.name = "张三"
        party.client.id_number = "110101199001011234"
        party.client.phone = "13800138000"
        party.client.address = "地址A"
        party.client.legal_representative = ""
        party.client.legal_representative_id_number = ""

        result = self._fn()(party=party)
        assert result["party_type"] == "natural"
        assert result["name"] == "张三"
        assert result["id_number"] == "110101199001011234"

    def test_legal_party_raises_on_empty_id_number(self):
        """Empty id_number should raise ValueError."""
        party = MagicMock()
        party.id = 2
        party.client.client_type = "legal"
        party.client.name = "公司A"
        party.client.id_number = ""
        party.client.phone = ""
        party.client.address = "广州市"
        party.client.legal_representative = "王五"
        party.client.legal_representative_id_number = "110101199001011236"

        with pytest.raises(ValueError, match="客户证件号不能为空"):
            self._fn()(party=party)

    def test_natural_party_empty_id_number_raises(self):
        """Empty id_number should raise ValueError."""
        party = MagicMock()
        party.id = 3
        party.client.client_type = "natural"
        party.client.name = "李四"
        party.client.id_number = ""
        party.client.phone = ""
        party.client.address = "北京市"

        with pytest.raises(ValueError, match="客户证件号不能为空"):
            self._fn()(party=party)

    def test_no_client_raises_value_error(self):
        party = MagicMock()
        party.id = 0
        party.client = None
        with pytest.raises(ValueError, match="客户姓名不能为空"):
            self._fn()(party=party)


# ---------------------------------------------------------------------------
# _list_party_payloads
# ---------------------------------------------------------------------------


class TestListPartyPayloads:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _list_party_payloads
        return _list_party_payloads

    def _make_party(self, status="plaintiff", is_our=True, name="张三"):
        party = MagicMock()
        party.legal_status = status
        party.client.is_our_client = is_our
        party.client.client_type = "natural"
        party.client.name = name
        party.client.id_number = "110101199001011234"
        party.client.phone = "13800138000"
        party.client.address = "地址A"
        party.client.legal_representative = ""
        party.client.legal_representative_id_number = ""
        party.id = 1
        return party

    def test_exact_match(self):
        party = self._make_party("plaintiff", True)
        result = self._fn()(case_parties=[party], preferred_statuses={"plaintiff"}, prefer_our=True)
        assert len(result) == 1

    def test_fallback_to_status_only(self):
        party = self._make_party("plaintiff", False)
        result = self._fn()(case_parties=[party], preferred_statuses={"plaintiff"}, prefer_our=True)
        assert len(result) == 1

    def test_fallback_to_side_only(self):
        party = self._make_party("other_status", True)
        result = self._fn()(case_parties=[party], preferred_statuses={"plaintiff"}, prefer_our=True)
        assert len(result) == 1

    def test_fallback_to_first_party(self):
        party = self._make_party("other_status", False)
        result = self._fn()(case_parties=[party], preferred_statuses={"plaintiff"}, prefer_our=True)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _pick_party_payload
# ---------------------------------------------------------------------------


class TestPickPartyPayload:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _pick_party_payload
        return _pick_party_payload

    @patch("plugins.court_automation.guarantee.helpers._list_party_payloads")
    def test_returns_first(self, mock_list):
        mock_list.return_value = [{"name": "A"}, {"name": "B"}]
        result = self._fn()(case_parties=[], preferred_statuses=set(), prefer_our=True)
        assert result["name"] == "A"

    @patch("plugins.court_automation.guarantee.helpers._list_party_payloads")
    def test_empty_returns_default(self, mock_list):
        mock_list.return_value = []
        with pytest.raises(ValueError, match="客户姓名不能为空"):
            self._fn()(case_parties=[], preferred_statuses=set(), prefer_our=True)


# ---------------------------------------------------------------------------
# _normalize_selected_party_ids
# ---------------------------------------------------------------------------


class TestNormalizeSelectedPartyIds:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _normalize_selected_party_ids
        return _normalize_selected_party_ids

    def test_none(self):
        assert self._fn()(None) is None

    def test_empty_list(self):
        assert self._fn()([]) == set()

    def test_valid_ids(self):
        assert self._fn()([1, 2, 3]) == {1, 2, 3}

    def test_zero_excluded(self):
        assert self._fn()([0, 1, -1]) == {1}

    def test_invalid_type_skipped(self):
        assert self._fn()([1, "abc", 2]) == {1, 2}


# ---------------------------------------------------------------------------
# _list_opponent_case_parties
# ---------------------------------------------------------------------------


class TestListOpponentCaseParties:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _list_opponent_case_parties
        return _list_opponent_case_parties

    def test_our_client_excluded(self):
        party = MagicMock()
        party.client.is_our_client = True
        result = self._fn()(case_parties=[party])
        # Our client excluded, fallback to respondent statuses
        # Since no respondent-status match, returns all parties
        assert len(result) == 1

    def test_opponent_returned(self):
        party = MagicMock()
        party.client.is_our_client = False
        party.legal_status = "defendant"
        result = self._fn()(case_parties=[party])
        assert len(result) == 1

    def test_fallback_to_respondent_statuses(self):
        party = MagicMock()
        party.client.is_our_client = True
        party.legal_status = "defendant"
        result = self._fn()(case_parties=[party])
        # No opponents, fallback to respondent statuses
        assert len(result) == 1

    def test_fallback_to_all(self):
        party = MagicMock()
        party.client.is_our_client = True
        party.legal_status = "other"
        result = self._fn()(case_parties=[party])
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _list_opponent_party_payloads
# ---------------------------------------------------------------------------


class TestListOpponentPartyPayloads:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _list_opponent_party_payloads
        return _list_opponent_party_payloads

    @patch("plugins.court_automation.guarantee.helpers._list_opponent_case_parties")
    @patch("plugins.court_automation.guarantee.helpers._build_party_payload_from_case_party")
    def test_delegates(self, mock_build, mock_list):
        mock_list.return_value = [MagicMock()]
        mock_build.return_value = {"name": "test"}
        result = self._fn()(case_parties=[])
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _build_respondent_options
# ---------------------------------------------------------------------------


class TestBuildRespondentOptions:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _build_respondent_options
        return _build_respondent_options

    @patch("plugins.court_automation.guarantee.helpers._list_opponent_case_parties")
    def test_builds_options(self, mock_list):
        party = MagicMock()
        party.id = 1
        party.legal_status = "defendant"
        party.client.name = "被告A"
        party.client.is_our_client = False
        party.get_legal_status_display.return_value = "被告"
        mock_list.return_value = [party]

        result = self._fn()(case_parties=[party])
        assert len(result) == 1
        assert result[0]["name"] == "被告A"
        assert result[0]["party_id"] == 1


# ---------------------------------------------------------------------------
# _build_plaintiff_agent_payload
# ---------------------------------------------------------------------------


class TestBuildPlaintiffAgentPayload:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _build_plaintiff_agent_payload
        return _fn

    def _fn_import(self):
        from plugins.court_automation.guarantee.helpers import _build_plaintiff_agent_payload
        return _build_plaintiff_agent_payload

    def test_lawyer_found_by_requester_id(self):
        case = MagicMock()
        lawyer = MagicMock()
        lawyer.real_name = "律师A"
        lawyer.username = "lv_a"
        lawyer.id_card = "110101199001011234"
        lawyer.phone = "13800138000"
        firm = MagicMock()
        firm.name = "律所A"
        lawyer.law_firm = firm
        lawyer.license_no = "12345"

        with patch("apps.organization.models.Lawyer") as mock_cls:
            mock_cls.objects.select_related.return_value.filter.return_value.first.return_value = lawyer
            result = self._fn_import()(case=case, requester_id=1, fallback_party={"name": "张三", "phone": "139"})
        assert result["name"] == "律师A"
        assert result["law_firm"] == "律所A"

    def test_no_lawyer_uses_fallback(self):
        case = MagicMock()
        case.assignments.select_related.return_value.order_by.return_value.first.return_value = None

        with patch("apps.organization.models.Lawyer") as mock_cls:
            mock_cls.objects.select_related.return_value.filter.return_value.first.return_value = None
            result = self._fn_import()(case=case, requester_id=None, fallback_party={"name": "张三", "phone": "139"})
        assert result["name"] == "张三"
        assert result["party_type"] == "agent"

    def test_lawyer_from_assignment(self):
        case = MagicMock()
        lawyer = MagicMock()
        lawyer.real_name = "律师B"
        lawyer.username = ""
        lawyer.id_card = ""
        lawyer.phone = ""
        firm = MagicMock()
        firm.name = "律所B"
        lawyer.law_firm = firm
        lawyer.license_no = ""
        assignment = MagicMock()
        assignment.lawyer = lawyer
        case.assignments.select_related.return_value.order_by.return_value.first.return_value = assignment

        with patch("apps.organization.models.Lawyer") as mock_cls:
            mock_cls.objects.select_related.return_value.filter.return_value.first.return_value = None
            result = self._fn_import()(case=case, requester_id=None, fallback_party={"name": "张三", "phone": "139"})
        assert result["name"] == "律师B"

    def test_empty_fallback_name(self):
        case = MagicMock()
        case.assignments.select_related.return_value.order_by.return_value.first.return_value = None

        with patch("apps.organization.models.Lawyer") as mock_cls:
            mock_cls.objects.select_related.return_value.filter.return_value.first.return_value = None
            result = self._fn_import()(case=case, requester_id=None, fallback_party={"name": "", "phone": ""})
        assert result["name"] == "张三"


# ---------------------------------------------------------------------------
# _build_session_status_payload (guarantee version)
# ---------------------------------------------------------------------------


class TestGuaranteeBuildSessionStatusPayload:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _build_session_status_payload
        return _build_session_status_payload

    def test_pending(self):
        task = MagicMock()
        task.id = 1
        task.status = "pending"
        task.result = {"message": "执行中", "timing": {"t": 1}}
        task.error_message = ""
        with patch("apps.automation.models.ScraperTaskStatus") as s:
            s.PENDING = "pending"
            s.RUNNING = "running"
            result = self._fn()(task=task)
        assert result["status"] == "in_progress"
        assert result["timing"] == {"t": 1}

    def test_success(self):
        task = MagicMock()
        task.id = 2
        task.status = "success"
        task.result = {"message": "完成"}
        task.error_message = ""
        with patch("apps.automation.models.ScraperTaskStatus") as s:
            s.SUCCESS = "success"
            result = self._fn()(task=task)
        assert result["status"] == "completed"

    def test_failed_with_error_message(self):
        task = MagicMock()
        task.id = 3
        task.status = "failed"
        task.result = {}
        task.error_message = "错误"
        with patch("apps.automation.models.ScraperTaskStatus") as s:
            s.PENDING = "pending"
            s.RUNNING = "running"
            s.SUCCESS = "success"
            result = self._fn()(task=task)
        assert result["status"] == "failed"
        assert "错误" in result["message"]

    def test_failed_default_message(self):
        task = MagicMock()
        task.id = 4
        task.status = "failed"
        task.result = None
        task.error_message = ""
        with patch("apps.automation.models.ScraperTaskStatus") as s:
            s.PENDING = "pending"
            s.RUNNING = "running"
            s.SUCCESS = "success"
            result = self._fn()(task=task)
        assert result["message"] == "担保失败"

    def test_failed_with_result_message(self):
        task = MagicMock()
        task.id = 5
        task.status = "failed"
        task.result = {"message": "自定义错误"}
        task.error_message = ""
        with patch("apps.automation.models.ScraperTaskStatus") as s:
            s.PENDING = "pending"
            s.RUNNING = "running"
            s.SUCCESS = "success"
            result = self._fn()(task=task)
        assert "自定义错误" in result["message"]

    def test_pending_non_dict_result(self):
        task = MagicMock()
        task.id = 6
        task.status = "pending"
        task.result = "not a dict"
        task.error_message = ""
        with patch("apps.automation.models.ScraperTaskStatus") as s:
            s.PENDING = "pending"
            s.RUNNING = "running"
            result = self._fn()(task=task)
        assert result["message"] == "担保任务执行中..."


# ---------------------------------------------------------------------------
# _update_session_task (guarantee version)
# ---------------------------------------------------------------------------


class TestGuaranteeUpdateSessionTask:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _update_session_task
        return _update_session_task

    def test_none_session_id(self):
        self._fn()(session_id=None, status="running")

    @patch("plugins.court_automation.guarantee.helpers.asyncio.get_running_loop")
    @patch("plugins.court_automation.guarantee.helpers._SESSION_UPDATE_EXECUTOR")
    def test_with_event_loop(self, mock_executor, mock_loop):
        mock_loop.return_value = MagicMock()
        self._fn()(session_id=1, status="running", set_started=True)
        mock_executor.submit.assert_called_once()

    @patch("plugins.court_automation.guarantee.helpers.asyncio.get_running_loop", side_effect=RuntimeError)
    def test_no_event_loop_sync(self, mock_loop):
        with patch("apps.automation.models.ScraperTask") as mock_task:
            mock_task.objects.filter.return_value.update.return_value = 1
            with patch("django.db.close_old_connections"):
                self._fn()(session_id=1, status="running", error_message="err")
            mock_task.objects.filter.assert_called_once_with(id=1)


# ---------------------------------------------------------------------------
# _get_organization_service / _get_client_service
# ---------------------------------------------------------------------------


class TestServiceGetters:
    def test_get_organization_service(self):
        from plugins.court_automation.guarantee.helpers import _get_organization_service
        with patch("apps.core.dependencies.build_organization_service", return_value="svc"):
            assert _get_organization_service() == "svc"

    def test_get_client_service(self):
        from plugins.court_automation.guarantee.helpers import _get_client_service
        with patch("apps.core.dependencies.build_client_service", return_value="svc"):
            assert _get_client_service() == "svc"


# ---------------------------------------------------------------------------
# _find_reusable_binding
# ---------------------------------------------------------------------------


class TestFindReusableBinding:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _find_reusable_binding
        return _fn

    def _fn_import(self):
        from plugins.court_automation.guarantee.helpers import _find_reusable_binding
        return _find_reusable_binding

    @patch("apps.automation.models.CasePreservationQuoteBinding")
    def test_found(self, mock_cls):
        mock_cls.objects.select_related.return_value.filter.return_value.order_by.return_value.first.return_value = "binding"
        result = self._fn_import()(case_id=1, preserve_amount=Decimal("100000"))
        assert result == "binding"

    @patch("apps.automation.models.CasePreservationQuoteBinding")
    def test_not_found(self, mock_cls):
        mock_cls.objects.select_related.return_value.filter.return_value.order_by.return_value.first.return_value = None
        result = self._fn_import()(case_id=1, preserve_amount=Decimal("100000"))
        assert result is None
