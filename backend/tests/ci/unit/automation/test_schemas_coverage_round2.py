"""Tests for court_filing_schemas and court_guarantee_schemas uncovered branches."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

try:
    from plugins.court_automation import filing
except ImportError:
    pytest.skip("court_automation plugin not installed", allow_module_level=True)



class TestReadIntEnv:
    """Cover _read_int_env in court_guarantee_schemas."""

    def _fn(self):
        from plugins.court_automation.guarantee.schemas import _read_int_env
        return _read_int_env

    def test_valid_env(self):
        with patch.dict(os.environ, {"TEST_INT": "42"}):
            result = self._fn()("TEST_INT", 8)
        assert result == 42

    def test_invalid_env_returns_default(self):
        with patch.dict(os.environ, {"TEST_INT": "not_a_number"}):
            result = self._fn()("TEST_INT", 8)
        assert result == 8

    def test_negative_returns_default(self):
        with patch.dict(os.environ, {"TEST_INT": "-5"}):
            result = self._fn()("TEST_INT", 8)
        assert result == 8

    def test_missing_env_returns_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TEST_MISSING_INT", None)
            result = self._fn()("TEST_MISSING_INT", 10)
        assert result == 10

    def test_zero_is_valid(self):
        with patch.dict(os.environ, {"TEST_INT": "0"}):
            result = self._fn()("TEST_INT", 8)
        assert result == 0


class TestCourtFilingSchemas:
    """Cover schema instantiation in court_filing_schemas."""

    def test_case_filing_info_out(self):
        from plugins.court_automation.filing.schemas import CaseFilingInfoOut
        obj = CaseFilingInfoOut(
            case_id=1,
            case_name="测试案件",
            cause_of_action="借款纠纷",
            court_name="天河区人民法院",
            target_amount="100000",
            plaintiff_name="原告",
            defendant_name="被告",
        )
        assert obj.case_id == 1
        assert obj.our_party_is_plaintiff_side is False

    def test_execute_court_filing_in(self):
        from plugins.court_automation.filing.schemas import ExecuteCourtFilingIn
        obj = ExecuteCourtFilingIn(case_id=1, filing_type="civil", filing_engine="api")
        assert obj.case_id == 1

    def test_execute_court_filing_out(self):
        from plugins.court_automation.filing.schemas import ExecuteCourtFilingOut
        obj = ExecuteCourtFilingOut(success=True, message="ok")
        assert obj.success is True
        assert obj.session_id is None


class TestCourtGuaranteeSchemas:
    """Cover schema instantiation in court_guarantee_schemas."""

    def test_case_guarantee_info_out(self):
        from plugins.court_automation.guarantee.schemas import CaseGuaranteeInfoOut
        obj = CaseGuaranteeInfoOut(
            case_id=1,
            case_name="测试",
            court_name="法院",
            cause_of_action="借款纠纷",
            preserve_amount="100000",
            preserve_category="其他",
            has_case_number=True,
        )
        assert obj.case_id == 1
        assert obj.insurance_company_name == "中国平安财产保险股份有限公司"

    def test_case_quote_operation_in(self):
        from plugins.court_automation.guarantee.schemas import CaseQuoteOperationIn
        obj = CaseQuoteOperationIn(case_id=1)
        assert obj.case_id == 1

    def test_case_quote_operation_out(self):
        from plugins.court_automation.guarantee.schemas import CaseQuoteOperationOut
        obj = CaseQuoteOperationOut(success=True, message="ok")
        assert obj.success is True

    def test_execute_court_guarantee_in(self):
        from plugins.court_automation.guarantee.schemas import ExecuteCourtGuaranteeIn
        obj = ExecuteCourtGuaranteeIn(
            case_id=1,
            insurance_company_name="平安",
            consultant_code="123",
            selected_respondent_ids=[1, 2],
        )
        assert obj.case_id == 1

    def test_execute_court_guarantee_out(self):
        from plugins.court_automation.guarantee.schemas import ExecuteCourtGuaranteeOut
        obj = ExecuteCourtGuaranteeOut(success=True, message="ok")
        assert obj.session_id is None
