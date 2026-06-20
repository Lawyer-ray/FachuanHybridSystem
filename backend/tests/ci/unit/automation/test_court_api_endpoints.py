"""Tests for court_filing_api.py and court_guarantee_api.py endpoint logic."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _make_request(user_id: int = 1):
    req = MagicMock()
    req.user = SimpleNamespace(id=user_id)
    return req


# ======================================================================
# court_filing_api._check_plugin
# ======================================================================

class TestFilingCheckPlugin:
    def test_plugin_installed(self):
        with patch.dict("sys.modules", {"plugins": MagicMock(has_court_automation_plugin=lambda: True)}):
            from plugins.court_automation.filing.api_endpoint import _check_plugin
            assert _check_plugin() is True

    def test_plugin_not_installed(self):
        import sys
        saved = sys.modules.get("plugins")
        sys.modules.pop("plugins", None)
        try:
            from importlib import reload
            import plugins.court_automation.filing.api_endpoint as mod
            # _check_plugin catches ImportError, returns False
            result = mod._check_plugin()
            assert isinstance(result, bool)
        finally:
            if saved is not None:
                sys.modules["plugins"] = saved


# ======================================================================
# get_case_filing_info -- plugin not available
# ======================================================================

class TestGetCaseFilingInfoNoPlugin:
    def test_returns_empty_when_no_plugin(self):
        from plugins.court_automation.filing.api_endpoint import get_case_filing_info
        request = _make_request()
        with patch("plugins.court_automation.filing.api_endpoint._check_plugin", return_value=False):
            result = get_case_filing_info(request, case_id=42)
            assert result["case_id"] == 42
            assert result["plugin_available"] is False
            assert result["case_name"] == ""


# ======================================================================
# get_case_filing_info -- plugin available
# ======================================================================

class TestGetCaseFilingInfoWithPlugin:
    def test_full_flow(self):
        from plugins.court_automation.filing.api_endpoint import get_case_filing_info

        case = SimpleNamespace(
            id=1, name="测试案", cause_of_action="借款纠纷",
            target_amount=10000, case_numbers=None,
        )
        sa = SimpleNamespace(name="天河区", authority_type="trial")
        party = SimpleNamespace(
            legal_status="plaintiff",
            client=SimpleNamespace(name="原告公司", is_our_client=True),
        )

        with patch("plugins.court_automation.filing.api_endpoint._check_plugin", return_value=True), \
             patch("plugins.court_automation.filing.api_endpoint._resolve_court_name", return_value="天河区人民法院"), \
             patch("plugins.court_automation.filing.api_endpoint._get_organization_service") as MockOrg, \
             patch("plugins.court_automation.filing.api_endpoint._infer_filing_type", return_value="civil"), \
             patch("apps.cases.models.Case") as MockCase, \
             patch("apps.cases.models.SupervisingAuthority") as MockSA, \
             patch("apps.cases.models.CaseParty") as MockParty:
            MockCase.objects.get.return_value = case
            MockSA.objects.filter.return_value.first.return_value = sa
            MockParty.objects.filter.return_value.select_related.return_value = [party]
            MockOrg.return_value.has_credential_for_lawyer.return_value = True

            with patch.dict("sys.modules", {"plugins": MagicMock(has_court_filing_api_plugin=lambda: True)}):
                result = get_case_filing_info(_make_request(), case_id=1)
                assert result["case_id"] == 1
                assert result["case_name"] == "测试案"
                assert result["plugin_available"] is True
                assert result["our_party_is_plaintiff_side"] is True

    def test_no_sa_returns_none_court(self):
        from plugins.court_automation.filing.api_endpoint import get_case_filing_info

        case = SimpleNamespace(id=1, name="案", cause_of_action="", target_amount=None)
        with patch("plugins.court_automation.filing.api_endpoint._check_plugin", return_value=True), \
             patch("plugins.court_automation.filing.api_endpoint._get_organization_service") as MockOrg, \
             patch("plugins.court_automation.filing.api_endpoint._infer_filing_type", return_value="civil"), \
             patch("apps.cases.models.Case") as MockCase, \
             patch("apps.cases.models.SupervisingAuthority") as MockSA, \
             patch("apps.cases.models.CaseParty") as MockParty:
            MockCase.objects.get.return_value = case
            MockSA.objects.filter.return_value.first.return_value = None
            MockParty.objects.filter.return_value.select_related.return_value = []
            MockOrg.return_value.has_credential_for_lawyer.return_value = False

            result = get_case_filing_info(_make_request(), case_id=1)
            assert result["court_name"] is None
            assert result["has_court_credential"] is False


# ======================================================================
# get_court_filing_session_status
# ======================================================================

class TestGetCourtFilingSessionStatus:
    def test_not_found(self):
        from plugins.court_automation.filing.api_endpoint import get_court_filing_session_status
        with patch("apps.automation.models.ScraperTask") as MockTask, \
             patch("apps.automation.models.ScraperTaskType") as MockType:
            MockType.COURT_FILING = "court_filing"
            MockTask.objects.filter.return_value.first.return_value = None
            result = get_court_filing_session_status(_make_request(), session_id=999)
            assert result["success"] is False
            assert "不存在" in result["message"]

    def test_found(self):
        from plugins.court_automation.filing.api_endpoint import get_court_filing_session_status
        task = SimpleNamespace(id=1, status="success", result={"message": "完成"}, error_message="")
        with patch("apps.automation.models.ScraperTask") as MockTask, \
             patch("apps.automation.models.ScraperTaskType") as MockType, \
             patch("plugins.court_automation.filing.api_endpoint._build_session_status_payload", return_value={"ok": True}):
            MockType.COURT_FILING = "court_filing"
            MockTask.objects.filter.return_value.first.return_value = task
            result = get_court_filing_session_status(_make_request(), session_id=1)
            assert result == {"ok": True}


# ======================================================================
# execute_court_filing -- various error paths
# ======================================================================

# Common patch context for execute_court_filing that mocks all imported helpers
def _filing_patches(**overrides):
    """Return a dict of patches needed for execute_court_filing tests."""
    defaults = {
        "check_plugin": True,
        "filing_type": "civil",
        "filing_engine": "api",
        "credential": SimpleNamespace(account="u", password="p"),
        "sa": SimpleNamespace(name="天河区"),
        "court_name": "天河区人民法院",
        "party_payloads": ([{"p": 1}], [{"d": 1}], []),
        "agents": [{"name": "律师", "phone": "13800138000"}],  # pragma: allowlist secret
        "materials": {"0": [("/tmp/起诉状.pdf", "起诉状.pdf")]},
    }
    defaults.update(overrides)
    return defaults


class TestExecuteCourtFiling:
    def _make_payload(self, case_id=1, filing_type=None, filing_engine=None):
        return SimpleNamespace(case_id=case_id, filing_type=filing_type, filing_engine=filing_engine)

    def test_no_plugin(self):
        from plugins.court_automation.filing.api_endpoint import execute_court_filing
        with patch("plugins.court_automation.filing.api_endpoint._check_plugin", return_value=False):
            result = execute_court_filing(_make_request(), self._make_payload())
            assert result["success"] is False
            assert "插件未安装" in result["message"]

    def test_no_credential(self):
        from plugins.court_automation.filing.api_endpoint import execute_court_filing
        case = SimpleNamespace(id=1, name="", cause_of_action="")
        with patch("plugins.court_automation.filing.api_endpoint._check_plugin", return_value=True), \
             patch("plugins.court_automation.filing.api_endpoint._normalize_filing_type", return_value="civil"), \
             patch("plugins.court_automation.filing.api_endpoint._normalize_filing_engine", return_value="api"), \
             patch("plugins.court_automation.filing.api_endpoint._get_organization_service") as MockOrg, \
             patch("apps.cases.models.Case") as MockCase, \
             patch("apps.cases.models.CaseParty") as MockParty, \
             patch("apps.cases.models.SupervisingAuthority"):
            MockCase.objects.get.return_value = case
            MockParty.objects.filter.return_value.select_related.return_value = []
            MockOrg.return_value.get_credential_for_lawyer.return_value = None
            result = execute_court_filing(_make_request(), self._make_payload())
            assert result["success"] is False
            assert "凭证" in result["message"]

    def test_no_supervising_authority(self):
        from plugins.court_automation.filing.api_endpoint import execute_court_filing
        case = SimpleNamespace(id=1, name="", cause_of_action="")
        with patch("plugins.court_automation.filing.api_endpoint._check_plugin", return_value=True), \
             patch("plugins.court_automation.filing.api_endpoint._normalize_filing_type", return_value="civil"), \
             patch("plugins.court_automation.filing.api_endpoint._normalize_filing_engine", return_value="api"), \
             patch("plugins.court_automation.filing.api_endpoint._get_organization_service") as MockOrg, \
             patch("apps.cases.models.Case") as MockCase, \
             patch("apps.cases.models.CaseParty") as MockParty, \
             patch("apps.cases.models.SupervisingAuthority") as MockSA:
            MockCase.objects.get.return_value = case
            MockParty.objects.filter.return_value.select_related.return_value = []
            MockOrg.return_value.get_credential_for_lawyer.return_value = SimpleNamespace(account="u", password="p")
            MockSA.objects.filter.return_value.first.return_value = None
            result = execute_court_filing(_make_request(), self._make_payload())
            assert result["success"] is False
            assert "管辖法院" in result["message"]

    def test_no_plaintiffs(self):
        from plugins.court_automation.filing.api_endpoint import execute_court_filing
        case = SimpleNamespace(id=1, name="", cause_of_action="", target_amount=None)
        with patch("plugins.court_automation.filing.api_endpoint._check_plugin", return_value=True), \
             patch("plugins.court_automation.filing.api_endpoint._normalize_filing_type", return_value="civil"), \
             patch("plugins.court_automation.filing.api_endpoint._normalize_filing_engine", return_value="api"), \
             patch("plugins.court_automation.filing.api_endpoint._resolve_court_name", return_value="天河区人民法院"), \
             patch("plugins.court_automation.filing.api_endpoint._get_organization_service") as MockOrg, \
             patch("plugins.court_automation.filing.api_endpoint._build_party_payloads", return_value=([], [{"d": 1}], [])), \
             patch("apps.cases.models.Case") as MockCase, \
             patch("apps.cases.models.CaseParty") as MockParty, \
             patch("apps.cases.models.SupervisingAuthority") as MockSA, \
             patch("apps.core.models.Court") as MockCourt:
            MockCase.objects.get.return_value = case
            MockSA.objects.filter.return_value.first.return_value = SimpleNamespace(name="天河区")
            MockParty.objects.filter.return_value.select_related.return_value = []
            MockOrg.return_value.get_credential_for_lawyer.return_value = SimpleNamespace(account="u", password="p")
            MockCourt.objects.filter.return_value.first.return_value = None
            result = execute_court_filing(_make_request(), self._make_payload())
            assert result["success"] is False
            assert "原告" in result["message"] or "当事人" in result["message"]

    def test_no_defendants(self):
        from plugins.court_automation.filing.api_endpoint import execute_court_filing
        case = SimpleNamespace(id=1, name="", cause_of_action="", target_amount=None)
        with patch("plugins.court_automation.filing.api_endpoint._check_plugin", return_value=True), \
             patch("plugins.court_automation.filing.api_endpoint._normalize_filing_type", return_value="civil"), \
             patch("plugins.court_automation.filing.api_endpoint._normalize_filing_engine", return_value="api"), \
             patch("plugins.court_automation.filing.api_endpoint._resolve_court_name", return_value="天河区人民法院"), \
             patch("plugins.court_automation.filing.api_endpoint._get_organization_service") as MockOrg, \
             patch("plugins.court_automation.filing.api_endpoint._build_party_payloads", return_value=([{"p": 1}], [], [])), \
             patch("apps.cases.models.Case") as MockCase, \
             patch("apps.cases.models.CaseParty") as MockParty, \
             patch("apps.cases.models.SupervisingAuthority") as MockSA, \
             patch("apps.core.models.Court") as MockCourt:
            MockCase.objects.get.return_value = case
            MockSA.objects.filter.return_value.first.return_value = SimpleNamespace(name="天河区")
            MockParty.objects.filter.return_value.select_related.return_value = []
            MockOrg.return_value.get_credential_for_lawyer.return_value = SimpleNamespace(account="u", password="p")
            MockCourt.objects.filter.return_value.first.return_value = None
            result = execute_court_filing(_make_request(), self._make_payload())
            assert result["success"] is False
            assert "被告" in result["message"] or "当事人" in result["message"]

    def test_no_agents(self):
        from plugins.court_automation.filing.api_endpoint import execute_court_filing
        case = SimpleNamespace(id=1, name="", cause_of_action="", target_amount=None)
        with patch("plugins.court_automation.filing.api_endpoint._check_plugin", return_value=True), \
             patch("plugins.court_automation.filing.api_endpoint._normalize_filing_type", return_value="civil"), \
             patch("plugins.court_automation.filing.api_endpoint._normalize_filing_engine", return_value="api"), \
             patch("plugins.court_automation.filing.api_endpoint._resolve_court_name", return_value="天河区人民法院"), \
             patch("plugins.court_automation.filing.api_endpoint._get_organization_service") as MockOrg, \
             patch("plugins.court_automation.filing.api_endpoint._build_party_payloads", return_value=([{"p": 1}], [{"d": 1}], [])), \
             patch("plugins.court_automation.filing.api_endpoint._build_agent_payloads", return_value=[]), \
             patch("apps.cases.models.Case") as MockCase, \
             patch("apps.cases.models.CaseParty") as MockParty, \
             patch("apps.cases.models.SupervisingAuthority") as MockSA, \
             patch("apps.core.models.Court") as MockCourt:
            MockCase.objects.get.return_value = case
            MockSA.objects.filter.return_value.first.return_value = SimpleNamespace(name="天河区")
            MockParty.objects.filter.return_value.select_related.return_value = []
            MockOrg.return_value.get_credential_for_lawyer.return_value = SimpleNamespace(account="u", password="p")
            MockCourt.objects.filter.return_value.first.return_value = None
            result = execute_court_filing(_make_request(), self._make_payload())
            assert result["success"] is False
            assert "代理律师" in result["message"]

    def test_no_materials(self):
        from plugins.court_automation.filing.api_endpoint import execute_court_filing
        case = SimpleNamespace(id=1, name="", cause_of_action="", target_amount=None)
        with patch("plugins.court_automation.filing.api_endpoint._check_plugin", return_value=True), \
             patch("plugins.court_automation.filing.api_endpoint._normalize_filing_type", return_value="civil"), \
             patch("plugins.court_automation.filing.api_endpoint._normalize_filing_engine", return_value="api"), \
             patch("plugins.court_automation.filing.api_endpoint._resolve_court_name", return_value="天河区人民法院"), \
             patch("plugins.court_automation.filing.api_endpoint._get_organization_service") as MockOrg, \
             patch("plugins.court_automation.filing.api_endpoint._build_party_payloads", return_value=([{"p": 1}], [{"d": 1}], [])), \
             patch("plugins.court_automation.filing.api_endpoint._build_agent_payloads", return_value=[{"name": "律师"}]), \
             patch("plugins.court_automation.filing.api_endpoint._build_materials_map", return_value={}), \
             patch("apps.cases.models.Case") as MockCase, \
             patch("apps.cases.models.CaseParty") as MockParty, \
             patch("apps.cases.models.SupervisingAuthority") as MockSA, \
             patch("apps.core.models.Court") as MockCourt:
            MockCase.objects.get.return_value = case
            MockSA.objects.filter.return_value.first.return_value = SimpleNamespace(name="天河区")
            MockParty.objects.filter.return_value.select_related.return_value = []
            MockOrg.return_value.get_credential_for_lawyer.return_value = SimpleNamespace(account="u", password="p")
            MockCourt.objects.filter.return_value.first.return_value = None
            result = execute_court_filing(_make_request(), self._make_payload())
            assert result["success"] is False
            assert "PDF" in result["message"] or "材料" in result["message"]


# ======================================================================
# court_guarantee_api tests
# ======================================================================

class TestGuaranteeCheckPlugin:
    def test_returns_bool(self):
        with patch.dict("sys.modules", {"plugins": MagicMock(has_court_automation_plugin=lambda: True)}):
            from plugins.court_automation.guarantee.api_endpoint import _check_plugin
            assert _check_plugin() is True


class TestGetCaseGuaranteeInfoNoPlugin:
    def test_returns_empty_when_no_plugin(self):
        from plugins.court_automation.guarantee.api_endpoint import get_case_guarantee_info
        with patch("plugins.court_automation.guarantee.api_endpoint._check_plugin", return_value=False):
            result = get_case_guarantee_info(_make_request(), case_id=10)
            assert result["case_id"] == 10
            assert result["plugin_available"] is False


class TestGetCourtGuaranteeSessionStatus:
    def test_not_found(self):
        from plugins.court_automation.guarantee.api_endpoint import get_court_guarantee_session_status
        with patch("apps.automation.models.ScraperTask") as MockTask:
            MockTask.objects.filter.return_value.first.return_value = None
            result = get_court_guarantee_session_status(_make_request(), session_id=999)
            assert result["success"] is False

    def test_found(self):
        from plugins.court_automation.guarantee.api_endpoint import get_court_guarantee_session_status
        task = SimpleNamespace(id=1, status="success", result={}, error_message="")
        with patch("apps.automation.models.ScraperTask") as MockTask, \
             patch("plugins.court_automation.guarantee.api_endpoint._build_session_status_payload", return_value={"ok": True}):
            MockTask.objects.filter.return_value.first.return_value = task
            result = get_court_guarantee_session_status(_make_request(), session_id=1)
            assert result == {"ok": True}


class TestExecuteCourtGuarantee:
    def _make_payload(self, **kwargs):
        defaults = {"case_id": 1, "insurance_company_name": None, "consultant_code": None, "selected_respondent_ids": None}
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_no_plugin(self):
        from plugins.court_automation.guarantee.api_endpoint import execute_court_guarantee
        with patch("plugins.court_automation.guarantee.api_endpoint._check_plugin", return_value=False):
            result = execute_court_guarantee(_make_request(), self._make_payload())
            assert result["success"] is False

    def test_no_credential(self):
        from plugins.court_automation.guarantee.api_endpoint import execute_court_guarantee
        case = SimpleNamespace(id=1, name="", preservation_amount=None)
        with patch("plugins.court_automation.guarantee.api_endpoint._check_plugin", return_value=True), \
             patch("plugins.court_automation.guarantee.api_endpoint._get_organization_service") as MockOrg, \
             patch("apps.cases.models.Case") as MockCase:
            MockCase.objects.get.return_value = case
            MockOrg.return_value.get_credential_for_lawyer.return_value = None
            result = execute_court_guarantee(_make_request(), self._make_payload())
            assert result["success"] is False
            assert "凭证" in result["message"]

    def test_no_court_name(self):
        from plugins.court_automation.guarantee.api_endpoint import execute_court_guarantee
        case = SimpleNamespace(id=1, name="", preservation_amount=10000)
        with patch("plugins.court_automation.guarantee.api_endpoint._check_plugin", return_value=True), \
             patch("plugins.court_automation.guarantee.api_endpoint._get_organization_service") as MockOrg, \
             patch("plugins.court_automation.guarantee.api_endpoint._get_case_court_name", return_value=None), \
             patch("apps.cases.models.Case") as MockCase:
            MockCase.objects.get.return_value = case
            MockOrg.return_value.get_credential_for_lawyer.return_value = SimpleNamespace(account="u", password="p")
            result = execute_court_guarantee(_make_request(), self._make_payload())
            assert result["success"] is False
            assert "管辖法院" in result["message"]

    def test_no_preserve_amount(self):
        from plugins.court_automation.guarantee.api_endpoint import execute_court_guarantee
        case = SimpleNamespace(id=1, name="", preservation_amount=None)
        with patch("plugins.court_automation.guarantee.api_endpoint._check_plugin", return_value=True), \
             patch("plugins.court_automation.guarantee.api_endpoint._get_organization_service") as MockOrg, \
             patch("plugins.court_automation.guarantee.api_endpoint._get_case_court_name", return_value="天河区人民法院"), \
             patch("apps.cases.models.Case") as MockCase:
            MockCase.objects.get.return_value = case
            MockOrg.return_value.get_credential_for_lawyer.return_value = SimpleNamespace(account="u", password="p")
            result = execute_court_guarantee(_make_request(), self._make_payload())
            assert result["success"] is False
            assert "保全金额" in result["message"]


# ======================================================================
# ensure_case_quote / bind / retry / delete
# ======================================================================

class TestGuaranteeQuoteOperations:
    def test_ensure_no_preserve_amount(self):
        from plugins.court_automation.guarantee.api_endpoint import ensure_case_quote
        from decimal import Decimal
        case = SimpleNamespace(id=1, preservation_amount=None)
        with patch("apps.cases.models.Case") as MockCase, \
             patch("plugins.court_automation.guarantee.api_endpoint._parse_preserve_amount", return_value=None), \
             patch("plugins.court_automation.guarantee.api_endpoint._build_case_quote_context", return_value=None):
            MockCase.objects.get.return_value = case
            result = ensure_case_quote(_make_request(), SimpleNamespace(case_id=1))
            assert result["success"] is False
            assert "保全金额" in result["message"]

    def test_ensure_existing_binding(self):
        from plugins.court_automation.guarantee.api_endpoint import ensure_case_quote
        from decimal import Decimal
        case = SimpleNamespace(id=1, preservation_amount=Decimal("10000"))
        with patch("apps.cases.models.Case") as MockCase, \
             patch("plugins.court_automation.guarantee.api_endpoint._parse_preserve_amount", return_value=Decimal("10000")), \
             patch("plugins.court_automation.guarantee.api_endpoint._find_reusable_binding", return_value=SimpleNamespace(id=1)), \
             patch("plugins.court_automation.guarantee.api_endpoint._build_case_quote_context", return_value={"status": "ok"}):
            MockCase.objects.get.return_value = case
            result = ensure_case_quote(_make_request(), SimpleNamespace(case_id=1))
            assert result["success"] is True
            assert "复用" in result["message"]

    def test_ensure_no_credential(self):
        from plugins.court_automation.guarantee.api_endpoint import ensure_case_quote
        from decimal import Decimal
        case = SimpleNamespace(id=1, preservation_amount=Decimal("10000"))
        with patch("apps.cases.models.Case") as MockCase, \
             patch("plugins.court_automation.guarantee.api_endpoint._parse_preserve_amount", return_value=Decimal("10000")), \
             patch("plugins.court_automation.guarantee.api_endpoint._find_reusable_binding", return_value=None), \
             patch("plugins.court_automation.guarantee.api_endpoint._get_organization_service") as MockOrg, \
             patch("plugins.court_automation.guarantee.api_endpoint._build_case_quote_context", return_value=None):
            MockCase.objects.get.return_value = case
            MockOrg.return_value.get_credential_for_lawyer.return_value = None
            result = ensure_case_quote(_make_request(), SimpleNamespace(case_id=1))
            assert result["success"] is False
            assert "凭证" in result["message"]

    def test_bind_quote_not_found(self):
        from plugins.court_automation.guarantee.api_endpoint import bind_case_quote
        from decimal import Decimal
        case = SimpleNamespace(id=1, preservation_amount=Decimal("10000"))
        with patch("apps.cases.models.Case") as MockCase, \
             patch("plugins.court_automation.guarantee.api_endpoint._parse_preserve_amount", return_value=Decimal("10000")), \
             patch("apps.automation.models.PreservationQuote") as MockQuote, \
             patch("plugins.court_automation.guarantee.api_endpoint._build_case_quote_context", return_value=None):
            MockCase.objects.get.return_value = case
            MockQuote.objects.filter.return_value.first.return_value = None
            result = bind_case_quote(_make_request(), quote_id=1, payload=SimpleNamespace(case_id=1))
            assert result["success"] is False
            assert "不存在" in result["message"]

    def test_bind_amount_mismatch(self):
        from plugins.court_automation.guarantee.api_endpoint import bind_case_quote
        from decimal import Decimal
        case = SimpleNamespace(id=1, preservation_amount=Decimal("10000"))
        quote = SimpleNamespace(id=1, preserve_amount=Decimal("20000"))
        with patch("apps.cases.models.Case") as MockCase, \
             patch("plugins.court_automation.guarantee.api_endpoint._parse_preserve_amount", return_value=Decimal("10000")), \
             patch("apps.automation.models.PreservationQuote") as MockQuote, \
             patch("plugins.court_automation.guarantee.api_endpoint._build_case_quote_context", return_value=None):
            MockCase.objects.get.return_value = case
            MockQuote.objects.filter.return_value.first.return_value = quote
            result = bind_case_quote(_make_request(), quote_id=1, payload=SimpleNamespace(case_id=1))
            assert result["success"] is False
            assert "同保全金额" in result["message"]

    def test_retry_no_binding(self):
        from plugins.court_automation.guarantee.api_endpoint import retry_case_quote
        case = SimpleNamespace(id=1)
        with patch("apps.cases.models.Case") as MockCase, \
             patch("apps.automation.models.CasePreservationQuoteBinding") as MockBinding, \
             patch("plugins.court_automation.guarantee.api_endpoint._build_case_quote_context", return_value=None):
            MockCase.objects.get.return_value = case
            MockBinding.objects.select_related.return_value.filter.return_value.first.return_value = None
            result = retry_case_quote(_make_request(), quote_id=1, payload=SimpleNamespace(case_id=1))
            assert result["success"] is False

    def test_retry_quote_not_found(self):
        from plugins.court_automation.guarantee.api_endpoint import retry_case_quote
        case = SimpleNamespace(id=1)
        binding = SimpleNamespace(id=1)
        with patch("apps.cases.models.Case") as MockCase, \
             patch("apps.automation.models.CasePreservationQuoteBinding") as MockBinding, \
             patch("apps.automation.models.PreservationQuote") as MockQuote, \
             patch("plugins.court_automation.guarantee.api_endpoint._build_case_quote_context", return_value=None):
            MockCase.objects.get.return_value = case
            MockBinding.objects.select_related.return_value.filter.return_value.first.return_value = binding
            MockQuote.objects.filter.return_value.first.return_value = None
            result = retry_case_quote(_make_request(), quote_id=1, payload=SimpleNamespace(case_id=1))
            assert result["success"] is False

    def test_delete_binding_not_found(self):
        from plugins.court_automation.guarantee.api_endpoint import delete_case_quote_binding
        case = SimpleNamespace(id=1)
        with patch("apps.cases.models.Case") as MockCase, \
             patch("apps.automation.models.CasePreservationQuoteBinding") as MockBinding, \
             patch("plugins.court_automation.guarantee.api_endpoint._build_case_quote_context", return_value=None):
            MockCase.objects.get.return_value = case
            MockBinding.objects.filter.return_value.first.return_value = None
            result = delete_case_quote_binding(_make_request(), binding_id=1, payload=SimpleNamespace(case_id=1))
            assert result["success"] is False
            assert "不存在" in result["message"]

    def test_delete_quote_not_found(self):
        from plugins.court_automation.guarantee.api_endpoint import delete_case_quote
        case = SimpleNamespace(id=1)
        with patch("apps.cases.models.Case") as MockCase, \
             patch("apps.automation.models.CasePreservationQuoteBinding") as MockBinding, \
             patch("apps.automation.models.PreservationQuote") as MockQuote, \
             patch("plugins.court_automation.guarantee.api_endpoint._build_case_quote_context", return_value=None):
            MockCase.objects.get.return_value = case
            MockBinding.objects.filter.return_value.exists.return_value = False
            result = delete_case_quote(_make_request(), quote_id=1, payload=SimpleNamespace(case_id=1))
            assert result["success"] is False
