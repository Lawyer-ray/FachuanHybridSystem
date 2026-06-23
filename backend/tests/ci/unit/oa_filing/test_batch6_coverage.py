"""Batch 6 coverage tests for oa_filing module."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class TestOAFilingExceptions:
    def test_oa_filing_error_default(self):
        from apps.oa_filing.services.exceptions import OAFilingError

        err = OAFilingError()
        assert err.message == ""
        assert str(err) == ""

    def test_oa_filing_error_with_message(self):
        from apps.oa_filing.services.exceptions import OAFilingError

        err = OAFilingError("something went wrong")
        assert err.message == "something went wrong"
        assert str(err) == "something went wrong"

    def test_script_execution_error_default(self):
        from apps.oa_filing.services.exceptions import ScriptExecutionError

        err = ScriptExecutionError()
        assert err.message == "脚本执行失败"

    def test_script_execution_error_custom_message(self):
        from apps.oa_filing.services.exceptions import ScriptExecutionError

        err = ScriptExecutionError("custom error")
        assert err.message == "custom error"

    def test_script_execution_error_is_oa_filing_error(self):
        from apps.oa_filing.services.exceptions import (
            OAFilingError,
            ScriptExecutionError,
        )

        assert issubclass(ScriptExecutionError, OAFilingError)


class TestScriptExecutorServiceMapping:
    def _make_service(self):
        from apps.oa_filing.services.script_executor_service import (
            ScriptExecutorService,
        )

        return ScriptExecutorService()

    def test_map_case_category_civil(self):
        svc = self._make_service()
        case = SimpleNamespace(case_type="civil")
        assert svc._map_case_category(case) == "03"

    def test_map_case_category_criminal(self):
        svc = self._make_service()
        case = SimpleNamespace(case_type="criminal")
        assert svc._map_case_category(case) == "05"

    def test_map_case_category_administrative(self):
        svc = self._make_service()
        case = SimpleNamespace(case_type="administrative")
        assert svc._map_case_category(case) == "04"

    def test_map_case_category_labor(self):
        svc = self._make_service()
        case = SimpleNamespace(case_type="labor")
        assert svc._map_case_category(case) == "03"

    def test_map_case_category_intl(self):
        svc = self._make_service()
        case = SimpleNamespace(case_type="intl")
        assert svc._map_case_category(case) == "06"

    def test_map_case_category_advisor(self):
        svc = self._make_service()
        case = SimpleNamespace(case_type="advisor")
        assert svc._map_case_category(case) == "01"

    def test_map_case_category_special(self):
        svc = self._make_service()
        case = SimpleNamespace(case_type="special")
        assert svc._map_case_category(case) == "02"

    def test_map_case_category_unknown(self):
        svc = self._make_service()
        case = SimpleNamespace(case_type="unknown")
        assert svc._map_case_category(case) == "03"

    def test_map_case_stage_advisor(self):
        svc = self._make_service()
        case = SimpleNamespace(case_type="advisor", current_stage="first_trial")
        assert svc._map_case_stage(case) == ""

    def test_map_case_stage_civil_first_trial(self):
        svc = self._make_service()
        case = SimpleNamespace(case_type="civil", current_stage="first_trial")
        assert svc._map_case_stage(case) == "0301"

    def test_map_case_stage_civil_second_trial(self):
        svc = self._make_service()
        case = SimpleNamespace(case_type="civil", current_stage="second_trial")
        assert svc._map_case_stage(case) == "0305"

    def test_map_case_stage_civil_enforcement(self):
        svc = self._make_service()
        case = SimpleNamespace(case_type="civil", current_stage="enforcement")
        assert svc._map_case_stage(case) == "0314"

    def test_map_case_stage_admin_review(self):
        svc = self._make_service()
        case = SimpleNamespace(
            case_type="administrative", current_stage="administrative_review"
        )
        assert svc._map_case_stage(case) == "0401"

    def test_map_case_stage_criminal_first_trial(self):
        svc = self._make_service()
        case = SimpleNamespace(case_type="criminal", current_stage="first_trial")
        assert svc._map_case_stage(case) == "0503"

    def test_map_case_stage_unknown_stage_civil(self):
        svc = self._make_service()
        case = SimpleNamespace(case_type="civil", current_stage="unknown_stage")
        assert svc._map_case_stage(case) == "0301"

    def test_map_fee_mode_fixed(self):
        svc = self._make_service()
        contract = SimpleNamespace(fee_mode="FIXED")
        assert svc._map_fee_mode(contract) == "01"

    def test_map_fee_mode_semi_risk(self):
        svc = self._make_service()
        contract = SimpleNamespace(fee_mode="SEMI_RISK")
        assert svc._map_fee_mode(contract) == "02"

    def test_map_fee_mode_full_risk(self):
        svc = self._make_service()
        contract = SimpleNamespace(fee_mode="FULL_RISK")
        assert svc._map_fee_mode(contract) == "02"

    def test_fee_mode_unknown(self):
        svc = self._make_service()
        contract = SimpleNamespace(fee_mode="UNKNOWN")
        assert svc._map_fee_mode(contract) == "01"

    def test_map_kindtype_litigation(self):
        svc = self._make_service()
        kind, kind2 = svc._map_kindtype("03", [])
        assert kind == ""
        assert kind2 == ""

    def test_map_kindtype_advisor_natural(self):
        svc = self._make_service()
        party = SimpleNamespace(client=SimpleNamespace(client_type="natural"))
        kind, kind2 = svc._map_kindtype("01", [party])
        assert kind == "KindType01_05"

    def test_map_kindtype_advisor_legal(self):
        svc = self._make_service()
        party = SimpleNamespace(client=SimpleNamespace(client_type="legal"))
        kind, kind2 = svc._map_kindtype("01", [party])
        assert kind == "KindType01_01"
        assert kind2 == "KindType01_0103"

    def test_map_kindtype_special_natural(self):
        svc = self._make_service()
        party = SimpleNamespace(client=SimpleNamespace(client_type="natural"))
        kind, kind2 = svc._map_kindtype("02", [party])
        assert kind == "KindType02_05"

    def test_map_kindtype_special_legal(self):
        svc = self._make_service()
        party = SimpleNamespace(client=SimpleNamespace(client_type="legal"))
        kind, kind2 = svc._map_kindtype("02", [party])
        assert kind == "KindType02_01"

    @pytest.mark.asyncio
    async def test_dispatch_unsupported_site(self):
        svc = self._make_service()
        with pytest.raises(Exception, match="不支持"):
            await svc._dispatch("未知站点", None, 1, None)

    def test_script_executor_supported_sites(self):
        from apps.oa_filing.services.script_executor_service import SUPPORTED_SITES

        assert "金诚同达OA" in SUPPORTED_SITES
