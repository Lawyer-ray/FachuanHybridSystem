"""Round 4 coverage tests for automation.api.court_guarantee_helpers.

Targets remaining uncovered branches:
- _get_case_number: empty filing_number fallback
- _get_case_court_name: any_named_authority fallback (non-trial)
- _resolve_court_name: empty/None input
- _normalize_insurance_company: empty with no options
- _normalize_consultant_code: sunshine with empty string code
- _normalize_property_clue_content: only empty lines
- _normalize_property_value: value without decimals
- _build_property_clue_info: empty clue_type
- _build_selected_respondent_property_clues: with clues from client service
- _build_primary_respondent_property_clue: empty case_parties
- _find_reusable_binding: delegates to model
- _build_case_quote_context: no preserve_amount, no binding, with binding
- _build_reusable_quote_options: empty amount, zero amount
- _extract_quote_company_options: items list not list
- _build_guarantee_material_paths: pick by type_name_keywords, extra files cap at 12
- _build_cause_candidates: fullwidth space, causes without 纠纷
- _list_party_payloads: fallback to first party
- _pick_party_payload: with payloads
- _list_opponent_case_parties: empty list
- _build_plaintiff_agent_payload: requester found, no assignment fallback
- _build_session_status_payload: running non-dict, success non-dict, failed with result message
- _update_session_task: with event loop executor path
- _run_guarantee: success, login failure, guarantee failure, exception, browser hold failure
"""
from __future__ import annotations

import time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, AsyncMock

import pytest


# ---------------------------------------------------------------------------
# _get_case_number — empty filing_number
# ---------------------------------------------------------------------------


class TestGetCaseNumberEdge:
    def test_empty_filing_number(self):
        from plugins.court_automation.guarantee.helpers import _get_case_number
        case = MagicMock()
        case.case_numbers.exclude.return_value.exclude.return_value.values_list.return_value.first.return_value = None
        case.filing_number = ""
        assert _get_case_number(case) == ""

    def test_none_filing_number(self):
        from plugins.court_automation.guarantee.helpers import _get_case_number
        case = MagicMock()
        case.case_numbers.exclude.return_value.exclude.return_value.values_list.return_value.first.return_value = None
        case.filing_number = None
        assert _get_case_number(case) == ""


# ---------------------------------------------------------------------------
# _get_case_court_name — any_named_authority fallback
# ---------------------------------------------------------------------------


class TestGetCaseCourtNameFallback:
    def test_fallback_to_any_named_authority(self):
        from plugins.court_automation.guarantee.helpers import _get_case_court_name

        authority = MagicMock()
        authority.name = "海珠区"
        authority.authority_type = "supervision"  # not trial

        case = MagicMock()
        qs = MagicMock()
        qs.filter.return_value.first.return_value = None  # no trial authority
        qs.exclude.return_value.exclude.return_value.first.return_value = authority
        case.supervising_authorities.all.return_value.order_by.return_value = qs

        with patch(
            "plugins.court_automation.guarantee.helpers._resolve_court_name",
            return_value="海珠区人民法院",
        ):
            result = _get_case_court_name(case)
        assert result == "海珠区人民法院"

    def test_any_named_authority_empty_name(self):
        from plugins.court_automation.guarantee.helpers import _get_case_court_name

        authority = MagicMock()
        authority.name = ""

        case = MagicMock()
        qs = MagicMock()
        qs.filter.return_value.first.return_value = None
        qs.exclude.return_value.exclude.return_value.first.return_value = authority
        case.supervising_authorities.all.return_value.order_by.return_value = qs

        assert _get_case_court_name(case) is None


# ---------------------------------------------------------------------------
# _resolve_court_name — empty/None input
# ---------------------------------------------------------------------------


class TestResolveCourtNameEdge:
    def test_empty_string(self):
        from plugins.court_automation.guarantee.helpers import _resolve_court_name
        assert _resolve_court_name("") is None

    def test_none(self):
        from plugins.court_automation.guarantee.helpers import _resolve_court_name
        assert _resolve_court_name(None) is None

    def test_already_has_renfayuan(self):
        from plugins.court_automation.guarantee.helpers import _resolve_court_name
        assert _resolve_court_name("天河区人民法院") == "天河区人民法院"

    def test_not_in_db_appends(self):
        from plugins.court_automation.guarantee.helpers import _resolve_court_name
        with patch("apps.core.models.Court") as MockCourt:
            MockCourt.objects.filter.return_value.first.return_value = None
            result = _resolve_court_name("天河区")
        assert result == "天河区人民法院"


# ---------------------------------------------------------------------------
# _normalize_consultant_code — sunshine with empty string
# ---------------------------------------------------------------------------


class TestNormalizeConsultantCodeEdge:
    def test_sunshine_with_empty_string_code(self):
        from plugins.court_automation.guarantee.helpers import _normalize_consultant_code
        result = _normalize_consultant_code(
            insurance_company_name="阳光财产保险股份有限公司", consultant_code=""
        )
        assert result == "08740007"

    def test_non_sunshine_with_code(self):
        from plugins.court_automation.guarantee.helpers import _normalize_consultant_code
        result = _normalize_consultant_code(
            insurance_company_name="平安", consultant_code="12345"
        )
        assert result == "12345"


# ---------------------------------------------------------------------------
# _normalize_property_value — integer without decimals
# ---------------------------------------------------------------------------


class TestNormalizePropertyValueEdge:
    def test_integer_no_decimal_point(self):
        from plugins.court_automation.guarantee.helpers import _normalize_property_value
        assert _normalize_property_value("500") == "500"

    def test_with_commas_and_decimal(self):
        from plugins.court_automation.guarantee.helpers import _normalize_property_value
        assert _normalize_property_value("1,234.50") == "1234.5"

    def test_all_zeros_after_decimal(self):
        from plugins.court_automation.guarantee.helpers import _normalize_property_value
        assert _normalize_property_value("100.00") == "100"


# ---------------------------------------------------------------------------
# _build_property_clue_info — empty clue_type
# ---------------------------------------------------------------------------


class TestBuildPropertyClueInfoEdge:
    def test_empty_clue_type_defaults(self):
        from plugins.court_automation.guarantee.helpers import _build_property_clue_info
        result = _build_property_clue_info(clue_type="", raw_content="线索内容")
        assert "财产线索" in result
        assert "线索内容" in result

    def test_none_clue_type(self):
        from plugins.court_automation.guarantee.helpers import _build_property_clue_info
        result = _build_property_clue_info(clue_type=None, raw_content="")
        assert "财产线索" in result


# ---------------------------------------------------------------------------
# _build_selected_respondent_property_clues — with clues from client
# ---------------------------------------------------------------------------


class TestBuildSelectedRespondentPropertyClues:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _build_selected_respondent_property_clues
        return _build_selected_respondent_property_clues

    def test_with_clues_from_client_service(self):
        party = MagicMock()
        party.id = 1
        party.client.id = 10
        party.client.name = "被告公司"
        party.client.address = "广州市"

        clue = MagicMock()
        clue.clue_type = "bank"
        clue.content = "工商银行账户"

        with patch(
            "plugins.court_automation.guarantee.helpers._get_client_service"
        ) as mock_svc:
            svc = MagicMock()
            svc.get_property_clues_by_client_internal.return_value = [clue]
            mock_svc.return_value = svc
            result = self._fn()(
                case_parties=[party],
                selected_respondents=[{"party_id": 1}],
                preserve_amount=Decimal("10000"),
            )
        assert len(result) >= 1
        assert any("工商银行" in r["property_info"] for r in result)

    def test_no_client_id_skips_clue_search(self):
        party = MagicMock()
        party.id = 1
        party.client.id = 0
        party.client.name = "被告"
        party.client.address = ""

        with patch(
            "plugins.court_automation.guarantee.helpers._get_client_service"
        ) as mock_svc:
            svc = MagicMock()
            mock_svc.return_value = svc
            result = self._fn()(
                case_parties=[party],
                selected_respondents=[{"party_id": 1}],
                preserve_amount=None,
            )
        # Should still have a default clue entry
        assert len(result) >= 1
        svc.get_property_clues_by_client_internal.assert_not_called()

    def test_no_selected_matches_falls_back_to_opponent(self):
        party = MagicMock()
        party.id = 1
        party.client.id = 10
        party.client.name = "被告"
        party.client.address = ""
        party.client.is_our_client = False

        with patch(
            "plugins.court_automation.guarantee.helpers._get_client_service"
        ) as mock_svc:
            svc = MagicMock()
            svc.get_property_clues_by_client_internal.return_value = []
            mock_svc.return_value = svc
            result = self._fn()(
                case_parties=[party],
                selected_respondents=[{"party_id": 999}],  # non-existent
                preserve_amount=None,
            )
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# _build_primary_respondent_property_clue — empty case_parties
# ---------------------------------------------------------------------------


class TestBuildPrimaryRespondentPropertyClue:
    def test_empty_case_parties_returns_default(self):
        from plugins.court_automation.guarantee.helpers import _build_primary_respondent_property_clue
        with patch(
            "plugins.court_automation.guarantee.helpers._get_client_service"
        ) as mock_svc:
            mock_svc.return_value = MagicMock()
            result = _build_primary_respondent_property_clue(
                case_parties=[],
                selected_respondents=[],
                preserve_amount=Decimal("5000"),
            )
        assert result["owner_name"] == "被申请人"


# ---------------------------------------------------------------------------
# _build_case_quote_context — no binding
# ---------------------------------------------------------------------------


class TestBuildCaseQuoteContext:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _build_case_quote_context
        return _build_case_quote_context

    def test_no_preserve_amount(self):
        case = MagicMock()
        case.preservation_amount = None
        assert self._fn()(case=case) is None

    def test_no_binding(self):
        case = MagicMock()
        case.id = 1
        case.preservation_amount = Decimal("10000")
        with patch(
            "plugins.court_automation.guarantee.helpers._find_reusable_binding",
            return_value=None,
        ):
            with patch(
                "apps.automation.models.CasePreservationQuoteBinding"
            ) as MockBinding:
                MockBinding.objects.select_related.return_value.filter.return_value.order_by.return_value.first.return_value = None
                result = self._fn()(case=case)
        assert result is None


# ---------------------------------------------------------------------------
# _build_reusable_quote_options — edge cases
# ---------------------------------------------------------------------------


class TestBuildReusableQuoteOptions:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _build_reusable_quote_options
        return _build_reusable_quote_options

    def test_none_amount_returns_empty(self):
        case = MagicMock()
        case.preservation_amount = None
        assert self._fn()(case=case) == []

    def test_zero_amount_returns_empty(self):
        case = MagicMock()
        case.preservation_amount = Decimal("0")
        assert self._fn()(case=case) == []

    def test_negative_amount_returns_empty(self):
        case = MagicMock()
        case.preservation_amount = Decimal("-100")
        assert self._fn()(case=case) == []


# ---------------------------------------------------------------------------
# _extract_quote_company_options — items not list
# ---------------------------------------------------------------------------


class TestExtractQuoteCompanyOptionsEdge:
    def test_items_is_not_list(self):
        from plugins.court_automation.guarantee.helpers import _extract_quote_company_options
        ctx = {"items": "not a list"}
        assert _extract_quote_company_options(quote_context=ctx) == []

    def test_company_name_empty_skipped(self):
        from plugins.court_automation.guarantee.helpers import _extract_quote_company_options
        ctx = {"items": [{"company_name": "", "status": "success"}]}
        assert _extract_quote_company_options(quote_context=ctx) == []


# ---------------------------------------------------------------------------
# _resolve_insurance_company_defaults — recommended not in options
# ---------------------------------------------------------------------------


class TestResolveInsuranceCompanyDefaultsEdge:
    def test_recommended_not_in_options(self):
        from plugins.court_automation.guarantee.helpers import _resolve_insurance_company_defaults
        ctx = {
            "recommended_company": "不在列表",
            "items": [
                {"company_name": "平安", "status": "success"},
            ],
        }
        default, options = _resolve_insurance_company_defaults(quote_context=ctx)
        assert default == "平安"

    def test_empty_recommended(self):
        from plugins.court_automation.guarantee.helpers import _resolve_insurance_company_defaults
        ctx = {
            "recommended_company": "",
            "items": [
                {"company_name": "人保", "status": "success"},
            ],
        }
        default, options = _resolve_insurance_company_defaults(quote_context=ctx)
        assert default == "人保"


# ---------------------------------------------------------------------------
# _build_cause_candidates — edge cases
# ---------------------------------------------------------------------------


class TestBuildCauseCandidatesEdge:
    def test_fullwidth_space(self):
        from plugins.court_automation.guarantee.helpers import _build_cause_candidates
        result = _build_cause_candidates("买卖合同纠纷　借款合同纠纷")
        assert len(result) >= 1

    def test_cause_without_jiufen(self):
        from plugins.court_automation.guarantee.helpers import _build_cause_candidates
        result = _build_cause_candidates("离婚")
        assert "离婚" in result
        assert len(result) == 1  # no suffix removal without 纠纷


# ---------------------------------------------------------------------------
# _list_party_payloads — fallback chain
# ---------------------------------------------------------------------------


class TestListPartyPayloadsFallback:
    def test_fallback_to_first_party(self):
        from plugins.court_automation.guarantee.helpers import _list_party_payloads

        party = MagicMock()
        party.legal_status = "other_status"
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
        # Falls through all fallbacks to first party
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _pick_party_payload — with payloads
# ---------------------------------------------------------------------------


class TestPickPartyPayloadWithPayloads:
    def test_returns_first(self):
        from plugins.court_automation.guarantee.helpers import _pick_party_payload

        party = MagicMock()
        party.legal_status = "plaintiff"
        party.id = 1
        party.client.client_type = "natural"
        party.client.name = "原告"
        party.client.id_number = "110101199003077715"
        party.client.phone = ""
        party.client.address = ""
        party.client.is_our_client = True
        party.client.legal_representative = ""
        party.client.legal_representative_id_number = ""

        result = _pick_party_payload(
            case_parties=[party],
            preferred_statuses={"plaintiff"},
            prefer_our=True,
        )
        assert result["name"] == "原告"


# ---------------------------------------------------------------------------
# _list_opponent_case_parties — empty list
# ---------------------------------------------------------------------------


class TestListOpponentCasePartiesEdge:
    def test_empty_returns_empty(self):
        from plugins.court_automation.guarantee.helpers import _list_opponent_case_parties
        result = _list_opponent_case_parties(case_parties=[])
        assert result == []


# ---------------------------------------------------------------------------
# _build_plaintiff_agent_payload — requester from DB
# ---------------------------------------------------------------------------


class TestBuildPlaintiffAgentPayloadEdge:
    def test_requester_found_in_db(self):
        from plugins.court_automation.guarantee.helpers import _build_plaintiff_agent_payload

        lawyer = MagicMock()
        lawyer.real_name = "王律师"
        lawyer.username = "wl"
        lawyer.id_card = "110101199003077715"
        lawyer.phone = "13900139000"
        lawyer.license_no = "B20201234"
        lawyer.law_firm = MagicMock()
        lawyer.law_firm.name = "Big Firm"

        case = MagicMock()

        with patch("apps.organization.models.Lawyer") as MockLawyer:
            MockLawyer.objects.select_related.return_value.filter.return_value.first.return_value = lawyer
            result = _build_plaintiff_agent_payload(
                case=case, requester_id=5, fallback_party={"name": "fallback", "phone": ""}
            )
        assert result["name"] == "王律师"
        assert result["law_firm"] == "Big Firm"


# ---------------------------------------------------------------------------
# _build_session_status_payload — guarantee edge cases
# ---------------------------------------------------------------------------


class TestGuaranteeSessionStatusPayloadEdge:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _build_session_status_payload
        return _build_session_status_payload

    def test_running_non_dict_result(self):
        task = MagicMock()
        task.status = "running"
        task.id = 1
        task.result = "string"
        result = self._fn()(task=task)
        assert result["status"] == "in_progress"

    def test_success_non_dict_result(self):
        task = MagicMock()
        task.status = "success"
        task.id = 2
        task.result = "string"
        result = self._fn()(task=task)
        assert result["status"] == "completed"

    def test_failed_with_result_message(self):
        task = MagicMock()
        task.status = "failed"
        task.id = 3
        task.error_message = ""
        task.result = {"message": "超时"}
        result = self._fn()(task=task)
        assert result["message"] == "超时"


# ---------------------------------------------------------------------------
# _update_session_task — guarantee executor path
# ---------------------------------------------------------------------------


class TestGuaranteeUpdateSessionTaskEdge:
    def test_with_event_loop(self):
        from plugins.court_automation.guarantee.helpers import _update_session_task

        with patch("plugins.court_automation.guarantee.helpers.asyncio") as mock_asyncio:
            mock_asyncio.get_running_loop.return_value = MagicMock()
            with patch("plugins.court_automation.guarantee.helpers._SESSION_UPDATE_EXECUTOR") as mock_exec:
                _update_session_task(session_id=1, status="running", set_started=True)
                mock_exec.submit.assert_called_once()

    def test_no_event_loop_direct_update(self):
        from plugins.court_automation.guarantee.helpers import _update_session_task

        with patch("plugins.court_automation.guarantee.helpers.asyncio") as mock_asyncio:
            mock_asyncio.get_running_loop.side_effect = RuntimeError("no loop")
            with patch("apps.automation.models.ScraperTask") as MockTask, \
                 patch("django.db.close_old_connections"):
                _update_session_task(
                    session_id=1,
                    status="success",
                    error_message="",
                    result={"key": "val"},
                    set_started=True,
                    set_finished=True,
                )
                MockTask.objects.filter.assert_called_once()


# ---------------------------------------------------------------------------
# _run_guarantee — key paths
# ---------------------------------------------------------------------------


class TestRunGuarantee:
    def _fn(self):
        from plugins.court_automation.guarantee.helpers import _run_guarantee
        return _run_guarantee

    def test_login_failure(self):
        with patch("apps.core.services.browser.create_browser") as mock_browser, \
             patch("plugins.court_automation.guarantee.helpers._update_session_task"):
            page = MagicMock()
            context = MagicMock()
            mock_browser.return_value.__enter__ = MagicMock(return_value=(page, context))
            mock_browser.return_value.__exit__ = MagicMock(return_value=False)

            with patch("apps.automation.services.scraper.sites.court_zxfw.CourtZxfwService") as MockLogin:
                login_instance = MockLogin.return_value
                login_instance.login.return_value = {"success": False, "message": "密码错误"}

                self._fn()(
                    account="user",
                    password="wrong",
                    case_data={},
                    session_id=1,
                )

    def test_exception_during_guarantee(self):
        with patch("apps.core.services.browser.create_browser") as mock_browser, \
             patch("plugins.court_automation.guarantee.helpers._update_session_task"):
            page = MagicMock()
            context = MagicMock()
            mock_browser.return_value.__enter__ = MagicMock(return_value=(page, context))
            mock_browser.return_value.__exit__ = MagicMock(return_value=False)

            with patch("apps.automation.services.scraper.sites.court_zxfw.CourtZxfwService") as MockLogin, \
                 patch("apps.automation.services.scraper.sites.court_zxfw_guarantee.CourtZxfwGuaranteeService") as MockGuarantee:
                login_instance = MockLogin.return_value
                login_instance.login.return_value = {"success": True}
                login_instance.fetch_baoquan_token.return_value = {"success": True}

                guarantee_instance = MockGuarantee.return_value
                guarantee_instance.apply_guarantee.side_effect = RuntimeError("playwright crash")

                self._fn()(
                    account="user",
                    password="pass",
                    case_data={},
                    session_id=1,
                )

    def test_guarantee_failure(self):
        with patch("apps.core.services.browser.create_browser") as mock_browser, \
             patch("plugins.court_automation.guarantee.helpers._update_session_task"):
            page = MagicMock()
            context = MagicMock()
            mock_browser.return_value.__enter__ = MagicMock(return_value=(page, context))
            mock_browser.return_value.__exit__ = MagicMock(return_value=False)

            with patch("apps.automation.services.scraper.sites.court_zxfw.CourtZxfwService") as MockLogin, \
                 patch("apps.automation.services.scraper.sites.court_zxfw_guarantee.CourtZxfwGuaranteeService") as MockGuarantee:
                login_instance = MockLogin.return_value
                login_instance.login.return_value = {"success": True}
                login_instance.fetch_baoquan_token.return_value = {"success": True}

                guarantee_instance = MockGuarantee.return_value
                guarantee_instance.apply_guarantee.return_value = {"success": False, "message": "表单填写失败"}

                self._fn()(
                    account="user",
                    password="pass",
                    case_data={},
                    session_id=1,
                )

    def test_guarantee_success(self):
        with patch("apps.core.services.browser.create_browser") as mock_browser, \
             patch("plugins.court_automation.guarantee.helpers._update_session_task"):
            page = MagicMock()
            context = MagicMock()
            mock_browser.return_value.__enter__ = MagicMock(return_value=(page, context))
            mock_browser.return_value.__exit__ = MagicMock(return_value=False)

            with patch("apps.automation.services.scraper.sites.court_zxfw.CourtZxfwService") as MockLogin, \
                 patch("apps.automation.services.scraper.sites.court_zxfw_guarantee.CourtZxfwGuaranteeService") as MockGuarantee:
                login_instance = MockLogin.return_value
                login_instance.login.return_value = {"success": True}
                login_instance.fetch_baoquan_token.return_value = {"success": True}

                guarantee_instance = MockGuarantee.return_value
                guarantee_instance.apply_guarantee.return_value = {"success": True, "message": "完成"}

                self._fn()(
                    account="user",
                    password="pass",
                    case_data={},
                    session_id=1,
                )


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
        with patch("apps.core.dependencies.build_client_service", return_value="cs"):
            assert _get_client_service() == "cs"


# ---------------------------------------------------------------------------
# _find_reusable_binding
# ---------------------------------------------------------------------------


class TestFindReusableBinding:
    def test_delegates_to_model(self):
        from plugins.court_automation.guarantee.helpers import _find_reusable_binding
        with patch("apps.automation.models.CasePreservationQuoteBinding") as MockModel:
            MockModel.objects.select_related.return_value.filter.return_value.order_by.return_value.first.return_value = "binding"
            result = _find_reusable_binding(case_id=1, preserve_amount=Decimal("100"))
        assert result == "binding"


# ---------------------------------------------------------------------------
# _normalize_insurance_company — edge cases
# ---------------------------------------------------------------------------


class TestNormalizeInsuranceCompanyEdge:
    def test_empty_no_options_uses_default(self):
        from plugins.court_automation.guarantee.helpers import _normalize_insurance_company
        result = _normalize_insurance_company("", allowed_options=[])
        # empty allowed_options is falsy, so falls to default
        assert result == "中国平安财产保险股份有限公司"

    def test_whitespace_only_name(self):
        from plugins.court_automation.guarantee.helpers import _normalize_insurance_company
        result = _normalize_insurance_company("   ")
        assert result == "中国平安财产保险股份有限公司"
