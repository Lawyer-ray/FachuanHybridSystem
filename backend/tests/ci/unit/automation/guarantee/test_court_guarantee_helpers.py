"""court_guarantee_helpers.py 单元测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from decimal import Decimal

import pytest
try:
    from plugins.court_automation import filing
except ImportError:
    pytest.skip("court_automation plugin not installed", allow_module_level=True)



# ── _resolve_court_name ──────────────────────────────────────────────────────

class TestResolveCourtNameGuarantee:

    def test_already_has_renmin(self):
        from plugins.court_automation.guarantee.helpers import _resolve_court_name
        assert _resolve_court_name("广州市天河区人民法院") == "广州市天河区人民法院"

    def test_empty_returns_none(self):
        from plugins.court_automation.guarantee.helpers import _resolve_court_name
        assert _resolve_court_name("") is None
        assert _resolve_court_name(None) is None

    @patch("apps.core.models.Court")
    def test_looks_up_court(self, MockCourt):
        from plugins.court_automation.guarantee.helpers import _resolve_court_name
        MockCourt.objects.filter.return_value.first.return_value = SimpleNamespace(name="广州市天河区人民法院")
        assert _resolve_court_name("天河区") == "广州市天河区人民法院"

    @patch("apps.core.models.Court")
    def test_appends_renmin_when_not_found(self, MockCourt):
        from plugins.court_automation.guarantee.helpers import _resolve_court_name
        MockCourt.objects.filter.return_value.first.return_value = None
        assert _resolve_court_name("天河区") == "天河区人民法院"


# ── _normalize_insurance_company ─────────────────────────────────────────────

class TestNormalizeInsuranceCompany:

    def test_empty_returns_default(self):
        from plugins.court_automation.guarantee.helpers import _normalize_insurance_company
        result = _normalize_insurance_company("")
        assert result  # 不为空

    def test_known_company_returns_self(self):
        from plugins.court_automation.guarantee.helpers import (
            _normalize_insurance_company,
            _GUARANTEE_INSURANCE_COMPANY_OPTIONS,
        )
        if _GUARANTEE_INSURANCE_COMPANY_OPTIONS:
            name = _GUARANTEE_INSURANCE_COMPANY_OPTIONS[0]
            assert _normalize_insurance_company(name) == name

    def test_unknown_company_returns_default(self):
        from plugins.court_automation.guarantee.helpers import _normalize_insurance_company
        result = _normalize_insurance_company("未知保险公司XYZ")
        assert result  # 返回默认值

    def test_allowed_options_fallback(self):
        from plugins.court_automation.guarantee.helpers import _normalize_insurance_company
        result = _normalize_insurance_company("未知", allowed_options=["A保险", "B保险"])
        assert result == "A保险"

    def test_allowed_options_exact_match(self):
        from plugins.court_automation.guarantee.helpers import _normalize_insurance_company
        result = _normalize_insurance_company("B保险", allowed_options=["A保险", "B保险"])
        assert result == "B保险"


# ── _parse_preserve_amount ───────────────────────────────────────────────────

class TestParsePreserveAmount:

    def test_none_returns_none(self):
        from plugins.court_automation.guarantee.helpers import _parse_preserve_amount
        assert _parse_preserve_amount(None) is None

    def test_decimal_passthrough(self):
        from plugins.court_automation.guarantee.helpers import _parse_preserve_amount
        assert _parse_preserve_amount(Decimal("1000.50")) == Decimal("1000.50")

    def test_string_to_decimal(self):
        from plugins.court_automation.guarantee.helpers import _parse_preserve_amount
        assert _parse_preserve_amount("5000") == Decimal("5000")

    def test_invalid_returns_none(self):
        from plugins.court_automation.guarantee.helpers import _parse_preserve_amount
        assert _parse_preserve_amount("abc") is None
        assert _parse_preserve_amount([1, 2]) is None


# ── _normalize_consultant_code ───────────────────────────────────────────────

class TestNormalizeConsultantCode:

    def test_empty_code_for_sunshine(self):
        from plugins.court_automation.guarantee.helpers import (
            _normalize_consultant_code,
            _SUNSHINE_INSURANCE_COMPANY,
            _SUNSHINE_DEFAULT_CONSULTANT_CODE,
        )
        result = _normalize_consultant_code(
            insurance_company_name=_SUNSHINE_INSURANCE_COMPANY, consultant_code=""
        )
        assert result == _SUNSHINE_DEFAULT_CONSULTANT_CODE

    def test_existing_code_kept(self):
        from plugins.court_automation.guarantee.helpers import _normalize_consultant_code
        result = _normalize_consultant_code(
            insurance_company_name="阳光保险", consultant_code="ABC123"
        )
        assert result == "ABC123"

    def test_non_sunshine_empty_returns_empty(self):
        from plugins.court_automation.guarantee.helpers import _normalize_consultant_code
        result = _normalize_consultant_code(
            insurance_company_name="平安保险", consultant_code=""
        )
        assert result == ""


# ── _normalize_property_clue_content ─────────────────────────────────────────

class TestNormalizePropertyClueContent:

    def test_joins_multiline(self):
        from plugins.court_automation.guarantee.helpers import _normalize_property_clue_content
        result = _normalize_property_clue_content("银行存款\n房产信息\n车辆")
        assert result == "银行存款；房产信息；车辆"

    def test_empty_lines_filtered(self):
        from plugins.court_automation.guarantee.helpers import _normalize_property_clue_content
        result = _normalize_property_clue_content("银行存款\n\n\n车辆")
        assert result == "银行存款；车辆"

    def test_empty_input(self):
        from plugins.court_automation.guarantee.helpers import _normalize_property_clue_content
        assert _normalize_property_clue_content("") == ""
        assert _normalize_property_clue_content(None) == ""


# ── _normalize_property_value ────────────────────────────────────────────────

class TestNormalizePropertyValue:

    def test_removes_commas(self):
        from plugins.court_automation.guarantee.helpers import _normalize_property_value
        assert _normalize_property_value("1,000,000") == "1000000"

    def test_strips_trailing_zeros(self):
        from plugins.court_automation.guarantee.helpers import _normalize_property_value
        assert _normalize_property_value("100.50") == "100.5"
        assert _normalize_property_value("100.00") == "100"

    def test_none_returns_empty(self):
        from plugins.court_automation.guarantee.helpers import _normalize_property_value
        assert _normalize_property_value(None) == ""


# ── _build_property_clue_info ────────────────────────────────────────────────

class TestBuildPropertyClueInfo:

    def test_with_content(self):
        from plugins.court_automation.guarantee.helpers import _build_property_clue_info
        result = _build_property_clue_info(clue_type="bank", raw_content="工商银行定期存款")
        assert "：" in result
        assert "工商银行" in result

    def test_empty_content_returns_type_display(self):
        from plugins.court_automation.guarantee.helpers import _build_property_clue_info
        result = _build_property_clue_info(clue_type="bank", raw_content="")
        assert result  # 至少返回类型展示名


# ── _normalize_party_type ────────────────────────────────────────────────────

class TestNormalizePartyType:

    @pytest.mark.parametrize("raw,expected", [
        ("natural", "natural"),
        ("person", "natural"),
        ("individual", "natural"),
        ("legal", "legal"),
        ("corp", "legal"),
        ("company", "legal"),
        ("enterprise", "legal"),
        ("organization", "legal"),
        ("org", "legal"),
        ("non_legal_org", "non_legal_org"),
        ("nonlegal", "non_legal_org"),
        ("other_org", "non_legal_org"),
        ("", "natural"),
        ("unknown", "natural"),
    ])
    def test_normalize_party_type(self, raw, expected):
        from plugins.court_automation.guarantee.helpers import _normalize_party_type
        assert _normalize_party_type(raw) == expected


# ── _build_cause_candidates ──────────────────────────────────────────────────

class TestBuildCauseCandidates:

    def test_splits_by_delimiters(self):
        from plugins.court_automation.guarantee.helpers import _build_cause_candidates
        result = _build_cause_candidates("买卖合同纠纷、借款合同纠纷")
        assert "买卖合同纠纷" in result
        assert "借款合同纠纷" in result

    def test_strips_suffix(self):
        from plugins.court_automation.guarantee.helpers import _build_cause_candidates
        result = _build_cause_candidates("买卖合同纠纷")
        assert "买卖合同纠纷" in result
        assert "买卖合同" in result

    def test_empty_input(self):
        from plugins.court_automation.guarantee.helpers import _build_cause_candidates
        assert _build_cause_candidates("") == []

    def test_max_eight(self):
        from plugins.court_automation.guarantee.helpers import _build_cause_candidates
        text = "、".join([f"案由{i}纠纷" for i in range(20)])
        result = _build_cause_candidates(text)
        assert len(result) <= 8


# ── _extract_quote_company_options ───────────────────────────────────────────

class TestExtractQuoteCompanyOptions:

    def test_none_context(self):
        from plugins.court_automation.guarantee.helpers import _extract_quote_company_options
        assert _extract_quote_company_options(quote_context=None) == []

    def test_success_items_preferred(self):
        from plugins.court_automation.guarantee.helpers import _extract_quote_company_options
        ctx = {
            "items": [
                {"company_name": "A公司", "status": "failed"},
                {"company_name": "B公司", "status": "success"},
                {"company_name": "C公司", "status": "success"},
            ]
        }
        result = _extract_quote_company_options(quote_context=ctx)
        assert result[0] == "B公司"  # success 优先
        assert result[1] == "C公司"

    def test_deduplicates(self):
        from plugins.court_automation.guarantee.helpers import _extract_quote_company_options
        ctx = {"items": [
            {"company_name": "A公司", "status": "success"},
            {"company_name": "A公司", "status": "success"},
        ]}
        result = _extract_quote_company_options(quote_context=ctx)
        assert result.count("A公司") == 1


# ── _resolve_insurance_company_defaults ──────────────────────────────────────

class TestResolveInsuranceCompanyDefaults:

    def test_with_quote_options(self):
        from plugins.court_automation.guarantee.helpers import _resolve_insurance_company_defaults
        ctx = {
            "recommended_company": "B公司",
            "items": [
                {"company_name": "A公司", "status": "success"},
                {"company_name": "B公司", "status": "success"},
            ],
        }
        default, options = _resolve_insurance_company_defaults(quote_context=ctx)
        assert default == "B公司"
        assert "A公司" in options

    def test_no_context_returns_global_default(self):
        from plugins.court_automation.guarantee.helpers import (
            _resolve_insurance_company_defaults,
            _DEFAULT_INSURANCE_COMPANY,
        )
        default, options = _resolve_insurance_company_defaults(quote_context=None)
        assert default == _DEFAULT_INSURANCE_COMPANY


# ── _normalize_selected_party_ids ────────────────────────────────────────────

class TestNormalizeSelectedPartyIds:

    def test_none_returns_none(self):
        from plugins.court_automation.guarantee.helpers import _normalize_selected_party_ids
        assert _normalize_selected_party_ids(None) is None

    def test_filters_invalid(self):
        from plugins.court_automation.guarantee.helpers import _normalize_selected_party_ids
        result = _normalize_selected_party_ids([1, 0, -1, "abc", 5])
        assert result == {1, 5}

    def test_empty_list(self):
        from plugins.court_automation.guarantee.helpers import _normalize_selected_party_ids
        assert _normalize_selected_party_ids([]) == set()


# ── _build_party_payload_from_case_party ─────────────────────────────────────

class TestBuildPartyPayloadFromCaseParty:

    def test_natural_person(self):
        from plugins.court_automation.guarantee.helpers import _build_party_payload_from_case_party
        client = SimpleNamespace(
            client_type="natural", name="张三", id_number="000000000000000000",
            phone="00000000000", address="广州",
            legal_representative="", legal_representative_id_number=""
        )
        party = SimpleNamespace(id=10, client=client)
        result = _build_party_payload_from_case_party(party=party)
        assert result["name"] == "张三"
        assert result["party_type"] == "natural"
        assert result["id_number"] == "000000000000000000"

    def test_none_party_raises_error(self):
        from plugins.court_automation.guarantee.helpers import _build_party_payload_from_case_party
        with pytest.raises(ValueError, match="客户姓名不能为空"):
            _build_party_payload_from_case_party(party=None)

    def test_legal_person(self):
        from plugins.court_automation.guarantee.helpers import _build_party_payload_from_case_party
        client = SimpleNamespace(
            client_type="legal", name="测试公司", id_number="91440101",
            phone="02000000000", address="天河区",
            legal_representative="李四", legal_representative_id_number="000000000000000000"
        )
        party = SimpleNamespace(id=20, client=client)
        result = _build_party_payload_from_case_party(party=party)
        assert result["party_type"] == "legal"


# ── _build_session_status_payload (guarantee) ────────────────────────────────

class TestGuaranteeSessionStatusPayload:

    def test_success_status(self):
        from plugins.court_automation.guarantee.helpers import _build_session_status_payload
        from apps.automation.models import ScraperTaskStatus
        task = SimpleNamespace(id=1, status=ScraperTaskStatus.SUCCESS, result={"message": "完成"}, error_message="")
        payload = _build_session_status_payload(task=task)
        assert payload["success"] is True
        assert payload["status"] == "completed"
        assert "担保" in payload["message"] or "完成" in payload["message"]

    def test_pending_status(self):
        from plugins.court_automation.guarantee.helpers import _build_session_status_payload
        from apps.automation.models import ScraperTaskStatus
        task = SimpleNamespace(id=2, status=ScraperTaskStatus.PENDING, result=None, error_message=None)
        payload = _build_session_status_payload(task=task)
        assert payload["success"] is True
        assert payload["status"] == "in_progress"

    def test_failed_status(self):
        from plugins.court_automation.guarantee.helpers import _build_session_status_payload
        from apps.automation.models import ScraperTaskStatus
        task = SimpleNamespace(id=3, status=ScraperTaskStatus.FAILED, result=None, error_message="出错了")
        payload = _build_session_status_payload(task=task)
        assert payload["success"] is False
        assert payload["status"] == "failed"
        assert payload["message"] == "出错了"

    def test_failed_default_message(self):
        from plugins.court_automation.guarantee.helpers import _build_session_status_payload
        from apps.automation.models import ScraperTaskStatus
        task = SimpleNamespace(id=4, status=ScraperTaskStatus.FAILED, result=None, error_message="")
        payload = _build_session_status_payload(task=task)
        assert "担保失败" in payload["message"]
