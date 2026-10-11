"""Unit tests for JTNAdapter mapping methods and oa_firm_registry."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.oa_filing.services.oa_firm_registry import SUPPORTED_SITES, create_adapter, get_adapter_class
from apps.oa_filing.services.oa_scripts.jtn.adapter import JTNAdapter


@pytest.fixture
def adapter():
    return JTNAdapter("test_account", "fake_secret")  # pragma: allowlist secret


# ──────────── _map_case_category ────────────


class TestMapCaseCategory:
    def test_civil(self, adapter):
        case = MagicMock(case_type="civil")
        assert adapter._map_case_category(case) == "03"

    def test_criminal(self, adapter):
        case = MagicMock(case_type="criminal")
        assert adapter._map_case_category(case) == "05"

    def test_administrative(self, adapter):
        case = MagicMock(case_type="administrative")
        assert adapter._map_case_category(case) == "04"

    def test_labor(self, adapter):
        case = MagicMock(case_type="labor")
        assert adapter._map_case_category(case) == "03"

    def test_intl(self, adapter):
        case = MagicMock(case_type="intl")
        assert adapter._map_case_category(case) == "06"

    def test_execution(self, adapter):
        case = MagicMock(case_type="execution")
        assert adapter._map_case_category(case) == "03"

    def test_bankruptcy(self, adapter):
        case = MagicMock(case_type="bankruptcy")
        assert adapter._map_case_category(case) == "03"

    def test_special(self, adapter):
        case = MagicMock(case_type="special")
        assert adapter._map_case_category(case) == "02"

    def test_advisor(self, adapter):
        case = MagicMock(case_type="advisor")
        assert adapter._map_case_category(case) == "01"

    def test_unknown_defaults_to_civil(self, adapter):
        case = MagicMock(case_type="unknown_type")
        assert adapter._map_case_category(case) == "03"

    def test_none_defaults_to_civil(self, adapter):
        case = MagicMock(case_type=None)
        assert adapter._map_case_category(case) == "03"


# ──────────── _map_case_stage ────────────


class TestMapCaseStage:
    def test_civil_first_trial(self, adapter):
        case = MagicMock(case_type="civil", current_stage="first_trial")
        assert adapter._map_case_stage(case) == "0301"

    def test_civil_second_trial(self, adapter):
        case = MagicMock(case_type="civil", current_stage="second_trial")
        assert adapter._map_case_stage(case) == "0305"

    def test_civil_enforcement(self, adapter):
        case = MagicMock(case_type="civil", current_stage="enforcement")
        assert adapter._map_case_stage(case) == "0314"

    def test_administrative_review(self, adapter):
        case = MagicMock(case_type="administrative", current_stage="administrative_review")
        assert adapter._map_case_stage(case) == "0401"

    def test_administrative_first_trial(self, adapter):
        case = MagicMock(case_type="administrative", current_stage="first_trial")
        assert adapter._map_case_stage(case) == "0402"

    def test_criminal_investigation(self, adapter):
        case = MagicMock(case_type="criminal", current_stage="investigation")
        assert adapter._map_case_stage(case) == "0501"

    def test_criminal_first_trial(self, adapter):
        case = MagicMock(case_type="criminal", current_stage="first_trial")
        assert adapter._map_case_stage(case) == "0503"

    def test_advisor_no_stage(self, adapter):
        case = MagicMock(case_type="advisor", current_stage="first_trial")
        assert adapter._map_case_stage(case) == ""

    def test_special_no_stage(self, adapter):
        case = MagicMock(case_type="special", current_stage="first_trial")
        assert adapter._map_case_stage(case) == ""

    def test_unknown_stage_defaults_civil(self, adapter):
        case = MagicMock(case_type="civil", current_stage="unknown_stage")
        assert adapter._map_case_stage(case) == "0301"

    def test_none_stage_defaults_civil(self, adapter):
        case = MagicMock(case_type="civil", current_stage=None)
        assert adapter._map_case_stage(case) == "0301"


# ──────────── _map_fee_mode ────────────


class TestMapFeeMode:
    def test_fixed(self, adapter):
        contract = MagicMock(fee_mode="FIXED")
        assert adapter._map_fee_mode(contract) == "01"

    def test_semi_risk(self, adapter):
        contract = MagicMock(fee_mode="SEMI_RISK")
        assert adapter._map_fee_mode(contract) == "02"

    def test_full_risk(self, adapter):
        contract = MagicMock(fee_mode="FULL_RISK")
        assert adapter._map_fee_mode(contract) == "02"

    def test_custom(self, adapter):
        contract = MagicMock(fee_mode="CUSTOM")
        assert adapter._map_fee_mode(contract) == "01"

    def test_unknown_defaults(self, adapter):
        contract = MagicMock(fee_mode="UNKNOWN")
        assert adapter._map_fee_mode(contract) == "01"

    def test_none_defaults(self, adapter):
        contract = MagicMock(fee_mode=None)
        assert adapter._map_fee_mode(contract) == "01"


# ──────────── _map_kindtype ────────────


class TestMapKindtype:
    def test_non_litigation_returns_empty(self, adapter):
        kind, kind_sed = adapter._map_kindtype("03", [])
        assert kind == ""
        assert kind_sed == ""

    def test_advisor_enterprise(self, adapter):
        party = MagicMock()
        party.client = MagicMock(client_type="legal")
        kind, kind_sed = adapter._map_kindtype("01", [party])
        assert kind == "KindType01_01"
        assert kind_sed == "KindType01_0103"

    def test_advisor_natural_person(self, adapter):
        party = MagicMock()
        party.client = MagicMock(client_type="natural")
        kind, kind_sed = adapter._map_kindtype("01", [party])
        assert kind == "KindType01_05"
        assert kind_sed == ""

    def test_special_enterprise(self, adapter):
        party = MagicMock()
        party.client = MagicMock(client_type="legal")
        kind, kind_sed = adapter._map_kindtype("02", [party])
        assert kind == "KindType02_01"
        assert kind_sed == ""

    def test_civil_with_contract_cause(self, adapter):
        # 373 真实形态：案由「买卖合同纠纷」→ 合同类
        kind, kind_sed = adapter._map_kindtype("03", [], cause_text="买卖合同纠纷")
        assert kind == "KindType03_04"
        assert kind_sed == ""

    def test_civil_specific_beats_generic(self, adapter):
        # 股权类须赢过泛化的"合同"（股权转让合同纠纷 → 公司类）
        kind, _ = adapter._map_kindtype("03", [], cause_text="股权转让合同纠纷")
        assert kind == "KindType03_08"
        # 劳动须赢过"合同"（劳动合同纠纷 → 劳动类）
        kind, _ = adapter._map_kindtype("03", [], cause_text="劳动合同纠纷")
        assert kind == "KindType03_06"

    def test_civil_other_causes(self, adapter):
        assert adapter._map_kindtype("03", [], cause_text="离婚后财产纠纷")[0] == "KindType03_02"
        assert adapter._map_kindtype("03", [], cause_text="机动车交通事故责任纠纷")[0] == "KindType03_09"
        assert adapter._map_kindtype("03", [], cause_text="侵害商标权纠纷")[0] == "KindType03_05"
        assert adapter._map_kindtype("03", [], cause_text="所有权确认纠纷")[0] == "KindType03_03"

    def test_civil_unmatched_cause_returns_empty(self, adapter):
        kind, kind_sed = adapter._map_kindtype("03", [], cause_text="申请宣告失踪案")
        assert kind == "" and kind_sed == ""


# ──────────── _map_case_stage：劳动仲裁 ────────────


class TestMapCaseStageLaborArbitration:
    def test_labor_arbitration_maps_to_0304(self, adapter):
        # 372 真实形态：劳动仲裁此前不在映射表，被默认成 0301 一审
        case = MagicMock(case_type="civil", current_stage="labor_arbitration")
        assert adapter._map_case_stage(case) == "0304"


# ──────────── _map_which_side_value：按阶段映射 ────────────


class TestMapWhichSideValue:
    def test_labor_arbitration_respondent(self, adapter):
        # 372 真实形态：被申请人在仲裁阶段 → 06，不再默认 01 原告
        assert adapter._map_which_side_value("respondent", "0304") == "06"

    def test_enforcement_defendant(self, adapter):
        assert adapter._map_which_side_value("defendant", "0314") == "06"

    def test_enforcement_plaintiff_cross_to_applicant(self, adapter):
        assert adapter._map_which_side_value("plaintiff", "0314") == "05"

    def test_first_trial_respondent_cross_to_defendant(self, adapter):
        assert adapter._map_which_side_value("respondent", "0301") == "02"

    def test_second_trial_appellant(self, adapter):
        assert adapter._map_which_side_value("appellant", "0305") == "03"

    def test_appellant_at_special_stage_cross_to_applicant(self, adapter):
        assert adapter._map_which_side_value("appellant", "0304") == "05"

    def test_orig_defendant_second_trial(self, adapter):
        assert adapter._map_which_side_value("orig_defendant", "0305") == "22"

    def test_third(self, adapter):
        assert adapter._map_which_side_value("third", "0301") == "09"

    def test_unknown_status_falls_back(self, adapter):
        assert adapter._map_which_side_value("whatever", "0301") == "01"
        assert adapter._map_which_side_value("", "0304") == "05"  # 05 排序最前

    def test_unknown_stage_defaults_01(self, adapter):
        assert adapter._map_which_side_value("defendant", "") == "01"


# ──────────── _resolve_kindtype_sed：子类匹配 ────────────


class TestResolveKindtypeSed:
    @pytest.mark.asyncio
    async def test_matches_by_name_core(self, adapter, monkeypatch):
        options = [
            {"id": "KindType03_0601", "sc_name": "劳动争议"},
            {"id": "KindType03_0602", "sc_name": "人事争议"},
        ]

        async def fake_fetch(kindtype: str):
            return options

        monkeypatch.setattr(adapter, "_fetch_kindtype_sed_options", fake_fetch)
        sed = await adapter._resolve_kindtype_sed(kindtype="KindType03_06", cause_text="劳动争议")
        assert sed == "KindType03_0601"

    @pytest.mark.asyncio
    async def test_single_option_adopted_directly(self, adapter, monkeypatch):
        async def fake_fetch(kindtype: str):
            return [{"id": "KindType02_0101", "sc_name": "常年法律顾问"}]

        monkeypatch.setattr(adapter, "_fetch_kindtype_sed_options", fake_fetch)
        sed = await adapter._resolve_kindtype_sed(kindtype="KindType02_01", cause_text="随便什么")
        assert sed == "KindType02_0101"

    @pytest.mark.asyncio
    async def test_unmatched_multi_option_returns_empty(self, adapter, monkeypatch):
        async def fake_fetch(kindtype: str):
            return [
                {"id": "KindType03_0401", "sc_name": "合同纠纷"},
                {"id": "KindType03_0402", "sc_name": "不当得利纠纷"},
                {"id": "KindType03_0403", "sc_name": "无因管理纠纷"},
            ]

        monkeypatch.setattr(adapter, "_fetch_kindtype_sed_options", fake_fetch)
        sed = await adapter._resolve_kindtype_sed(kindtype="KindType03_04", cause_text="申请宣告失踪案")
        assert sed == ""

    @pytest.mark.asyncio
    async def test_empty_kindtype_returns_empty(self, adapter):
        assert await adapter._resolve_kindtype_sed(kindtype="", cause_text="合同") == ""

    @pytest.mark.asyncio
    async def test_fetch_failure_returns_empty(self, adapter, monkeypatch):
        async def fake_fetch(kindtype: str):
            return []

        monkeypatch.setattr(adapter, "_fetch_kindtype_sed_options", fake_fetch)
        assert await adapter._resolve_kindtype_sed(kindtype="KindType03_04", cause_text="合同纠纷") == ""


# ──────────── _map_case_contact ────────────


class TestMapCaseContact:
    def _client(self, **kwargs):
        info = MagicMock()
        for key, value in kwargs.items():
            setattr(info, key, value)
        return info

    def test_enterprise_uses_legal_representative(self, adapter):
        client = self._client(client_type="legal", name="某公司", legal_representative="张三", phone="010-123")
        assert adapter._map_case_contact([client]) == ("张三", "010-123")

    def test_natural_uses_self(self, adapter):
        client = self._client(client_type="natural", name="李四", legal_representative="", phone="13800000000")
        assert adapter._map_case_contact([client]) == ("李四", "13800000000")

    def test_enterprise_without_legal_rep_falls_back_to_name(self, adapter):
        client = self._client(client_type="legal", name="某公司", legal_representative="", phone="")
        assert adapter._map_case_contact([client]) == ("某公司", "/")

    def test_empty_clients_returns_slash(self, adapter):
        assert adapter._map_case_contact([]) == ("/", "/")

    def test_special_natural_person(self, adapter):
        party = MagicMock()
        party.client = MagicMock(client_type="natural")
        kind, kind_sed = adapter._map_kindtype("02", [party])
        assert kind == "KindType02_05"
        assert kind_sed == ""

    def test_no_parties_enterprise(self, adapter):
        kind, kind_sed = adapter._map_kindtype("01", [])
        assert kind == "KindType01_01"
        assert kind_sed == "KindType01_0103"


# ──────────── oa_firm_registry ────────────


class TestFirmRegistry:
    def test_supported_sites(self):
        assert "金诚同达OA" in SUPPORTED_SITES
        assert len(SUPPORTED_SITES) >= 1

    def test_get_adapter_class(self):
        cls = get_adapter_class("金诚同达OA")
        assert cls is JTNAdapter

    def test_get_adapter_class_unsupported(self):
        with pytest.raises(ValueError, match="不支持"):
            get_adapter_class("不存在的律所")

    def test_create_adapter(self):
        adapter = create_adapter("金诚同达OA", "test_acc", "fake_secret")  # pragma: allowlist secret
        assert isinstance(adapter, JTNAdapter)
        assert adapter._account == "test_acc"
        assert adapter._password == "fake_secret"  # pragma: allowlist secret

    def test_create_adapter_unsupported(self):
        with pytest.raises(ValueError, match="不支持"):
            create_adapter("不存在的律所", "test_acc", "fake_secret")  # pragma: allowlist secret
