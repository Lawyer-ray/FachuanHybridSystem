"""Full coverage tests for plugins.court_automation.guarantee.helpers."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.api import court_guarantee_helpers as helpers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_case_party(
    *,
    party_id: int = 1,
    client_id: int = 10,
    client_name: str = "张三",
    legal_status: str = "defendant",
    client_type: str = "natural",
    id_number: str = "110101199003077715",  # pragma: allowlist secret
    phone: str = "13800138000",  # pragma: allowlist secret
    address: str = "广州市天河区",
    is_our_client: bool = False,
    legal_rep: str = "",
    legal_rep_id: str = "",
) -> SimpleNamespace:
    client = SimpleNamespace(
        id=client_id,
        client_type=client_type,
        name=client_name,
        id_number=id_number,
        phone=phone,
        address=address,
        is_our_client=is_our_client,
        legal_representative=legal_rep,
        legal_representative_id_number=legal_rep_id,
    )
    party = SimpleNamespace(id=party_id, legal_status=legal_status, client=client)
    party.get_legal_status_display = lambda: legal_status
    return party


class _FakeClientService:
    def __init__(self, clues: dict[int, list] | None = None):
        self._clues = clues or {}

    def get_property_clues_by_client_internal(self, client_id: int):
        return list(self._clues.get(client_id, []))


# ======================================================================
# _resolve_court_name
# ======================================================================

class TestResolveCourtName:
    def test_none_input(self):
        assert helpers._resolve_court_name(None) is None

    def test_empty_string(self):
        assert helpers._resolve_court_name("") is None

    def test_already_has_people_court(self):
        assert helpers._resolve_court_name("天河区人民法院") == "天河区人民法院"

    def test_found_in_db(self):
        with patch("apps.core.models.Court") as MockCourt:
            MockCourt.objects.filter.return_value.first.return_value = SimpleNamespace(name="广州市天河区人民法院")
            result = helpers._resolve_court_name("天河区")
            assert result == "广州市天河区人民法院"

    def test_not_in_db_appends_suffix(self):
        with patch("apps.core.models.Court") as MockCourt:
            MockCourt.objects.filter.return_value.first.return_value = None
            result = helpers._resolve_court_name("浦东新区")
            assert result == "浦东新区人民法院"


# ======================================================================
# _normalize_insurance_company
# ======================================================================

class TestNormalizeInsuranceCompany:
    def test_empty_returns_default(self):
        result = helpers._normalize_insurance_company("")
        assert result == helpers._DEFAULT_INSURANCE_COMPANY

    def test_valid_in_options(self):
        with patch.object(helpers, "_GUARANTEE_INSURANCE_COMPANY_OPTIONS", ["阳光财险", "平安财险"]):
            result = helpers._normalize_insurance_company("阳光财险")
            assert result == "阳光财险"

    def test_not_in_options_returns_default(self):
        with patch.object(helpers, "_GUARANTEE_INSURANCE_COMPANY_OPTIONS", ["阳光财险"]):
            result = helpers._normalize_insurance_company("某小公司")
            assert result == helpers._DEFAULT_INSURANCE_COMPANY

    def test_with_allowed_options_present(self):
        result = helpers._normalize_insurance_company("A", allowed_options=["A", "B", "C"])
        assert result == "A"

    def test_with_allowed_options_missing(self):
        result = helpers._normalize_insurance_company("Z", allowed_options=["A", "B"])
        assert result == "A"

    def test_empty_with_allowed_options(self):
        result = helpers._normalize_insurance_company("", allowed_options=["X", "Y"])
        assert result == "X"


# ======================================================================
# _parse_preserve_amount
# ======================================================================

class TestParsePreserveAmount:
    def test_none(self):
        assert helpers._parse_preserve_amount(None) is None

    def test_decimal_passthrough(self):
        assert helpers._parse_preserve_amount(Decimal("10000")) == Decimal("10000")

    def test_string_valid(self):
        assert helpers._parse_preserve_amount("50000") == Decimal("50000")

    def test_string_invalid(self):
        assert helpers._parse_preserve_amount("abc") is None

    def test_int_value(self):
        assert helpers._parse_preserve_amount(100) == Decimal("100")

    def test_float_value(self):
        result = helpers._parse_preserve_amount(100.5)
        assert result == Decimal("100.5")


# ======================================================================
# _normalize_consultant_code
# ======================================================================

class TestNormalizeConsultantCode:
    def test_sunshine_with_empty_code(self):
        result = helpers._normalize_consultant_code(
            insurance_company_name="阳光财产保险股份有限公司", consultant_code=None
        )
        assert result == helpers._SUNSHINE_DEFAULT_CONSULTANT_CODE

    def test_sunshine_with_code(self):
        result = helpers._normalize_consultant_code(
            insurance_company_name="阳光财产保险股份有限公司", consultant_code="12345"
        )
        assert result == "12345"

    def test_other_company(self):
        result = helpers._normalize_consultant_code(
            insurance_company_name="平安财险", consultant_code=None
        )
        assert result == ""


# ======================================================================
# _normalize_property_clue_content
# ======================================================================

class TestNormalizePropertyClueContent:
    def test_empty(self):
        assert helpers._normalize_property_clue_content("") == ""

    def test_single_line(self):
        assert helpers._normalize_property_clue_content("线索一") == "线索一"

    def test_multi_line(self):
        result = helpers._normalize_property_clue_content("线索一\n线索二\n线索三")
        assert result == "线索一；线索二；线索三"

    def test_blank_lines_filtered(self):
        result = helpers._normalize_property_clue_content("线索一\n\n\n线索二")
        assert result == "线索一；线索二"


# ======================================================================
# _normalize_property_value
# ======================================================================

class TestNormalizePropertyValue:
    def test_none(self):
        assert helpers._normalize_property_value(None) == ""

    def test_integer_string(self):
        assert helpers._normalize_property_value("10000") == "10000"

    def test_decimal_trailing_zeros(self):
        assert helpers._normalize_property_value("10000.50") == "10000.5"

    def test_commas_removed(self):
        assert helpers._normalize_property_value("10,000.50") == "10000.5"

    def test_whole_number_decimal(self):
        assert helpers._normalize_property_value("10000.00") == "10000"


# ======================================================================
# _build_property_clue_info
# ======================================================================

class TestBuildPropertyClueInfo:
    def test_known_type(self):
        result = helpers._build_property_clue_info(clue_type="bank", raw_content="账户内容")
        assert result == "银行账户：账户内容"

    def test_unknown_type(self):
        result = helpers._build_property_clue_info(clue_type="unknown_type", raw_content="内容")
        assert "unknown_type" in result

    def test_empty_content(self):
        result = helpers._build_property_clue_info(clue_type="bank", raw_content="")
        assert "银行账户" in result

    def test_real_estate(self):
        result = helpers._build_property_clue_info(clue_type="real_estate", raw_content="某房产")
        assert "不动产" in result

    def test_alipay(self):
        result = helpers._build_property_clue_info(clue_type="alipay", raw_content="支付宝")
        assert "支付宝账户" in result

    def test_wechat(self):
        result = helpers._build_property_clue_info(clue_type="wechat", raw_content="微信")
        assert "微信账户" in result


# ======================================================================
# _build_cause_candidates
# ======================================================================

class TestBuildCauseCandidates:
    def test_empty(self):
        assert helpers._build_cause_candidates("") == []

    def test_single_cause(self):
        result = helpers._build_cause_candidates("借款纠纷")
        assert "借款纠纷" in result

    def test_multiple_causes(self):
        result = helpers._build_cause_candidates("买卖合同纠纷、借款合同纠纷")
        assert len(result) >= 3  # full + split + stripped "纠纷"

    def test_with_slash_separator(self):
        result = helpers._build_cause_candidates("合同纠纷/侵权纠纷")
        assert "合同纠纷" in result
        assert "侵权纠纷" in result

    def test_strips_suffix(self):
        result = helpers._build_cause_candidates("借款合同纠纷")
        assert "借款合同" in result

    def test_max_8_candidates(self):
        long_text = "、".join([f"案由{i}纠纷" for i in range(15)])
        result = helpers._build_cause_candidates(long_text)
        assert len(result) <= 8

    def test_fullwidth_space(self):
        result = helpers._build_cause_candidates("借款　纠纷")
        assert len(result) >= 1


# ======================================================================
# _normalize_party_type
# ======================================================================

class TestNormalizePartyType:
    def test_natural(self):
        assert helpers._normalize_party_type("natural") == "natural"

    def test_person(self):
        assert helpers._normalize_party_type("person") == "natural"

    def test_individual(self):
        assert helpers._normalize_party_type("individual") == "natural"

    def test_legal(self):
        assert helpers._normalize_party_type("legal") == "legal"

    def test_corp(self):
        assert helpers._normalize_party_type("corp") == "legal"

    def test_company(self):
        assert helpers._normalize_party_type("company") == "legal"

    def test_enterprise(self):
        assert helpers._normalize_party_type("enterprise") == "legal"

    def test_organization(self):
        assert helpers._normalize_party_type("organization") == "legal"

    def test_non_legal_org(self):
        assert helpers._normalize_party_type("non_legal_org") == "non_legal_org"

    def test_unknown_defaults_natural(self):
        assert helpers._normalize_party_type("bogus") == "natural"

    def test_none_defaults_natural(self):
        assert helpers._normalize_party_type(None) == "natural"


# ======================================================================
# _build_party_payload_from_case_party
# ======================================================================

class TestBuildPartyPayloadFromCaseParty:
    def test_natural_party(self):
        party = _make_case_party(client_type="natural", client_name="张三")
        result = helpers._build_party_payload_from_case_party(party=party)
        assert result["party_type"] == "natural"
        assert result["name"] == "张三"
        assert result["id_number"] == "110101199003077715"  # pragma: allowlist secret

    def test_legal_party(self):
        party = _make_case_party(
            client_type="legal", client_name="某公司", id_number="91440101MA59TEST8X",
            legal_rep="李四", legal_rep_id="110101199003077715",  # pragma: allowlist secret
        )
        result = helpers._build_party_payload_from_case_party(party=party)
        assert result["party_type"] == "legal"
        assert result["legal_representative"] == "李四"

    def test_missing_name_defaults_to_zhangsan(self):
        client = SimpleNamespace(
            id=1, client_type="natural", name="", id_number="", phone="",
            address="", is_our_client=False, legal_representative="", legal_representative_id_number="",
        )
        party = SimpleNamespace(id=1, legal_status="defendant", client=client)
        result = helpers._build_party_payload_from_case_party(party=party)
        assert result["name"] == "张三"

    def test_none_party(self):
        result = helpers._build_party_payload_from_case_party(party=None)
        assert result["name"] == "张三"
        assert result["party_type"] == "natural"


# ======================================================================
# _list_party_payloads / _pick_party_payload
# ======================================================================

class TestListAndPickPartyPayloads:
    def test_list_filters_by_status_and_side(self):
        party = _make_case_party(legal_status="defendant", is_our_client=False)
        result = helpers._list_party_payloads(
            case_parties=[party],
            preferred_statuses={"defendant"},
            prefer_our=False,
        )
        assert len(result) == 1

    def test_list_falls_back_to_status_only(self):
        party = _make_case_party(legal_status="defendant", is_our_client=True)
        result = helpers._list_party_payloads(
            case_parties=[party],
            preferred_statuses={"defendant"},
            prefer_our=False,
        )
        assert len(result) == 1

    def test_list_falls_back_to_side_only(self):
        party = _make_case_party(legal_status="plaintiff", is_our_client=False)
        result = helpers._list_party_payloads(
            case_parties=[party],
            preferred_statuses={"defendant"},
            prefer_our=False,
        )
        assert len(result) == 1

    def test_list_falls_back_to_first(self):
        party = _make_case_party(legal_status="plaintiff", is_our_client=True)
        result = helpers._list_party_payloads(
            case_parties=[party],
            preferred_statuses={"defendant"},
            prefer_our=False,
        )
        assert len(result) == 1

    def test_pick_returns_first(self):
        party = _make_case_party()
        result = helpers._pick_party_payload(
            case_parties=[party],
            preferred_statuses={"defendant"},
            prefer_our=False,
        )
        assert result["name"] == "张三"

    def test_pick_empty_returns_default(self):
        result = helpers._pick_party_payload(
            case_parties=[],
            preferred_statuses=set(),
            prefer_our=False,
        )
        assert result["name"] == "张三"


# ======================================================================
# _normalize_selected_party_ids
# ======================================================================

class TestNormalizeSelectedPartyIds:
    def test_none(self):
        assert helpers._normalize_selected_party_ids(None) is None

    def test_valid_ids(self):
        assert helpers._normalize_selected_party_ids([1, 2, 3]) == {1, 2, 3}

    def test_filters_zero_and_negative(self):
        assert helpers._normalize_selected_party_ids([0, -1, 5]) == {5}

    def test_empty_list(self):
        assert helpers._normalize_selected_party_ids([]) == set()


# ======================================================================
# _list_opponent_case_parties
# ======================================================================

class TestListOpponentCaseParties:
    def test_opponent_by_is_our_client(self):
        opponent = _make_case_party(is_our_client=False, legal_status="defendant")
        our = _make_case_party(party_id=2, is_our_client=True, legal_status="plaintiff")
        result = helpers._list_opponent_case_parties(case_parties=[our, opponent])
        assert len(result) == 1
        assert result[0].id == opponent.id

    def test_fallback_to_respondent_status(self):
        party = _make_case_party(legal_status="respondent", is_our_client=True)
        result = helpers._list_opponent_case_parties(case_parties=[party])
        assert len(result) == 1

    def test_final_fallback_all(self):
        party = _make_case_party(legal_status="other", is_our_client=True)
        result = helpers._list_opponent_case_parties(case_parties=[party])
        assert len(result) == 1


# ======================================================================
# _list_opponent_party_payloads
# ======================================================================

class TestListOpponentPartyPayloads:
    def test_returns_payloads(self):
        opponent = _make_case_party(is_our_client=False, legal_status="defendant")
        result = helpers._list_opponent_party_payloads(case_parties=[opponent])
        assert len(result) == 1
        assert result[0]["name"] == "张三"


# ======================================================================
# _build_respondent_options
# ======================================================================

class TestBuildRespondentOptions:
    def test_returns_options(self):
        opponent = _make_case_party(party_id=5, is_our_client=False, legal_status="defendant")
        result = helpers._build_respondent_options(case_parties=[opponent])
        assert len(result) == 1
        assert result[0]["party_id"] == 5
        assert result[0]["name"] == "张三"


# ======================================================================
# _extract_quote_company_options
# ======================================================================

class TestExtractQuoteCompanyOptions:
    def test_none(self):
        assert helpers._extract_quote_company_options(quote_context=None) == []

    def test_no_items(self):
        assert helpers._extract_quote_company_options(quote_context={}) == []

    def test_success_items_first(self):
        context = {
            "items": [
                {"company_name": "B公司", "status": "failed"},
                {"company_name": "A公司", "status": "success"},
            ]
        }
        result = helpers._extract_quote_company_options(quote_context=context)
        assert result[0] == "A公司"  # success first

    def test_dedup(self):
        context = {
            "items": [
                {"company_name": "A", "status": "success"},
                {"company_name": "A", "status": "failed"},
            ]
        }
        result = helpers._extract_quote_company_options(quote_context=context)
        assert result.count("A") == 1


# ======================================================================
# _resolve_insurance_company_defaults
# ======================================================================

class TestResolveInsuranceCompanyDefaults:
    def test_none_context(self):
        default, options = helpers._resolve_insurance_company_defaults(quote_context=None)
        assert default == helpers._DEFAULT_INSURANCE_COMPANY

    def test_with_recommended(self):
        context = {
            "recommended_company": "阳光财险",
            "items": [
                {"company_name": "阳光财险", "status": "success"},
                {"company_name": "平安财险", "status": "success"},
            ]
        }
        default, options = helpers._resolve_insurance_company_defaults(quote_context=context)
        assert default == "阳光财险"

    def test_with_recommended_not_in_options(self):
        context = {
            "recommended_company": "不存在",
            "items": [
                {"company_name": "A公司", "status": "success"},
            ]
        }
        default, options = helpers._resolve_insurance_company_defaults(quote_context=context)
        assert default == "A公司"


# ======================================================================
# _build_session_status_payload
# ======================================================================

class TestBuildSessionStatusPayload:
    def _make_task(self, status, task_id=1, result=None, error_message=""):
        return SimpleNamespace(id=task_id, status=status, result=result or {}, error_message=error_message)

    def test_pending(self):
        with patch("apps.automation.models.ScraperTaskStatus") as S:
            S.PENDING = "pending"
            S.RUNNING = "running"
            S.SUCCESS = "success"
            task = self._make_task("pending", result={"message": "排队中"})
            r = helpers._build_session_status_payload(task=task)
            assert r["status"] == "in_progress"
            assert r["message"] == "排队中"

    def test_success(self):
        with patch("apps.automation.models.ScraperTaskStatus") as S:
            S.PENDING = "pending"
            S.RUNNING = "running"
            S.SUCCESS = "success"
            task = self._make_task("success", result={"message": "完成"})
            r = helpers._build_session_status_payload(task=task)
            assert r["status"] == "completed"

    def test_failed_with_error(self):
        with patch("apps.automation.models.ScraperTaskStatus") as S:
            S.PENDING = "pending"
            S.RUNNING = "running"
            S.SUCCESS = "success"
            task = self._make_task("failed", error_message="超时")
            r = helpers._build_session_status_payload(task=task)
            assert r["status"] == "failed"
            assert r["message"] == "超时"

    def test_failed_default_message(self):
        with patch("apps.automation.models.ScraperTaskStatus") as S:
            S.PENDING = "pending"
            S.RUNNING = "running"
            S.SUCCESS = "success"
            task = self._make_task("failed", error_message="", result={})
            r = helpers._build_session_status_payload(task=task)
            assert r["message"] == "担保失败"

    def test_timing_included(self):
        with patch("apps.automation.models.ScraperTaskStatus") as S:
            S.PENDING = "pending"
            S.RUNNING = "running"
            S.SUCCESS = "success"
            task = self._make_task("success", result={"timing": {"t": 1}})
            r = helpers._build_session_status_payload(task=task)
            assert "timing" in r


# ======================================================================
# _update_session_task
# ======================================================================

class TestUpdateSessionTask:
    def test_noop_when_none(self):
        helpers._update_session_task(session_id=None, status="running")

    @patch("plugins.court_automation.guarantee.helpers.timezone")
    def test_sync_update(self, mock_tz):
        mock_tz.now.return_value = "2026-01-01"
        with patch("apps.automation.models.ScraperTask") as MockTask:
            with patch("django.db.close_old_connections"):
                with patch("asyncio.get_running_loop", side_effect=RuntimeError("no loop")):
                    helpers._update_session_task(session_id=5, status="success", set_started=True, set_finished=True)
                    MockTask.objects.filter.assert_called_once_with(id=5)

    @patch("plugins.court_automation.guarantee.helpers.timezone")
    def test_async_update(self, mock_tz):
        mock_tz.now.return_value = "2026-01-01"
        with patch("asyncio.get_running_loop", return_value=MagicMock()):
            with patch.object(helpers._SESSION_UPDATE_EXECUTOR, "submit") as mock_submit:
                helpers._update_session_task(session_id=5, status="running", error_message="err")
                mock_submit.assert_called_once()


# ======================================================================
# _get_case_number / _has_case_number
# ======================================================================

class TestCaseNumberHelpers:
    def test_get_case_number_from_table(self):
        mock_qs = MagicMock()
        mock_qs.exclude.return_value = mock_qs
        mock_qs.values_list.return_value.first.return_value = "2025粤01民初1号"
        case = SimpleNamespace(case_numbers=mock_qs)
        assert helpers._get_case_number(case) == "2025粤01民初1号"

    def test_get_case_number_fallback_to_filing(self):
        mock_qs = MagicMock()
        mock_qs.exclude.return_value = mock_qs
        mock_qs.values_list.return_value.first.return_value = None
        case = SimpleNamespace(case_numbers=mock_qs, filing_number="F123")
        assert helpers._get_case_number(case) == "F123"

    def test_has_case_number_true(self):
        mock_qs = MagicMock()
        mock_qs.exclude.return_value = mock_qs
        mock_qs.values_list.return_value.first.return_value = "CN001"
        case = SimpleNamespace(case_numbers=mock_qs)
        assert helpers._has_case_number(case) is True

    def test_has_case_number_false(self):
        mock_qs = MagicMock()
        mock_qs.exclude.return_value = mock_qs
        mock_qs.values_list.return_value.first.return_value = None
        case = SimpleNamespace(case_numbers=mock_qs, filing_number="")
        assert helpers._has_case_number(case) is False


# ======================================================================
# _get_case_court_name
# ======================================================================

class TestGetCaseCourtName:
    def test_trial_authority(self):
        sa = SimpleNamespace(name="天河区", authority_type="trial")
        mock_qs = MagicMock()
        mock_qs.all.return_value.order_by.return_value = mock_qs
        mock_qs.filter.return_value.first.return_value = sa
        case = SimpleNamespace(supervising_authorities=mock_qs)
        with patch("apps.core.models.enums.AuthorityType") as MockAT:
            MockAT.TRIAL = "trial"
            with patch.object(helpers, "_resolve_court_name", return_value="天河区人民法院"):
                result = helpers._get_case_court_name(case)
                assert result == "天河区人民法院"

    def test_no_authority(self):
        mock_qs = MagicMock()
        mock_qs.all.return_value.order_by.return_value = mock_qs
        mock_qs.filter.return_value.first.return_value = None
        mock_qs.exclude.return_value = mock_qs
        mock_qs.exclude.return_value.first.return_value = None
        case = SimpleNamespace(supervising_authorities=mock_qs)
        with patch("apps.core.models.enums.AuthorityType") as MockAT:
            MockAT.TRIAL = "trial"
            result = helpers._get_case_court_name(case)
            assert result is None


# ======================================================================
# _build_plaintiff_agent_payload
# ======================================================================

class TestBuildPlaintiffAgentPayload:
    def test_with_lawyer(self):
        case = SimpleNamespace(assignments=MagicMock())
        case.assignments.select_related.return_value.order_by.return_value.first.return_value = None
        lawyer = SimpleNamespace(
            id=1,
            real_name="王律师",
            username="wang",
            id_card="110101199003077715",  # pragma: allowlist secret
            phone="13800138000",  # pragma: allowlist secret
            license_no="12345",
            law_firm=SimpleNamespace(name="测试所"),
        )
        with patch("apps.organization.models.Lawyer") as MockLawyer:
            MockLawyer.objects.select_related.return_value.filter.return_value.first.return_value = lawyer
            result = helpers._build_plaintiff_agent_payload(
                case=case, requester_id=1, fallback_party={"name": "张三", "phone": "139"}
            )
            assert result["name"] == "王律师"
            assert result["law_firm"] == "测试所"

    def test_fallback_when_no_lawyer(self):
        case = SimpleNamespace(assignments=MagicMock())
        case.assignments.select_related.return_value.order_by.return_value.first.return_value = None
        with patch("apps.organization.models.Lawyer") as MockLawyer:
            MockLawyer.objects.select_related.return_value.filter.return_value.first.return_value = None
            result = helpers._build_plaintiff_agent_payload(
                case=case, requester_id=None, fallback_party={"name": "张三", "phone": "139"}
            )
            assert result["name"] == "张三"
            assert result["party_type"] == "agent"


# ======================================================================
# _build_case_quote_context
# ======================================================================

class TestBuildCaseQuoteContext:
    def test_no_preserve_amount(self):
        case = SimpleNamespace(preservation_amount=None)
        assert helpers._build_case_quote_context(case=case) is None

    def test_with_binding(self):
        from apps.automation.models import QuoteItemStatus
        quote_item = SimpleNamespace(
            id=1,
            company_name="平安财险",
            premium=Decimal("100"),
            min_amount=Decimal("1000"),
            max_amount=Decimal("100000"),
            max_apply_amount=Decimal("100000"),
            status=QuoteItemStatus.SUCCESS,
            error_message="",
        )
        quote = SimpleNamespace(
            id=1,
            status="success",
            error_message="",
            created_at=None,
            finished_at=None,
            success_count=1,
            failed_count=0,
            total_companies=1,
            quotes=MagicMock(),
        )
        quote.quotes.filter.return_value.order_by.return_value = [quote_item]
        binding = SimpleNamespace(
            id=1,
            preservation_quote=quote,
            preserve_amount_snapshot=Decimal("50000"),
        )
        case = SimpleNamespace(id=1, preservation_amount=Decimal("50000"))
        with patch.object(helpers, "_find_reusable_binding", return_value=binding):
            result = helpers._build_case_quote_context(case=case)
            assert result is not None
            assert result["quote_id"] == 1
            assert len(result["items"]) == 1


# ======================================================================
# _build_reusable_quote_options
# ======================================================================

class TestBuildReusableQuoteOptions:
    def test_no_preserve_amount(self):
        case = SimpleNamespace(id=1, preservation_amount=None)
        assert helpers._build_reusable_quote_options(case=case) == []

    def test_zero_amount(self):
        case = SimpleNamespace(id=1, preservation_amount=Decimal("0"))
        assert helpers._build_reusable_quote_options(case=case) == []


# ======================================================================
# _get_organization_service / _get_client_service
# ======================================================================

class TestServiceGetters:
    def test_org_service(self):
        with patch("apps.core.dependencies.build_organization_service", return_value="svc"):
            assert helpers._get_organization_service() == "svc"

    def test_client_service(self):
        with patch("apps.core.dependencies.build_client_service", return_value="svc"):
            assert helpers._get_client_service() == "svc"
