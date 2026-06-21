"""Comprehensive tests for court_guarantee_helpers data processing functions."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
try:
    from plugins.court_automation import filing  # noqa: F401
except ImportError:
    pytest.skip("court_automation plugin not installed", allow_module_level=True)


from plugins.court_automation.guarantee.helpers import (
    _build_cause_candidates,
    _build_party_payload_from_case_party,
    _build_property_clue_info,
    _build_respondent_options,
    _build_session_status_payload,
    _extract_quote_company_options,
    _list_opponent_case_parties,
    _list_opponent_party_payloads,
    _list_party_payloads,
    _normalize_consultant_code,
    _normalize_insurance_company,
    _normalize_party_type,
    _normalize_property_clue_content,
    _normalize_property_value,
    _normalize_selected_party_ids,
    _parse_preserve_amount,
    _pick_party_payload,
    _resolve_insurance_company_defaults,
)
from plugins.court_automation.guarantee.schemas import (
    _DEFAULT_INSURANCE_COMPANY,
    _GUARANTEE_INSURANCE_COMPANY_OPTIONS,
    _SUNSHINE_DEFAULT_CONSULTANT_CODE,
    _SUNSHINE_INSURANCE_COMPANY,
    _QUOTE_RETRY_ALLOWED_STATUSES,
    _RESPONDENT_SIDE_STATUSES,
    _read_int_env,
)


# ---------------------------------------------------------------------------
# _read_int_env (from schemas)
# ---------------------------------------------------------------------------
class TestReadIntEnv:
    def test_default(self):
        assert _read_int_env("NONEXISTENT_KEY_12345", 42) == 42

    def test_valid_int(self):
        import os
        os.environ["TEST_READ_INT_ENV_VALID"] = "10"
        try:
            assert _read_int_env("TEST_READ_INT_ENV_VALID", 0) == 10
        finally:
            del os.environ["TEST_READ_INT_ENV_VALID"]

    def test_negative_returns_default(self):
        import os
        os.environ["TEST_READ_INT_ENV_NEG"] = "-5"
        try:
            assert _read_int_env("TEST_READ_INT_ENV_NEG", 10) == 10
        finally:
            del os.environ["TEST_READ_INT_ENV_NEG"]

    def test_invalid_returns_default(self):
        import os
        os.environ["TEST_READ_INT_ENV_BAD"] = "abc"
        try:
            assert _read_int_env("TEST_READ_INT_ENV_BAD", 7) == 7
        finally:
            del os.environ["TEST_READ_INT_ENV_BAD"]


# ---------------------------------------------------------------------------
# _normalize_insurance_company
# ---------------------------------------------------------------------------
class TestNormalizeInsuranceCompany:
    def test_valid_company(self):
        result = _normalize_insurance_company("中国平安财产保险股份有限公司")
        assert result == "中国平安财产保险股份有限公司"

    def test_empty_returns_default(self):
        result = _normalize_insurance_company("")
        assert result == _DEFAULT_INSURANCE_COMPANY

    def test_invalid_company_returns_default(self):
        result = _normalize_insurance_company("不存在的公司")
        assert result == _DEFAULT_INSURANCE_COMPANY

    def test_with_allowed_options(self):
        result = _normalize_insurance_company("公司A", allowed_options=["公司A", "公司B"])
        assert result == "公司A"

    def test_allowed_options_fallback(self):
        result = _normalize_insurance_company("不在列表中", allowed_options=["公司A", "公司B"])
        assert result == "公司A"

    def test_empty_with_allowed_options(self):
        result = _normalize_insurance_company("", allowed_options=["公司A"])
        assert result == "公司A"


# ---------------------------------------------------------------------------
# _parse_preserve_amount
# ---------------------------------------------------------------------------
class TestParsePreserveAmount:
    def test_none(self):
        assert _parse_preserve_amount(None) is None

    def test_decimal_passthrough(self):
        d = Decimal("100000")
        assert _parse_preserve_amount(d) == d

    def test_string_number(self):
        assert _parse_preserve_amount("100000") == Decimal("100000")

    def test_int(self):
        assert _parse_preserve_amount(50000) == Decimal("50000")

    def test_float(self):
        assert _parse_preserve_amount(50000.50) == Decimal("50000.50")

    def test_invalid(self):
        assert _parse_preserve_amount("abc") is None

    def test_empty_string(self):
        assert _parse_preserve_amount("") is None


# ---------------------------------------------------------------------------
# _normalize_consultant_code
# ---------------------------------------------------------------------------
class TestNormalizeConsultantCode:
    def test_sunshine_no_code(self):
        result = _normalize_consultant_code(
            insurance_company_name=_SUNSHINE_INSURANCE_COMPANY,
            consultant_code=None,
        )
        assert result == _SUNSHINE_DEFAULT_CONSULTANT_CODE

    def test_sunshine_with_code(self):
        result = _normalize_consultant_code(
            insurance_company_name=_SUNSHINE_INSURANCE_COMPANY,
            consultant_code="custom123",
        )
        assert result == "custom123"

    def test_other_company_no_code(self):
        result = _normalize_consultant_code(
            insurance_company_name="其他公司",
            consultant_code=None,
        )
        assert result == ""


# ---------------------------------------------------------------------------
# _normalize_property_clue_content
# ---------------------------------------------------------------------------
class TestNormalizePropertyClueContent:
    def test_empty(self):
        assert _normalize_property_clue_content("") == ""

    def test_none(self):
        assert _normalize_property_clue_content(None) == ""  # type: ignore[arg-type]

    def test_single_line(self):
        assert _normalize_property_clue_content("银行账户123") == "银行账户123"

    def test_multi_line(self):
        result = _normalize_property_clue_content("银行账户123\n支付宝456\n微信789")
        assert result == "银行账户123；支付宝456；微信789"

    def test_blank_lines_filtered(self):
        result = _normalize_property_clue_content("银行账户123\n\n\n支付宝456\n")
        assert result == "银行账户123；支付宝456"


# ---------------------------------------------------------------------------
# _normalize_property_value
# ---------------------------------------------------------------------------
class TestNormalizePropertyValue:
    def test_none(self):
        assert _normalize_property_value(None) == ""

    def test_integer(self):
        assert _normalize_property_value(100000) == "100000"

    def test_comma_separated(self):
        assert _normalize_property_value("100,000.00") == "100000"

    def test_decimal(self):
        assert _normalize_property_value("50000.50") == "50000.5"

    def test_trailing_zeros(self):
        assert _normalize_property_value("50000.00") == "50000"

    def test_no_decimal(self):
        assert _normalize_property_value("50000") == "50000"


# ---------------------------------------------------------------------------
# _build_property_clue_info
# ---------------------------------------------------------------------------
class TestBuildPropertyClueInfo:
    def test_bank(self):
        result = _build_property_clue_info(clue_type="bank", raw_content="工商银行1234")
        assert "银行账户" in result
        assert "工商银行1234" in result

    def test_real_estate(self):
        result = _build_property_clue_info(clue_type="real_estate", raw_content="天河区某房产")
        assert "不动产" in result

    def test_empty_content(self):
        result = _build_property_clue_info(clue_type="bank", raw_content="")
        assert "银行账户" in result

    def test_unknown_type(self):
        result = _build_property_clue_info(clue_type="unknown_type", raw_content="some content")
        assert "unknown_type" in result


# ---------------------------------------------------------------------------
# _build_cause_candidates
# ---------------------------------------------------------------------------
class TestBuildCauseCandidates:
    def test_empty(self):
        assert _build_cause_candidates("") == []

    def test_none(self):
        assert _build_cause_candidates(None) == []  # type: ignore[arg-type]

    def test_single_cause(self):
        result = _build_cause_candidates("借款合同纠纷")
        assert "借款合同纠纷" in result
        assert "借款合同" in result

    def test_multiple_causes(self):
        result = _build_cause_candidates("借款合同纠纷、买卖合同纠纷")
        assert len(result) >= 2

    def test_dedup(self):
        result = _build_cause_candidates("借款合同纠纷、借款合同纠纷")
        assert result.count("借款合同纠纷") == 1

    def test_max_eight(self):
        result = _build_cause_candidates("、".join([f"案由{i}纠纷" for i in range(15)]))
        assert len(result) <= 8

    def test_with_full_width_space(self):
        result = _build_cause_candidates("借款合同纠纷　买卖合同纠纷")
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# _normalize_party_type
# ---------------------------------------------------------------------------
class TestNormalizePartyType:
    def test_natural(self):
        assert _normalize_party_type("natural") == "natural"

    def test_person(self):
        assert _normalize_party_type("person") == "natural"

    def test_individual(self):
        assert _normalize_party_type("individual") == "natural"

    def test_legal(self):
        assert _normalize_party_type("legal") == "legal"

    def test_company(self):
        assert _normalize_party_type("company") == "legal"

    def test_enterprise(self):
        assert _normalize_party_type("enterprise") == "legal"

    def test_non_legal_org(self):
        assert _normalize_party_type("non_legal_org") == "non_legal_org"

    def test_unknown_defaults_natural(self):
        assert _normalize_party_type("unknown") == "natural"

    def test_none(self):
        assert _normalize_party_type(None) == "natural"

    def test_empty(self):
        assert _normalize_party_type("") == "natural"


# ---------------------------------------------------------------------------
# _normalize_selected_party_ids
# ---------------------------------------------------------------------------
class TestNormalizeSelectedPartyIds:
    def test_none(self):
        assert _normalize_selected_party_ids(None) is None

    def test_valid_ids(self):
        result = _normalize_selected_party_ids([1, 2, 3])
        assert result == {1, 2, 3}

    def test_zero_filtered(self):
        result = _normalize_selected_party_ids([0, 1, -1, 2])
        assert result == {1, 2}

    def test_invalid_type(self):
        result = _normalize_selected_party_ids([1, "abc", 2])  # type: ignore[list-item]
        assert result == {1, 2}

    def test_empty_list(self):
        result = _normalize_selected_party_ids([])
        assert result == set()


# ---------------------------------------------------------------------------
# _list_opponent_case_parties
# ---------------------------------------------------------------------------
class TestListOpponentCaseParties:
    def test_with_opponents(self):
        our_client = SimpleNamespace(is_our_client=True)
        opp_client = SimpleNamespace(is_our_client=False)
        parties = [
            SimpleNamespace(client=our_client, legal_status="plaintiff"),
            SimpleNamespace(client=opp_client, legal_status="defendant"),
        ]
        result = _list_opponent_case_parties(case_parties=parties)
        assert len(result) == 1
        assert result[0].client == opp_client

    def test_fallback_to_status(self):
        # All is_our_client=True, but defendant status
        client = SimpleNamespace(is_our_client=True)
        parties = [
            SimpleNamespace(client=client, legal_status="defendant"),
        ]
        result = _list_opponent_case_parties(case_parties=parties)
        assert len(result) == 1

    def test_no_match_returns_all(self):
        client = SimpleNamespace(is_our_client=True)
        parties = [
            SimpleNamespace(client=client, legal_status="plaintiff"),
        ]
        result = _list_opponent_case_parties(case_parties=parties)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _build_party_payload_from_case_party
# ---------------------------------------------------------------------------
class TestBuildPartyPayloadFromCaseParty:
    def test_natural_party(self):
        client = SimpleNamespace(
            client_type="natural", name="张三",
            id_number="110101199003071234", phone="13800138000",
            address="北京市", legal_representative="",
            legal_representative_id_number="",
        )
        party = SimpleNamespace(id=1, client=client)
        result = _build_party_payload_from_case_party(party=party)
        assert result["name"] == "张三"
        assert result["party_type"] == "natural"

    def test_legal_party(self):
        client = SimpleNamespace(
            client_type="legal", name="某公司",
            id_number="91440101MA59TEST", phone="020-12345678",
            address="广州市", legal_representative="李四",
            legal_representative_id_number="440101199001011234",
        )
        party = SimpleNamespace(id=2, client=client)
        result = _build_party_payload_from_case_party(party=party)
        assert result["name"] == "某公司"
        assert result["party_type"] == "legal"

    def test_none_party_raises_error(self):
        with pytest.raises(ValueError, match="客户姓名不能为空"):
            _build_party_payload_from_case_party(party=None)

    def test_empty_id_number_raises_error(self):
        client = SimpleNamespace(
            client_type="natural", name="王五",
            id_number="", phone="13800000000",
            address="测试地址", legal_representative="",
            legal_representative_id_number="",
        )
        party = SimpleNamespace(id=3, client=client)
        with pytest.raises(ValueError, match="客户证件号不能为空"):
            _build_party_payload_from_case_party(party=party)


# ---------------------------------------------------------------------------
# _list_party_payloads
# ---------------------------------------------------------------------------
class TestListPartyPayloads:
    def _make_party(self, legal_status, is_our_client=True, name="Test"):
        client = SimpleNamespace(
            client_type="natural", name=name,
            id_number="110101199003071234", phone="13800138000",
            address="地址", is_our_client=is_our_client,
            legal_representative="", legal_representative_id_number="",
        )
        return SimpleNamespace(id=1, legal_status=legal_status, client=client)

    def test_prefer_our_plaintiff(self):
        our = self._make_party("plaintiff", True, "我方")
        opp = self._make_party("plaintiff", False, "对方")
        result = _list_party_payloads(
            case_parties=[our, opp],
            preferred_statuses={"plaintiff"},
            prefer_our=True,
        )
        assert len(result) == 1
        assert result[0]["name"] == "我方"

    def test_fallback_to_status(self):
        opp = self._make_party("plaintiff", False, "对方")
        result = _list_party_payloads(
            case_parties=[opp],
            preferred_statuses={"plaintiff"},
            prefer_our=True,
        )
        assert len(result) == 1

    def test_fallback_to_first(self):
        party = self._make_party("defendant", True, "唯一")
        result = _list_party_payloads(
            case_parties=[party],
            preferred_statuses={"plaintiff"},
            prefer_our=True,
        )
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _pick_party_payload
# ---------------------------------------------------------------------------
class TestPickPartyPayload:
    def test_returns_first(self):
        client = SimpleNamespace(
            client_type="natural", name="张三",
            id_number="110101199003071234", phone="13800138000",
            address="地址", is_our_client=True,
            legal_representative="", legal_representative_id_number="",
        )
        party = SimpleNamespace(id=1, legal_status="plaintiff", client=client)
        result = _pick_party_payload(
            case_parties=[party],
            preferred_statuses={"plaintiff"},
            prefer_our=True,
        )
        assert result["name"] == "张三"

    def test_empty_returns_default(self):
        result = _pick_party_payload(
            case_parties=[],
            preferred_statuses={"plaintiff"},
            prefer_our=True,
        )
        assert result["name"] == "张三"  # default fallback


# ---------------------------------------------------------------------------
# _extract_quote_company_options
# ---------------------------------------------------------------------------
class TestExtractQuoteCompanyOptions:
    def test_none(self):
        assert _extract_quote_company_options(quote_context=None) == []

    def test_empty_dict(self):
        assert _extract_quote_company_options(quote_context={}) == []

    def test_no_items(self):
        assert _extract_quote_company_options(quote_context={"items": None}) == []

    def test_success_items_first(self):
        ctx = {
            "items": [
                {"company_name": "B公司", "status": "failed"},
                {"company_name": "A公司", "status": "success"},
            ]
        }
        result = _extract_quote_company_options(quote_context=ctx)
        assert result[0] == "A公司"

    def test_dedup(self):
        ctx = {
            "items": [
                {"company_name": "A公司", "status": "success"},
                {"company_name": "A公司", "status": "success"},
            ]
        }
        result = _extract_quote_company_options(quote_context=ctx)
        assert result.count("A公司") == 1


# ---------------------------------------------------------------------------
# _resolve_insurance_company_defaults
# ---------------------------------------------------------------------------
class TestResolveInsuranceCompanyDefaults:
    def test_no_quote_context(self):
        company, options = _resolve_insurance_company_defaults(quote_context=None)
        assert company == _DEFAULT_INSURANCE_COMPANY

    def test_with_recommended(self):
        ctx = {
            "recommended_company": "A公司",
            "items": [
                {"company_name": "A公司", "status": "success"},
                {"company_name": "B公司", "status": "success"},
            ],
        }
        company, options = _resolve_insurance_company_defaults(quote_context=ctx)
        assert company == "A公司"

    def test_recommended_not_in_options(self):
        ctx = {
            "recommended_company": "C公司",
            "items": [
                {"company_name": "A公司", "status": "success"},
            ],
        }
        company, options = _resolve_insurance_company_defaults(quote_context=ctx)
        assert company == "A公司"


# ---------------------------------------------------------------------------
# _build_session_status_payload (guarantee version)
# ---------------------------------------------------------------------------
class TestGuaranteeSessionStatusPayload:
    def test_pending(self):
        from apps.automation.models import ScraperTaskStatus
        task = SimpleNamespace(
            id=1, status=ScraperTaskStatus.PENDING,
            result=None, error_message=None,
        )
        payload = _build_session_status_payload(task=task)
        assert payload["status"] == "in_progress"
        assert payload["success"] is True

    def test_success(self):
        from apps.automation.models import ScraperTaskStatus
        task = SimpleNamespace(
            id=2, status=ScraperTaskStatus.SUCCESS,
            result={"message": "完成"}, error_message=None,
        )
        payload = _build_session_status_payload(task=task)
        assert payload["status"] == "completed"

    def test_failed_no_message(self):
        from apps.automation.models import ScraperTaskStatus
        task = SimpleNamespace(
            id=3, status=ScraperTaskStatus.FAILED,
            result=None, error_message="",
        )
        payload = _build_session_status_payload(task=task)
        assert payload["status"] == "failed"
        assert "担保失败" in payload["message"]

    def test_failed_with_result_message(self):
        from apps.automation.models import ScraperTaskStatus
        task = SimpleNamespace(
            id=4, status=ScraperTaskStatus.FAILED,
            result={"message": "具体错误"}, error_message="",
        )
        payload = _build_session_status_payload(task=task)
        assert "具体错误" in payload["message"]

    def test_timing_included(self):
        from apps.automation.models import ScraperTaskStatus
        task = SimpleNamespace(
            id=5, status=ScraperTaskStatus.RUNNING,
            result={"timing": {"start": 1.0}}, error_message=None,
        )
        payload = _build_session_status_payload(task=task)
        assert "timing" in payload
