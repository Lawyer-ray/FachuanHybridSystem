"""Unit tests for ScriptExecutorService — mapping methods."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.oa_filing.services.script_executor_service import (
    SUPPORTED_SITES,
    ScriptExecutorService,
)


@pytest.fixture
def svc():
    return ScriptExecutorService()


# ──────────── _map_case_category ────────────


class TestMapCaseCategory:
    def test_civil(self, svc):
        case = MagicMock(case_type="civil")
        assert svc._map_case_category(case) == "03"

    def test_criminal(self, svc):
        case = MagicMock(case_type="criminal")
        assert svc._map_case_category(case) == "05"

    def test_administrative(self, svc):
        case = MagicMock(case_type="administrative")
        assert svc._map_case_category(case) == "04"

    def test_labor(self, svc):
        case = MagicMock(case_type="labor")
        assert svc._map_case_category(case) == "03"

    def test_intl(self, svc):
        case = MagicMock(case_type="intl")
        assert svc._map_case_category(case) == "06"

    def test_execution(self, svc):
        case = MagicMock(case_type="execution")
        assert svc._map_case_category(case) == "03"

    def test_bankruptcy(self, svc):
        case = MagicMock(case_type="bankruptcy")
        assert svc._map_case_category(case) == "03"

    def test_special(self, svc):
        case = MagicMock(case_type="special")
        assert svc._map_case_category(case) == "02"

    def test_advisor(self, svc):
        case = MagicMock(case_type="advisor")
        assert svc._map_case_category(case) == "01"

    def test_unknown_defaults_to_civil(self, svc):
        case = MagicMock(case_type="unknown_type")
        assert svc._map_case_category(case) == "03"

    def test_none_defaults_to_civil(self, svc):
        case = MagicMock(case_type=None)
        assert svc._map_case_category(case) == "03"


# ──────────── _map_case_stage ────────────


class TestMapCaseStage:
    def test_civil_first_trial(self, svc):
        case = MagicMock(case_type="civil", current_stage="first_trial")
        assert svc._map_case_stage(case) == "0301"

    def test_civil_second_trial(self, svc):
        case = MagicMock(case_type="civil", current_stage="second_trial")
        assert svc._map_case_stage(case) == "0305"

    def test_civil_enforcement(self, svc):
        case = MagicMock(case_type="civil", current_stage="enforcement")
        assert svc._map_case_stage(case) == "0314"

    def test_administrative_review(self, svc):
        case = MagicMock(case_type="administrative", current_stage="administrative_review")
        assert svc._map_case_stage(case) == "0401"

    def test_administrative_first_trial(self, svc):
        case = MagicMock(case_type="administrative", current_stage="first_trial")
        assert svc._map_case_stage(case) == "0402"

    def test_criminal_investigation(self, svc):
        case = MagicMock(case_type="criminal", current_stage="investigation")
        assert svc._map_case_stage(case) == "0501"

    def test_criminal_first_trial(self, svc):
        case = MagicMock(case_type="criminal", current_stage="first_trial")
        assert svc._map_case_stage(case) == "0503"

    def test_advisor_no_stage(self, svc):
        case = MagicMock(case_type="advisor", current_stage="first_trial")
        assert svc._map_case_stage(case) == ""

    def test_special_no_stage(self, svc):
        case = MagicMock(case_type="special", current_stage="first_trial")
        assert svc._map_case_stage(case) == ""

    def test_unknown_stage_defaults_civil(self, svc):
        case = MagicMock(case_type="civil", current_stage="unknown_stage")
        assert svc._map_case_stage(case) == "0301"

    def test_none_stage_defaults_civil(self, svc):
        case = MagicMock(case_type="civil", current_stage=None)
        assert svc._map_case_stage(case) == "0301"


# ──────────── _map_fee_mode ────────────


class TestMapFeeMode:
    def test_fixed(self, svc):
        contract = MagicMock(fee_mode="FIXED")
        assert svc._map_fee_mode(contract) == "01"

    def test_semi_risk(self, svc):
        contract = MagicMock(fee_mode="SEMI_RISK")
        assert svc._map_fee_mode(contract) == "02"

    def test_full_risk(self, svc):
        contract = MagicMock(fee_mode="FULL_RISK")
        assert svc._map_fee_mode(contract) == "02"

    def test_custom(self, svc):
        contract = MagicMock(fee_mode="CUSTOM")
        assert svc._map_fee_mode(contract) == "01"

    def test_unknown_defaults(self, svc):
        contract = MagicMock(fee_mode="UNKNOWN")
        assert svc._map_fee_mode(contract) == "01"

    def test_none_defaults(self, svc):
        contract = MagicMock(fee_mode=None)
        assert svc._map_fee_mode(contract) == "01"


# ──────────── _map_kindtype ────────────


class TestMapKindtype:
    def test_non_litigation_returns_empty(self, svc):
        kind, kind_sed = svc._map_kindtype("03", [])
        assert kind == ""
        assert kind_sed == ""

    def test_advisor_enterprise(self, svc):
        party = MagicMock()
        party.client = MagicMock(client_type="legal")
        kind, kind_sed = svc._map_kindtype("01", [party])
        assert kind == "KindType01_01"
        assert kind_sed == "KindType01_0103"

    def test_advisor_natural_person(self, svc):
        party = MagicMock()
        party.client = MagicMock(client_type="natural")
        kind, kind_sed = svc._map_kindtype("01", [party])
        assert kind == "KindType01_05"
        assert kind_sed == ""

    def test_special_enterprise(self, svc):
        party = MagicMock()
        party.client = MagicMock(client_type="legal")
        kind, kind_sed = svc._map_kindtype("02", [party])
        assert kind == "KindType02_01"
        assert kind_sed == ""

    def test_special_natural_person(self, svc):
        party = MagicMock()
        party.client = MagicMock(client_type="natural")
        kind, kind_sed = svc._map_kindtype("02", [party])
        assert kind == "KindType02_05"
        assert kind_sed == ""

    def test_no_parties_enterprise(self, svc):
        kind, kind_sed = svc._map_kindtype("01", [])
        # No parties → has_natural = False → enterprise path
        assert kind == "KindType01_01"
        assert kind_sed == "KindType01_0103"


# ──────────── _dispatch ────────────


class TestDispatch:
    def test_unsupported_site_raises(self, svc):
        from apps.oa_filing.services.exceptions import ScriptExecutionError
        with pytest.raises(ScriptExecutionError, match="不支持"):
            svc._dispatch("unsupported_site", MagicMock(), 1, None)

    @patch.object(ScriptExecutorService, "_run_jtn")
    def test_jtn_dispatches(self, mock_run):
        svc = ScriptExecutorService()
        svc._dispatch("金诚同达OA", MagicMock(), 1, None)
        mock_run.assert_called_once()


# ──────────── Module constants ────────────


class TestModuleConstants:
    def test_supported_sites(self):
        assert "金诚同达OA" in SUPPORTED_SITES
        assert len(SUPPORTED_SITES) >= 1
