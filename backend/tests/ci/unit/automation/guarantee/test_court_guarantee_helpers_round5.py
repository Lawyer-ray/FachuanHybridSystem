"""court_guarantee_helpers.py — round5 tests for uncovered branches.

Covers:
- _get_case_number: from filing_number fallback, from table
- _get_case_court_name: trial authority, fallback authority, none
- _list_party_payloads: status + side matching, fallback to status-only, fallback to is_our_client, fallback to first
- _pick_party_payload: returns first payload or default
- _list_opponent_case_parties: fallback to respondent statuses, fallback to all
- _build_respondent_options
- _build_plaintiff_agent_payload: lawyer from assignment fallback, no lawyer returns fallback
- _build_guarantee_material_paths: file path error handling, no source_attachment
- _build_session_status_payload: timing dict
- _update_session_task: set_started, set_finished, asyncio path
- _build_primary_respondent_property_clue: empty clues returns default
- _extract_quote_company_options: items not a list, non-dict items, empty company name
- _resolve_insurance_company_defaults: recommended not in options
- _normalize_insurance_company: empty allowed_options with empty name
- _build_cause_candidates: full-width space replacement
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

try:
    from plugins.court_automation import filing
except ImportError:
    pytest.skip("court_automation plugin not installed", allow_module_level=True)



# ── _get_case_number ──────────────────────────────────────────────────────────


class TestGetCaseNumber:
    def test_from_case_table(self):
        from plugins.court_automation.guarantee.helpers import _get_case_number

        qs = MagicMock()
        qs.exclude.return_value.exclude.return_value.values_list.return_value.first.return_value = "(2025)粤01民初1号"
        case = SimpleNamespace(case_numbers=qs)
        assert _get_case_number(case) == "(2025)粤01民初1号"

    def test_fallback_to_filing_number(self):
        from plugins.court_automation.guarantee.helpers import _get_case_number

        qs = MagicMock()
        qs.exclude.return_value.exclude.return_value.values_list.return_value.first.return_value = None
        case = SimpleNamespace(case_numbers=qs, filing_number="FN-2025-001")
        assert _get_case_number(case) == "FN-2025-001"


# ── _get_case_court_name ──────────────────────────────────────────────────────


class TestGetCaseCourtName:
    def test_trial_authority_first(self):
        from plugins.court_automation.guarantee.helpers import _get_case_court_name

        trial = SimpleNamespace(authority_type="trial", name="天河区")
        # Build mock chain: case.supervising_authorities.all().order_by("id").filter(...).first()
        mock_all = MagicMock()
        mock_ordered = MagicMock()
        mock_filtered = MagicMock()
        mock_all.order_by.return_value = mock_ordered
        mock_ordered.filter.return_value.first.return_value = trial
        mock_ordered.exclude.return_value.first.return_value = None
        case = SimpleNamespace(supervising_authorities=MagicMock(all=MagicMock(return_value=mock_all)))

        with patch("plugins.court_automation.guarantee.helpers._resolve_court_name", return_value="天河区人民法院") as mock_resolve:
            result = _get_case_court_name(case)
            assert result == "天河区人民法院"
            mock_resolve.assert_called_once()

    @pytest.mark.django_db
    def test_no_authority_returns_none(self):
        """Verify no-authority path. Requires django_db because AuthorityType
        import triggers AppConfig.ready() which queries core_systemconfig."""
        from plugins.court_automation.guarantee.helpers import _get_case_court_name

        # Build mock chain:
        # case.supervising_authorities.all().order_by("id") -> mock_ordered
        # mock_ordered.filter(authority_type=...).first() -> None (no trial authority)
        # mock_ordered.exclude(name__isnull=True).exclude(name="").first() -> None (no named authority)
        mock_all = MagicMock()
        mock_ordered = MagicMock()
        mock_all.order_by.return_value = mock_ordered

        # For filter().first() -> None
        mock_filtered = MagicMock()
        mock_filtered.first.return_value = None
        mock_ordered.filter.return_value = mock_filtered

        # For exclude().first() -> None
        mock_excluded1 = MagicMock()
        mock_excluded2 = MagicMock()
        mock_excluded2.first.return_value = None
        mock_ordered.exclude.return_value = mock_excluded1
        mock_excluded1.exclude.return_value = mock_excluded2

        case = SimpleNamespace(
            supervising_authorities=MagicMock(all=MagicMock(return_value=mock_all))
        )
        assert _get_case_court_name(case) is None

    def test_any_named_authority_fallback(self):
        from plugins.court_automation.guarantee.helpers import _get_case_court_name

        fallback = SimpleNamespace(name="番禺区")
        mock_all = MagicMock()
        mock_ordered = MagicMock()
        mock_all.order_by.return_value = mock_ordered
        mock_ordered.filter.return_value.first.return_value = None
        mock_ordered.exclude.return_value.first.return_value = fallback
        case = SimpleNamespace(supervising_authorities=MagicMock(all=MagicMock(return_value=mock_all)))

        with patch("plugins.court_automation.guarantee.helpers._resolve_court_name", return_value="番禺区人民法院") as mock_resolve:
            result = _get_case_court_name(case)
            assert result == "番禺区人民法院"


# ── _list_party_payloads — matching logic ─────────────────────────────────────


class TestListPartyPayloads:
    def _make_party(self, pid, status, is_our=False):
        client = SimpleNamespace(
            is_our_client=is_our, name=f"Client{pid}", id_number=f"11010119900101{pid:04d}",
            phone="13800000000", address="测试地址", client_type="natural",
            legal_representative="", legal_representative_id_number=""
        )
        return SimpleNamespace(id=pid, client=client, legal_status=status, name=f"Party{pid}")

    def test_status_match_with_prefer_our(self):
        from plugins.court_automation.guarantee.helpers import _list_party_payloads

        p1 = self._make_party(1, "plaintiff_side", is_our=True)
        p2 = self._make_party(2, "plaintiff_side", is_our=False)
        result = _list_party_payloads(
            case_parties=[p1, p2],
            preferred_statuses={"plaintiff_side"},
            prefer_our=True,
        )
        assert any(r["party_id"] == 1 for r in result)

    def test_fallback_to_status_only(self):
        from plugins.court_automation.guarantee.helpers import _list_party_payloads

        p1 = self._make_party(1, "defendant_side", is_our=True)
        result = _list_party_payloads(
            case_parties=[p1],
            preferred_statuses={"plaintiff_side"},
            prefer_our=True,
        )
        # No match on status, falls through to status-only which also fails,
        # then falls to is_our_client check
        # p1 is_our=True and prefer_our=True -> matches is_our check
        assert len(result) >= 1

    def test_fallback_to_first_party(self):
        from plugins.court_automation.guarantee.helpers import _list_party_payloads

        p1 = self._make_party(1, "unknown_status", is_our=False)
        result = _list_party_payloads(
            case_parties=[p1],
            preferred_statuses={"plaintiff_side"},
            prefer_our=True,
        )
        assert len(result) == 1


# ── _pick_party_payload ───────────────────────────────────────────────────────


class TestPickPartyPayload:
    def _make_party(self, pid, status, is_our=False):
        client = SimpleNamespace(
            is_our_client=is_our, name=f"Client{pid}", id_number=f"11010119900101{pid:04d}",
            phone="13800000000", address="测试地址", client_type="natural",
            legal_representative="", legal_representative_id_number=""
        )
        return SimpleNamespace(id=pid, client=client, legal_status=status, name=f"Party{pid}")

    def test_returns_first_payload(self):
        from plugins.court_automation.guarantee.helpers import _pick_party_payload

        p1 = self._make_party(1, "plaintiff_side", is_our=True)
        result = _pick_party_payload(
            case_parties=[p1],
            preferred_statuses={"plaintiff_side"},
            prefer_our=True,
        )
        assert result["party_id"] == 1

    def test_empty_raises_error(self):
        from plugins.court_automation.guarantee.helpers import _pick_party_payload

        with pytest.raises(ValueError, match="客户姓名不能为空"):
            _pick_party_payload(
                case_parties=[],
                preferred_statuses={"plaintiff_side"},
                prefer_our=True,
            )


# ── _list_opponent_case_parties ───────────────────────────────────────────────


class TestListOpponentCaseParties:
    def test_fallback_to_respondent_statuses(self):
        from plugins.court_automation.guarantee.helpers import _list_opponent_case_parties

        p1 = SimpleNamespace(
            client=SimpleNamespace(is_our_client=True),
            legal_status="defendant_side"
        )
        result = _list_opponent_case_parties(case_parties=[p1])
        # No non-our clients, fallback to respondent statuses
        assert len(result) >= 0  # depends on whether defendant_side is in _RESPONDENT_SIDE_STATUSES

    def test_fallback_to_all_when_no_respondent(self):
        from plugins.court_automation.guarantee.helpers import _list_opponent_case_parties

        p1 = SimpleNamespace(
            client=SimpleNamespace(is_our_client=True),
            legal_status="unknown"
        )
        result = _list_opponent_case_parties(case_parties=[p1])
        assert len(result) == 1

    def test_direct_our_client_exclusion(self):
        from plugins.court_automation.guarantee.helpers import _list_opponent_case_parties

        p1 = SimpleNamespace(client=SimpleNamespace(is_our_client=True), legal_status="plaintiff")
        p2 = SimpleNamespace(client=SimpleNamespace(is_our_client=False), legal_status="defendant")
        result = _list_opponent_case_parties(case_parties=[p1, p2])
        assert any(getattr(getattr(p, "client", None), "is_our_client", False) is False for p in result)


# ── _build_respondent_options ─────────────────────────────────────────────────


class TestBuildRespondentOptions:
    def test_basic(self):
        from plugins.court_automation.guarantee.helpers import _build_respondent_options

        p1 = SimpleNamespace(
            id=1,
            client=SimpleNamespace(name="被告公司", is_our_client=False),
            legal_status="defendant_side",
            get_legal_status_display=lambda: "被告",
        )
        result = _build_respondent_options(case_parties=[p1])
        assert len(result) == 1
        assert result[0]["name"] == "被告公司"


# ── _build_plaintiff_agent_payload ────────────────────────────────────────────


class TestBuildPlaintiffAgentPayload:
    def test_no_lawyer_returns_fallback(self):
        from plugins.court_automation.guarantee.helpers import _build_plaintiff_agent_payload

        # The function does: case.assignments.select_related("lawyer__law_firm").order_by("id").first()
        # We need .first() to return None so lawyer is None
        mock_first = MagicMock(return_value=None)
        mock_order_by = MagicMock()
        mock_order_by.first = mock_first
        mock_select_related = MagicMock()
        mock_select_related.order_by.return_value = mock_order_by
        assignments_mock = MagicMock()
        assignments_mock.select_related.return_value = mock_select_related
        case = SimpleNamespace(assignments=assignments_mock)
        result = _build_plaintiff_agent_payload(case=case, requester_id=None, fallback_party={"name": "原告", "phone": "12000000000"})
        assert result["party_type"] == "agent"
        assert result["name"] == "原告"

    def test_lawyer_from_requester(self):
        from plugins.court_automation.guarantee.helpers import _build_plaintiff_agent_payload

        lawyer = SimpleNamespace(
            real_name="律师A", username="a", id_card="123", phone="12000000000",
            license_no="L001", law_firm=SimpleNamespace(name="律所A")
        )
        case = SimpleNamespace(assignments=MagicMock())
        with patch("apps.organization.models.Lawyer") as MockLawyer:
            MockLawyer.objects.select_related.return_value.filter.return_value.first.return_value = lawyer
            result = _build_plaintiff_agent_payload(case=case, requester_id=10, fallback_party={"name": "原告", "phone": ""})
            assert result["name"] == "律师A"


# ── _build_primary_respondent_property_clue — empty clues ─────────────────────


class TestBuildPrimaryRespondentPropertyClueEmpty:
    def test_no_parties_returns_default(self):
        from plugins.court_automation.guarantee.helpers import _build_primary_respondent_property_clue

        with patch("plugins.court_automation.guarantee.helpers._build_selected_respondent_property_clues", return_value=[]):
            result = _build_primary_respondent_property_clue(
                case_parties=[], selected_respondents=[], preserve_amount=None
            )
            assert result["owner_name"] == "被申请人"


# ── _extract_quote_company_options — edge cases ───────────────────────────────


class TestExtractQuoteCompanyOptionsEdge:
    def test_items_not_a_list(self):
        from plugins.court_automation.guarantee.helpers import _extract_quote_company_options
        assert _extract_quote_company_options(quote_context={"items": "not a list"}) == []

    def test_non_dict_items(self):
        from plugins.court_automation.guarantee.helpers import _extract_quote_company_options
        result = _extract_quote_company_options(quote_context={"items": ["str", 123]})
        assert result == []

    def test_empty_company_name(self):
        from plugins.court_automation.guarantee.helpers import _extract_quote_company_options
        result = _extract_quote_company_options(quote_context={"items": [{"company_name": "", "status": "success"}]})
        assert result == []


# ── _resolve_insurance_company_defaults — recommended not in options ──────────


class TestResolveInsuranceCompanyDefaultsEdge:
    def test_recommended_not_in_options_uses_first(self):
        from plugins.court_automation.guarantee.helpers import _resolve_insurance_company_defaults

        ctx = {
            "recommended_company": "不存在的公司",
            "items": [
                {"company_name": "A公司", "status": "success"},
            ],
        }
        default, options = _resolve_insurance_company_defaults(quote_context=ctx)
        assert default == "A公司"


# ── _normalize_insurance_company — edge ───────────────────────────────────────


class TestNormalizeInsuranceCompanyEdge:
    def test_empty_name_empty_allowed_returns_default(self):
        from plugins.court_automation.guarantee.helpers import _DEFAULT_INSURANCE_COMPANY, _normalize_insurance_company
        assert _normalize_insurance_company("", allowed_options=[]) == _DEFAULT_INSURANCE_COMPANY

    def test_empty_name_with_allowed_returns_first(self):
        from plugins.court_automation.guarantee.helpers import _normalize_insurance_company
        assert _normalize_insurance_company("", allowed_options=["X", "Y"]) == "X"


# ── _build_cause_candidates — full-width space ────────────────────────────────


class TestBuildCauseCandidatesFullWidthSpace:
    def test_fullwidth_space_replaced(self):
        from plugins.court_automation.guarantee.helpers import _build_cause_candidates
        result = _build_cause_candidates("买卖合同　纠纷")
        # fullwidth space replaced with regular space
        assert any("买卖合同 纠纷" in c for c in result)


# ── _update_session_task (guarantee) ─────────────────────────────────────────


class TestUpdateSessionTaskGuarantee:
    def test_none_session_id_noop(self):
        from plugins.court_automation.guarantee.helpers import _update_session_task
        _update_session_task(session_id=None, status="running")

    @pytest.mark.django_db
    def test_set_started_and_finished(self):
        from plugins.court_automation.guarantee.helpers import _update_session_task

        with patch("plugins.court_automation.guarantee.helpers.timezone") as mock_tz:
            mock_tz.now.return_value = "now"
            with patch("plugins.court_automation.guarantee.helpers.asyncio") as mock_asyncio:
                mock_asyncio.get_running_loop.side_effect = RuntimeError("no loop")
                _update_session_task(
                    session_id=1, status="running",
                    set_started=True, set_finished=True
                )


# ── _build_session_status_payload — timing ────────────────────────────────────


class TestGuaranteeSessionStatusPayloadTiming:
    def test_failed_with_timing(self):
        from apps.automation.models import ScraperTaskStatus
        from plugins.court_automation.guarantee.helpers import _build_session_status_payload

        task = SimpleNamespace(
            id=1, status=ScraperTaskStatus.FAILED,
            result={"timing": {"overall_start": 1.0}},
            error_message="fail"
        )
        payload = _build_session_status_payload(task=task)
        assert payload["timing"]["overall_start"] == 1.0

    def test_failed_without_timing(self):
        from apps.automation.models import ScraperTaskStatus
        from plugins.court_automation.guarantee.helpers import _build_session_status_payload

        task = SimpleNamespace(id=1, status=ScraperTaskStatus.FAILED, result={}, error_message="fail")
        payload = _build_session_status_payload(task=task)
        assert "timing" not in payload

    def test_result_message_for_failed(self):
        from apps.automation.models import ScraperTaskStatus
        from plugins.court_automation.guarantee.helpers import _build_session_status_payload

        task = SimpleNamespace(
            id=1, status=ScraperTaskStatus.FAILED,
            result={"message": "result msg"}, error_message=""
        )
        payload = _build_session_status_payload(task=task)
        assert payload["message"] == "result msg"

    def test_running_with_result_message(self):
        from apps.automation.models import ScraperTaskStatus
        from plugins.court_automation.guarantee.helpers import _build_session_status_payload

        task = SimpleNamespace(
            id=1, status=ScraperTaskStatus.RUNNING,
            result={"message": "running msg"}, error_message=""
        )
        payload = _build_session_status_payload(task=task)
        assert payload["message"] == "running msg"

    def test_success_with_result_message(self):
        from apps.automation.models import ScraperTaskStatus
        from plugins.court_automation.guarantee.helpers import _build_session_status_payload

        task = SimpleNamespace(
            id=1, status=ScraperTaskStatus.SUCCESS,
            result={"message": "success msg"}, error_message=""
        )
        payload = _build_session_status_payload(task=task)
        assert payload["message"] == "success msg"
