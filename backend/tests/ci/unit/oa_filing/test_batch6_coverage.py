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
        from apps.oa_filing.services.exceptions import OAFilingError, ScriptExecutionError

        assert issubclass(ScriptExecutionError, OAFilingError)


class TestJTNAdapterMapping:
    def _make_service(self):
        from apps.oa_filing.services.oa_scripts.jtn.adapter import JTNAdapter

        return JTNAdapter("test", "test")

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
        case = SimpleNamespace(case_type="administrative", current_stage="administrative_review")
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
        # 业务种类是 OA 必填项，案由缺失时兜底合同类，不再留空
        kind, kind2 = svc._map_kindtype("03", [])
        assert kind == "KindType03_04"
        assert kind2 == ""

    def test_map_kindtype_execution_objection(self):
        """执行异议之诉属「适用特殊程序」，不得被泛化词吞掉或留空（合同 386 回归）。"""
        svc = self._make_service()
        kind, kind2 = svc._map_kindtype("03", [], cause_text="执行异议之诉")
        assert kind == "KindType03_10"
        assert kind2 == ""

    def test_map_kindtype_third_party_revocation(self):
        svc = self._make_service()
        kind, _ = svc._map_kindtype("03", [], cause_text="第三人撤销之诉")
        assert kind == "KindType03_10"

    def test_map_kindtype_contract_still_wins_for_civil(self):
        """普通民事案由仍按原关键词映射，不受特殊程序规则影响。"""
        svc = self._make_service()
        kind, _ = svc._map_kindtype("03", [], cause_text="买卖合同纠纷")
        assert kind == "KindType03_04"
        kind, _ = svc._map_kindtype("03", [], cause_text="劳动争议")
        assert kind == "KindType03_06"

    def test_map_kindtype_fallback_when_no_keyword(self):
        svc = self._make_service()
        kind, _ = svc._map_kindtype("03", [], cause_text="某完全不匹配的案由XYZ")
        assert kind == "KindType03_04"

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

    def test_http_client_payload_emits_contact_fields(self):
        """客户本案联系人必须写入 pro_pl_*（合同 386 回归：旧代码永远匹配不到）。

        OA 页的 pro_pl_* 只存在于 layui 模板，服务端抓取的 payload 里没有这些键，
        旧代码的 `for field_name in payload` 循环一条也无法命中。
        """
        from apps.oa_filing.services.oa_scripts.jtn.filing.filing_models import CaseInfo, ResolvedCustomer
        from apps.oa_filing.services.oa_scripts.jtn.filing.http_filing import HttpFilingMixin

        svc = HttpFilingMixin()
        payload: dict[str, str] = {}
        svc._apply_client_payload(
            payload=payload,
            customers=[ResolvedCustomer(customer_id="123", customer_name="某甲方公司")],
        )

        pl_name_keys = [k for k in payload if "pro_pl_name" in k]
        pl_phone_keys = [k for k in payload if "pro_pl_phone" in k]
        assert len(pl_name_keys) == 1, "必须为客户行生成 pro_pl_name_<gid>"
        assert len(pl_phone_keys) == 1, "必须为客户行生成 pro_pl_phone_<gid>"

        case_info = CaseInfo(
            manager_id="",
            manager_name="",
            category="03",
            stage="0301",
            which_side="02",
            kindtype="KindType03_10",
            kindtype_sed="KindType03_1013",
            kindtype_thr="",
            case_name="测试案件",
            contact_name="张三",
            contact_phone="/",
        )
        form_state = MagicMock(html_text="<html></html>")
        svc._apply_case_info_payload(payload=payload, case_info=case_info, form_state=form_state)

        assert payload[pl_name_keys[0]] == "张三"
        assert payload[pl_phone_keys[0]] == "/"

    def test_http_client_payload_contact_defaults_to_slash(self):
        """联系人缺失时必须填 "/"，因为 OA 侧是必填项。"""
        from apps.oa_filing.services.oa_scripts.jtn.filing.filing_models import CaseInfo, ResolvedCustomer
        from apps.oa_filing.services.oa_scripts.jtn.filing.http_filing import HttpFilingMixin

        svc = HttpFilingMixin()
        payload: dict[str, str] = {}
        svc._apply_client_payload(
            payload=payload,
            customers=[ResolvedCustomer(customer_id="123", customer_name="某公司")],
        )
        case_info = CaseInfo(
            manager_id="",
            manager_name="",
            category="03",
            stage="0301",
            which_side="02",
            kindtype="KindType03_04",
            kindtype_sed="",
            kindtype_thr="",
            case_name="测试案件",
            contact_name="",
            contact_phone="",
        )
        svc._apply_case_info_payload(payload=payload, case_info=case_info, form_state=MagicMock(html_text=""))

        assert all(v == "/" for k, v in payload.items() if "pro_pl_name" in k)
        assert all(v == "/" for k, v in payload.items() if "pro_pl_phone" in k)

    @pytest.mark.asyncio
    async def test_dispatch_unsupported_site(self):
        from apps.oa_filing.services.oa_firm_registry import create_adapter

        with pytest.raises(ValueError, match="不支持"):
            create_adapter("未知站点", "acc", "pwd")

    def test_script_executor_supported_sites(self):
        from apps.oa_filing.services.oa_firm_registry import SUPPORTED_SITES

        assert "金诚同达OA" in SUPPORTED_SITES
