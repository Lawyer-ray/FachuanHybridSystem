"""Additional coverage tests for court_guarantee_helpers uncovered branches."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

try:
    from plugins.court_automation import filing
except ImportError:
    pytest.skip("court_automation plugin not installed", allow_module_level=True)



class TestBuildGuaranteeMaterialPaths:
    """Cover _build_guarantee_material_paths branches."""

    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _build_guarantee_material_paths
        return _build_guarantee_material_paths

    def _make_qs(self, materials):
        """Build a mock queryset chain: filter().select_related().order_by() -> materials."""
        ordered = MagicMock()
        ordered.__iter__ = MagicMock(return_value=iter(materials))

        select = MagicMock()
        select.order_by.return_value = ordered

        filter2 = MagicMock()
        filter2.select_related.return_value = select

        filter1 = MagicMock()
        filter1.filter.return_value = filter2
        return filter1

    @patch("apps.cases.models.CaseMaterial")
    @patch("apps.cases.models.CaseMaterialCategory")
    @patch("apps.cases.models.CaseMaterialSide")
    def test_empty_materials(self, mock_side, mock_cat, mock_cm):
        case = MagicMock()

        our_qs = self._make_qs([])
        non_qs = self._make_qs([])

        mock_cm.objects.filter.side_effect = [our_qs, non_qs]
        result = self._fn()(case=case)
        assert result == []

    @patch("apps.cases.models.CaseMaterial")
    @patch("apps.cases.models.CaseMaterialCategory")
    @patch("apps.cases.models.CaseMaterialSide")
    def test_picks_required_materials(self, mock_side, mock_cat, mock_cm):
        case = MagicMock()

        def make_material(mid, type_name, path):
            m = MagicMock()
            m.id = mid
            m.type_name = type_name
            attachment = MagicMock()
            attachment.file.path = path
            attachment.original_filename = Path(path).name
            m.source_attachment = attachment
            return m

        our_files = [
            make_material(1, "保全申请书", "/test/保全申请书.pdf"),
            make_material(2, "起诉状", "/test/起诉状.pdf"),
            make_material(3, "身份证明", "/test/身份证.pdf"),
            make_material(4, "证据材料", "/test/证据.pdf"),
        ]
        non_files = [
            make_material(5, "立案受理通知书", "/test/通知书.pdf"),
        ]

        our_qs = self._make_qs(our_files)
        non_qs = self._make_qs(non_files)

        mock_cm.objects.filter.side_effect = [our_qs, non_qs]

        with patch("pathlib.Path.exists", return_value=True):
            result = self._fn()(case=case)
        assert len(result) >= 4
        assert any("保全" in item["type_name"] for item in result)

    @patch("apps.cases.models.CaseMaterial")
    @patch("apps.cases.models.CaseMaterialCategory")
    @patch("apps.cases.models.CaseMaterialSide")
    def test_capped_at_12(self, mock_side, mock_cat, mock_cm):
        case = MagicMock()

        our_files = []
        for i in range(15):
            m = MagicMock()
            m.id = i
            m.type_name = f"材料{i}"
            attachment = MagicMock()
            attachment.file.path = f"/test/doc{i}.pdf"
            attachment.original_filename = f"doc{i}.pdf"
            m.source_attachment = attachment
            our_files.append(m)

        our_qs = self._make_qs(our_files)
        non_qs = self._make_qs([])

        mock_cm.objects.filter.side_effect = [our_qs, non_qs]

        with patch("pathlib.Path.exists", return_value=True):
            result = self._fn()(case=case)
        assert len(result) <= 12

    @patch("apps.cases.models.CaseMaterial")
    @patch("apps.cases.models.CaseMaterialCategory")
    @patch("apps.cases.models.CaseMaterialSide")
    def test_skips_non_allowed_suffix(self, mock_side, mock_cat, mock_cm):
        case = MagicMock()

        m = MagicMock()
        m.id = 1
        m.type_name = "测试"
        attachment = MagicMock()
        attachment.file.path = "/test/file.txt"
        attachment.original_filename = "file.txt"
        m.source_attachment = attachment

        our_qs = self._make_qs([m])
        non_qs = self._make_qs([])

        mock_cm.objects.filter.side_effect = [our_qs, non_qs]

        with patch("pathlib.Path.exists", return_value=True):
            result = self._fn()(case=case)
        assert result == []

    @patch("apps.cases.models.CaseMaterial")
    @patch("apps.cases.models.CaseMaterialCategory")
    @patch("apps.cases.models.CaseMaterialSide")
    def test_skips_file_not_exists(self, mock_side, mock_cat, mock_cm):
        case = MagicMock()

        m = MagicMock()
        m.id = 1
        m.type_name = "测试"
        attachment = MagicMock()
        attachment.file.path = "/test/missing.pdf"
        attachment.original_filename = "missing.pdf"
        m.source_attachment = attachment

        our_qs = self._make_qs([m])
        non_qs = self._make_qs([])

        mock_cm.objects.filter.side_effect = [our_qs, non_qs]

        with patch("pathlib.Path.exists", return_value=False):
            result = self._fn()(case=case)
        assert result == []

    @patch("apps.cases.models.CaseMaterial")
    @patch("apps.cases.models.CaseMaterialCategory")
    @patch("apps.cases.models.CaseMaterialSide")
    def test_skips_none_attachment(self, mock_side, mock_cat, mock_cm):
        case = MagicMock()

        m = MagicMock()
        m.id = 1
        m.type_name = "测试"
        m.source_attachment = None

        our_qs = self._make_qs([m])
        non_qs = self._make_qs([])

        mock_cm.objects.filter.side_effect = [our_qs, non_qs]

        result = self._fn()(case=case)
        assert result == []

    @patch("apps.cases.models.CaseMaterial")
    @patch("apps.cases.models.CaseMaterialCategory")
    @patch("apps.cases.models.CaseMaterialSide")
    def test_original_name_fallback(self, mock_side, mock_cat, mock_cm):
        case = MagicMock()

        m = MagicMock()
        m.id = 1
        m.type_name = "测试"
        attachment = MagicMock()
        attachment.file.path = "/test/file.pdf"
        attachment.original_filename = ""
        m.source_attachment = attachment

        our_qs = self._make_qs([m])
        non_qs = self._make_qs([])

        mock_cm.objects.filter.side_effect = [our_qs, non_qs]

        with patch("pathlib.Path.exists", return_value=True):
            result = self._fn()(case=case)
        assert len(result) == 1
        assert result[0]["original_name"] == "file.pdf"


class TestBuildCauseCandidates:
    """Cover _build_cause_candidates edge cases."""

    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _build_cause_candidates
        return _build_cause_candidates

    def test_empty_input(self):
        assert self._fn()("") == []

    def test_single_cause(self):
        result = self._fn()("借款合同纠纷")
        assert "借款合同纠纷" in result
        assert "借款合同" in result  # removed suffix

    def test_multiple_causes_split(self):
        result = self._fn()("借款合同纠纷、保证合同纠纷")
        assert len(result) >= 2

    def test_full_width_space(self):
        result = self._fn()("借款合同纠纷　保证合同纠纷")
        assert len(result) >= 1

    def test_max_8(self):
        cause = "、".join([f"原因{i}纠纷" for i in range(20)])
        result = self._fn()(cause)
        assert len(result) <= 8


class TestNormalizePartyType:
    """Cover _normalize_party_type."""

    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _normalize_party_type
        return _normalize_party_type

    def test_person(self):
        assert self._fn()("person") == "natural"

    def test_individual(self):
        assert self._fn()("individual") == "natural"

    def test_corp(self):
        assert self._fn()("corp") == "legal"

    def test_company(self):
        assert self._fn()("company") == "legal"

    def test_enterprise(self):
        assert self._fn()("enterprise") == "legal"

    def test_organization(self):
        assert self._fn()("organization") == "legal"

    def test_org(self):
        assert self._fn()("org") == "legal"

    def test_non_legal_org(self):
        assert self._fn()("non_legal_org") == "non_legal_org"

    def test_nonlegal(self):
        assert self._fn()("nonlegal") == "non_legal_org"

    def test_non_legal(self):
        assert self._fn()("non_legal") == "non_legal_org"

    def test_other_org(self):
        assert self._fn()("other_org") == "non_legal_org"

    def test_none_defaults_natural(self):
        assert self._fn()(None) == "natural"

    def test_empty_defaults_natural(self):
        assert self._fn()("") == "natural"

    def test_unknown_defaults_natural(self):
        assert self._fn()("alien") == "natural"


class TestBuildPartyPayloadFromCaseParty:
    """Cover _build_party_payload_from_case_party edge cases."""

    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _build_party_payload_from_case_party
        return _build_party_payload_from_case_party

    def test_natural_party_defaults(self):
        """Empty name should raise ValueError."""
        party = MagicMock()
        party.id = 1
        client = MagicMock()
        client.client_type = "natural"
        client.name = ""
        client.id_number = ""
        client.phone = ""
        client.address = ""
        client.legal_representative = ""
        client.legal_representative_id_number = ""
        party.client = client

        with pytest.raises(ValueError, match="客户姓名不能为空"):
            self._fn()(party=party)

    def test_legal_party_raises_on_empty_fields(self):
        """Empty id_number and address should raise ValueError."""
        party = MagicMock()
        party.id = 2
        client = MagicMock()
        client.client_type = "legal"
        client.name = "公司"
        client.id_number = ""
        client.phone = ""
        client.address = ""
        client.legal_representative = ""
        client.legal_representative_id_number = ""
        party.client = client

        with pytest.raises(ValueError, match="客户证件号不能为空"):
            self._fn()(party=party)

    def test_none_party(self):
        with pytest.raises(ValueError, match="客户姓名不能为空"):
            self._fn()(party=None)


class TestListPartyPayloads:
    """Cover _list_party_payloads fallbacks."""

    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _list_party_payloads
        return _list_party_payloads

    def test_status_and_side_match(self):
        party = MagicMock()
        party.legal_status = "defendant"
        client = MagicMock()
        client.client_type = "natural"
        client.name = "被告"
        client.id_number = "440100199001010001"
        client.phone = "13800138000"
        client.address = "addr"
        client.is_our_client = False
        client.legal_representative = ""
        client.legal_representative_id_number = ""
        party.client = client

        result = self._fn()(
            case_parties=[party],
            preferred_statuses={"defendant"},
            prefer_our=False,
        )
        assert len(result) == 1

    def test_fallback_to_status_only(self):
        party = MagicMock()
        party.legal_status = "defendant"
        client = MagicMock()
        client.client_type = "natural"
        client.name = "被告"
        client.id_number = "440100199001010001"
        client.phone = "13800138000"
        client.address = "广州市"
        client.is_our_client = True  # wrong side
        client.legal_representative = ""
        client.legal_representative_id_number = ""
        party.client = client

        result = self._fn()(
            case_parties=[party],
            preferred_statuses={"defendant"},
            prefer_our=False,
        )
        assert len(result) == 1

    def test_fallback_to_side_only(self):
        party = MagicMock()
        party.legal_status = "plaintiff"  # wrong status
        client = MagicMock()
        client.client_type = "natural"
        client.name = "原告"
        client.id_number = "440100199001010002"
        client.phone = "13800138001"
        client.address = "深圳市"
        client.is_our_client = False
        client.legal_representative = ""
        client.legal_representative_id_number = ""
        party.client = client

        result = self._fn()(
            case_parties=[party],
            preferred_statuses={"defendant"},
            prefer_our=False,
        )
        assert len(result) == 1

    def test_fallback_to_first(self):
        party = MagicMock()
        party.legal_status = "plaintiff"
        client = MagicMock()
        client.client_type = "natural"
        client.name = "原告"
        client.id_number = "440100199001010003"
        client.phone = "13800138002"
        client.address = "佛山市"
        client.is_our_client = True
        client.legal_representative = ""
        client.legal_representative_id_number = ""
        party.client = client

        result = self._fn()(
            case_parties=[party],
            preferred_statuses={"defendant"},
            prefer_our=True,  # wrong side match
        )
        assert len(result) == 1


class TestPickPartyPayload:
    """Cover _pick_party_payload empty case."""

    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _pick_party_payload
        return _pick_party_payload

    def test_empty_parties_raises_value_error(self):
        with pytest.raises(ValueError, match="客户姓名不能为空"):
            self._fn()(
                case_parties=[],
                preferred_statuses={"defendant"},
                prefer_our=False,
            )


class TestListOpponentCaseParties:
    """Cover _list_opponent_case_parties fallbacks."""

    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _list_opponent_case_parties
        return _list_opponent_case_parties

    def test_opponents_found(self):
        party = MagicMock()
        client = MagicMock()
        client.is_our_client = False
        party.client = client
        result = self._fn()(case_parties=[party])
        assert len(result) == 1

    def test_fallback_to_respondent_status(self):
        party = MagicMock()
        party.legal_status = "defendant"
        client = MagicMock()
        client.is_our_client = True
        party.client = client
        result = self._fn()(case_parties=[party])
        assert len(result) == 1

    def test_fallback_to_all_parties(self):
        party = MagicMock()
        party.legal_status = "plaintiff"
        client = MagicMock()
        client.is_our_client = True
        party.client = client
        result = self._fn()(case_parties=[party])
        assert len(result) == 1


class TestExtractQuoteCompanyOptions:
    """Cover _extract_quote_company_options branches."""

    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _extract_quote_company_options
        return _extract_quote_company_options

    def test_none_context(self):
        assert self._fn()(quote_context=None) == []

    def test_empty_context(self):
        assert self._fn()(quote_context={}) == []

    def test_items_not_list(self):
        assert self._fn()(quote_context={"items": "not_list"}) == []

    def test_success_items_preferred(self):
        ctx = {
            "items": [
                {"company_name": "公司A", "status": "success"},
                {"company_name": "公司B", "status": "failed"},
                {"company_name": "公司C", "status": "success"},
            ]
        }
        result = self._fn()(quote_context=ctx)
        assert result[0] == "公司A"

    def test_dedup(self):
        ctx = {
            "items": [
                {"company_name": "公司A", "status": "success"},
                {"company_name": "公司A", "status": "failed"},
            ]
        }
        result = self._fn()(quote_context=ctx)
        assert result.count("公司A") == 1

    def test_non_dict_item_skipped(self):
        ctx = {"items": ["not_a_dict", {"company_name": "公司A", "status": "success"}]}
        result = self._fn()(quote_context=ctx)
        assert "公司A" in result

    def test_empty_company_name_skipped(self):
        ctx = {"items": [{"company_name": "", "status": "success"}]}
        result = self._fn()(quote_context=ctx)
        assert result == []


class TestResolveInsuranceCompanyDefaults:
    """Cover _resolve_insurance_company_defaults branches."""

    def _fn_import(self):
        from plugins.court_automation.guarantee.helpers import _resolve_insurance_company_defaults
        return _resolve_insurance_company_defaults

    def test_no_quote_returns_defaults(self):
        company, options = self._fn_import()(quote_context=None)
        assert company == "中国平安财产保险股份有限公司"

    def test_recommended_in_options(self):
        ctx = {
            "recommended_company": "公司A",
            "items": [
                {"company_name": "公司A", "status": "success"},
                {"company_name": "公司B", "status": "failed"},
            ],
        }
        company, options = self._fn_import()(quote_context=ctx)
        assert company == "公司A"

    def test_recommended_not_in_options_fallback(self):
        ctx = {
            "recommended_company": "不存在",
            "items": [
                {"company_name": "公司A", "status": "success"},
            ],
        }
        company, options = self._fn_import()(quote_context=ctx)
        assert company == "公司A"


class TestNormalizePropertyClueContent:
    """Cover _normalize_property_clue_content edge cases."""

    def _fn_import(self):
        from plugins.court_automation.guarantee.helpers import _normalize_property_clue_content
        return _normalize_property_clue_content

    def test_multiline_joins_with_semicolon(self):
        result = self._fn_import()("line1\nline2\nline3")
        assert result == "line1；line2；line3"

    def test_empty_lines_filtered(self):
        result = self._fn_import()("line1\n\n  \nline2")
        assert result == "line1；line2"

    def test_all_empty_lines(self):
        result = self._fn_import()("\n\n  \n")
        assert result == ""


class TestBuildPropertyClueInfo:
    """Cover _build_property_clue_info edge cases."""

    def _fn_import(self):
        from plugins.court_automation.guarantee.helpers import _build_property_clue_info
        return _build_property_clue_info

    def test_known_type_with_content(self):
        result = self._fn_import()(clue_type="bank", raw_content="工商银行\n6222")
        assert "银行账户" in result

    def test_unknown_type_with_content(self):
        result = self._fn_import()(clue_type="unknown", raw_content="线索内容")
        assert "unknown" in result

    def test_empty_type_defaults(self):
        result = self._fn_import()(clue_type="", raw_content="内容")
        assert "财产线索" in result

    def test_empty_content(self):
        result = self._fn_import()(clue_type="bank", raw_content="")
        assert result == "银行账户"


class TestNormalizePropertyValue:
    """Cover _normalize_property_value edge cases."""

    def _fn_import(self):
        from plugins.court_automation.guarantee.helpers import _normalize_property_value
        return _normalize_property_value

    def test_none(self):
        assert self._fn_import()(None) == ""

    def test_strips_trailing_zeros(self):
        assert self._fn_import()("100000.00") == "100000"

    def test_strips_dot(self):
        assert self._fn_import()("100000.") == "100000"

    def test_removes_commas(self):
        assert self._fn_import()("1,000,000") == "1000000"

    def test_integer_string(self):
        assert self._fn_import()("500000") == "500000"


class TestParsePreserveAmount:
    """Cover _parse_preserve_amount edge cases."""

    def _fn_import(self):
        from plugins.court_automation.guarantee.helpers import _parse_preserve_amount
        return _parse_preserve_amount

    def test_none(self):
        assert self._fn_import()(None) is None

    def test_decimal_passthrough(self):
        assert self._fn_import()(Decimal("100000")) == Decimal("100000")

    def test_string_number(self):
        assert self._fn_import()("50000") == Decimal("50000")

    def test_invalid_string(self):
        assert self._fn_import()("not_a_number") is None

    def test_none_type(self):
        assert self._fn_import()(None) is None


class TestGetCaseCourtNameBranches:
    """Cover _get_case_court_name branches."""

    def _fn_import(self):
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

        with patch("apps.core.models.enums.AuthorityType") as mock_enum:
            mock_enum.TRIAL = "trial"
            with patch("plugins.court_automation.guarantee.helpers._resolve_court_name", return_value="广州市天河区人民法院"):
                result = self._fn_import()(case=case)
        assert result == "广州市天河区人民法院"

    def test_any_named_authority_fallback(self):
        case = MagicMock()
        authority = MagicMock()
        authority.name = "海珠区"
        authority.authority_type = "other"

        qs = MagicMock()
        qs.filter.return_value.first.return_value = None
        qs.exclude.return_value.exclude.return_value.first.return_value = authority
        case.supervising_authorities.all.return_value.order_by.return_value = qs

        with patch("apps.core.models.enums.AuthorityType") as mock_enum:
            mock_enum.TRIAL = "trial"
            with patch("plugins.court_automation.guarantee.helpers._resolve_court_name", return_value="广州市海珠区人民法院"):
                result = self._fn_import()(case=case)
        assert result == "广州市海珠区人民法院"

    def test_no_authority_returns_none(self):
        case = MagicMock()
        qs = MagicMock()
        qs.filter.return_value.first.return_value = None
        qs.exclude.return_value.exclude.return_value.first.return_value = None
        case.supervising_authorities.all.return_value.order_by.return_value = qs

        with patch("apps.core.models.enums.AuthorityType") as mock_enum:
            mock_enum.TRIAL = "trial"
            result = self._fn_import()(case=case)
        assert result is None


class TestResolveCourtNameGuarantee:
    """Cover guarantee _resolve_court_name edge cases."""

    def _fn_import(self):
        from plugins.court_automation.guarantee.helpers import _resolve_court_name
        return _resolve_court_name

    def test_court_not_found_appends(self):
        with patch("apps.core.models.Court") as mock_court:
            mock_court.objects.filter.return_value.first.return_value = None
            result = self._fn_import()("不存在ABC")
        assert result == "不存在ABC人民法院"


class TestNormalizeConsultantCode:
    """Cover _normalize_consultant_code."""

    def _fn_import(self):
        from plugins.court_automation.guarantee.helpers import _normalize_consultant_code
        return _normalize_consultant_code

    def test_sunshine_default_code(self):
        result = self._fn_import()(
            insurance_company_name="阳光财产保险股份有限公司",
            consultant_code=None,
        )
        assert result == "08740007"

    def test_sunshine_custom_code(self):
        result = self._fn_import()(
            insurance_company_name="阳光财产保险股份有限公司",
            consultant_code="12345",
        )
        assert result == "12345"

    def test_other_company_empty(self):
        result = self._fn_import()(
            insurance_company_name="其他公司",
            consultant_code=None,
        )
        assert result == ""


class TestNormalizeInsuranceCompany:
    """Cover _normalize_insurance_company."""

    def _fn_import(self):
        from plugins.court_automation.guarantee.helpers import _normalize_insurance_company
        return _normalize_insurance_company

    def test_empty_with_allowed_options(self):
        result = self._fn_import()("", allowed_options=["公司A", "公司B"])
        assert result == "公司A"

    def test_empty_without_allowed_options(self):
        result = self._fn_import()("")
        assert result == "中国平安财产保险股份有限公司"

    def test_allowed_options_match(self):
        result = self._fn_import()("公司B", allowed_options=["公司A", "公司B"])
        assert result == "公司B"

    def test_allowed_options_no_match(self):
        result = self._fn_import()("公司C", allowed_options=["公司A", "公司B"])
        assert result == "公司A"

    def test_in_default_options(self):
        result = self._fn_import()("中国平安财产保险股份有限公司")
        assert result == "中国平安财产保险股份有限公司"

    def test_not_in_default_options(self):
        result = self._fn_import()("不存在的公司")
        assert result == "中国平安财产保险股份有限公司"


class TestNormalizeSelectedPartyIds:
    """Cover _normalize_selected_party_ids."""

    def _fn_import(self):
        from plugins.court_automation.guarantee.helpers import _normalize_selected_party_ids
        return _normalize_selected_party_ids

    def test_none_returns_none(self):
        assert self._fn_import()(None) is None

    def test_filters_invalid(self):
        result = self._fn_import()([1, 0, -1, "abc", 3])
        assert result == {1, 3}

    def test_empty_list(self):
        result = self._fn_import()([])
        assert result == set()
