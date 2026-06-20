"""Comprehensive tests for automation.api.court_filing_helpers.

Covers all branches: resolve_court_name, normalize_filing_type/engine,
infer_filing_type, resolve_original_case_number, build_party_payloads,
to_valid_mobile, apply_execution_party_fallbacks, build_agent_payloads,
build_execution_reason_text, build_execution_request_text, normalize_text,
score_slot_for_signal, build_material_slot_signals, score_slot_deduplicated,
match_slot, build_materials_map, build_session_status_payload,
update_session_task.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# _resolve_court_name
# ---------------------------------------------------------------------------


class TestResolveCourtName:
    """Tests for _resolve_court_name."""

    def _fn(self):
        from plugins.court_automation.filing.helpers import _resolve_court_name
        return _resolve_court_name

    def test_already_has_renmfy(self):
        assert self._fn()("广州市天河区人民法院") == "广州市天河区人民法院"

    @pytest.mark.django_db
    def test_not_found_appends_suffix(self):
        assert self._fn()("不存在的法院ABC") == "不存在的法院ABC人民法院"

    def test_contains_renmfy_substring(self):
        """Authority name containing 人民法院 is returned as-is."""
        assert self._fn()("某人民法院") == "某人民法院"


# ---------------------------------------------------------------------------
# _normalize_filing_type / _normalize_filing_engine
# ---------------------------------------------------------------------------


class TestNormalizeFilingType:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _normalize_filing_type
        return _normalize_filing_type

    def test_valid_type_civil(self):
        result = self._fn()(requested_filing_type="civil", case=MagicMock(), parties=[])
        assert result == "civil"

    def test_valid_type_execution(self):
        result = self._fn()(requested_filing_type="execution", case=MagicMock(), parties=[])
        assert result == "execution"

    def test_case_insensitive(self):
        result = self._fn()(requested_filing_type="CIVIL", case=MagicMock(), parties=[])
        assert result == "civil"

    def test_invalid_type_delegates_to_infer(self):
        with patch("plugins.court_automation.filing.helpers._infer_filing_type", return_value="execution") as m:
            result = self._fn()(requested_filing_type="unknown", case=MagicMock(), parties=[])
            assert result == "execution"
            m.assert_called_once()

    def test_none_delegates_to_infer(self):
        with patch("plugins.court_automation.filing.helpers._infer_filing_type", return_value="civil") as m:
            result = self._fn()(requested_filing_type=None, case=MagicMock(), parties=[])
            assert result == "civil"

    def test_whitespace_delegates_to_infer(self):
        with patch("plugins.court_automation.filing.helpers._infer_filing_type", return_value="civil"):
            result = self._fn()(requested_filing_type="  ", case=MagicMock(), parties=[])
            assert result == "civil"


class TestNormalizeFilingEngine:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _normalize_filing_engine
        return _normalize_filing_engine

    def test_valid_engine(self):
        assert self._fn()("api") == "api"

    def test_invalid_engine_returns_default(self):
        assert self._fn()("browser") == "api"

    def test_none_returns_default(self):
        assert self._fn()(None) == "api"

    def test_empty_returns_default(self):
        assert self._fn()("") == "api"


# ---------------------------------------------------------------------------
# _infer_filing_type
# ---------------------------------------------------------------------------


class TestInferFilingType:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _infer_filing_type
        return _infer_filing_type

    def test_execution_hint_statuses(self):
        party = MagicMock()
        party.legal_status = "applicant"
        case = MagicMock()
        case.name = "test"
        case.cause_of_action = ""
        with patch("plugins.court_automation.filing.helpers._EXECUTION_HINT_STATUSES", {"applicant"}):
            with patch("apps.cases.models.CaseMaterial") as mock_cm:
                mock_cm.objects.filter.return_value.values_list.return_value = []
                assert self._fn()(case=case, parties=[party]) == "execution"

    def test_case_name_contains_execution_keyword(self):
        party = MagicMock()
        party.legal_status = "plaintiff"
        case = MagicMock()
        case.name = "申请执行纠纷"
        case.cause_of_action = ""
        with patch("plugins.court_automation.filing.helpers._EXECUTION_HINT_STATUSES", set()):
            with patch("apps.cases.models.CaseMaterial") as mock_cm:
                mock_cm.objects.filter.return_value.values_list.return_value = []
                assert self._fn()(case=case, parties=[party]) == "execution"

    def test_cause_of_action_contains_execution_keyword(self):
        party = MagicMock()
        party.legal_status = "plaintiff"
        case = MagicMock()
        case.name = ""
        case.cause_of_action = "申请执行"
        with patch("plugins.court_automation.filing.helpers._EXECUTION_HINT_STATUSES", set()):
            with patch("apps.cases.models.CaseMaterial") as mock_cm:
                mock_cm.objects.filter.return_value.values_list.return_value = []
                assert self._fn()(case=case, parties=[party]) == "execution"

    def test_material_type_name_contains_execution_keyword(self):
        party = MagicMock()
        party.legal_status = "plaintiff"
        case = MagicMock()
        case.name = ""
        case.cause_of_action = ""
        with patch("plugins.court_automation.filing.helpers._EXECUTION_HINT_STATUSES", set()):
            with patch("apps.cases.models.CaseMaterial") as mock_cm:
                mock_cm.objects.filter.return_value.values_list.return_value = ["执行申请书"]
                assert self._fn()(case=case, parties=[party]) == "execution"

    def test_default_civil(self):
        party = MagicMock()
        party.legal_status = "plaintiff"
        case = MagicMock()
        case.name = ""
        case.cause_of_action = ""
        with patch("plugins.court_automation.filing.helpers._EXECUTION_HINT_STATUSES", set()):
            with patch("apps.cases.models.CaseMaterial") as mock_cm:
                mock_cm.objects.filter.return_value.values_list.return_value = []
                assert self._fn()(case=case, parties=[party]) == "civil"


# ---------------------------------------------------------------------------
# _resolve_original_case_number
# ---------------------------------------------------------------------------


class TestResolveOriginalCaseNumber:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _resolve_original_case_number
        return _resolve_original_case_number

    def test_no_case_numbers_attr(self):
        case = MagicMock(spec=[])  # no case_numbers
        assert self._fn()(case) == ""

    def test_active_number_found(self):
        case = MagicMock()
        qs = MagicMock()
        qs.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = "(2025)粤01民初1号"
        case.case_numbers = qs
        assert self._fn()(case) == "(2025)粤01民初1号"

    def test_fallback_number_found(self):
        case = MagicMock()
        qs = MagicMock()
        qs.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = None
        qs.order_by.return_value.values_list.return_value.first.return_value = "(2025)粤01民初2号"
        case.case_numbers = qs
        assert self._fn()(case) == "(2025)粤01民初2号"

    def test_no_numbers(self):
        case = MagicMock()
        qs = MagicMock()
        qs.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = None
        qs.order_by.return_value.values_list.return_value.first.return_value = None
        case.case_numbers = qs
        assert self._fn()(case) == ""


# ---------------------------------------------------------------------------
# _to_valid_mobile
# ---------------------------------------------------------------------------


class TestToValidMobile:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _to_valid_mobile
        return _to_valid_mobile

    def test_valid_mobile(self):
        assert self._fn()("13800138000") == "13800138000"

    def test_mobile_with_spaces(self):
        assert self._fn()("138 0013 8000") == "13800138000"

    def test_invalid_mobile(self):
        assert self._fn()("12345") == ""

    def test_empty(self):
        assert self._fn()("") == ""

    def test_none(self):
        assert self._fn()(None) == ""

    def test_non_digit_chars(self):
        assert self._fn()("abc13800138000xyz") == "13800138000"

    def test_12_digits(self):
        assert self._fn()("138001380001") == ""

    def test_starts_with_2(self):
        assert self._fn()("23800138000") == ""


# ---------------------------------------------------------------------------
# _build_party_payloads
# ---------------------------------------------------------------------------


class TestBuildPartyPayloads:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _build_party_payloads
        return _build_party_payloads

    def _make_party(self, legal_status: str, client_type: str = "natural", **client_kw):
        party = MagicMock()
        party.legal_status = legal_status
        client = MagicMock()
        client.client_type = client_type
        client.name = client_kw.get("name", "张三")
        client.address = client_kw.get("address", "地址1")
        client.phone = client_kw.get("phone", "13800138000")
        client.id_number = client_kw.get("id_number", "110101199001011234")
        client.legal_representative = client_kw.get("legal_rep", "李四")
        client.legal_representative_id_number = client_kw.get("legal_rep_id", "110101199001011235")
        party.client = client
        return party

    @patch("apps.core.utils.id_card_utils.IdCardUtils.extract_gender", return_value="男")
    def test_natural_plaintiff(self, mock_gender):
        party = self._make_party("plaintiff", "natural")
        plaintiffs, defendants, thirds = self._fn()([party])
        assert len(plaintiffs) == 1
        assert len(defendants) == 0
        assert plaintiffs[0]["client_type"] == "natural"
        assert plaintiffs[0]["gender"] == "男"

    @patch("apps.core.utils.id_card_utils.IdCardUtils.extract_gender", return_value=None)
    def test_natural_plaintiff_gender_fallback(self, mock_gender):
        party = self._make_party("plaintiff", "natural")
        plaintiffs, _, _ = self._fn()([party])
        assert plaintiffs[0]["gender"] == "男"

    def test_legal_defendant(self):
        party = self._make_party("defendant", "legal")
        _, defendants, _ = self._fn()([party])
        assert len(defendants) == 1
        assert defendants[0]["uscc"] == "110101199001011234"
        assert defendants[0]["legal_rep"] == "李四"

    def test_third_party(self):
        party = self._make_party("third", "natural")
        _, _, thirds = self._fn()([party])
        assert len(thirds) == 1

    def test_unknown_status_excluded(self):
        party = self._make_party("unknown_status", "natural")
        plaintiffs, defendants, thirds = self._fn()([party])
        assert len(plaintiffs) == 0
        assert len(defendants) == 0
        assert len(thirds) == 0

    def test_multiple_statuses(self):
        p1 = self._make_party("plaintiff", "natural")
        p2 = self._make_party("defendant", "legal")
        p3 = self._make_party("third", "natural")
        plaintiffs, defendants, thirds = self._fn()([p1, p2, p3])
        assert len(plaintiffs) == 1
        assert len(defendants) == 1
        assert len(thirds) == 1

    def test_empty_address_and_phone(self):
        party = self._make_party("plaintiff", "natural", address="", phone="")
        plaintiffs, _, _ = self._fn()([party])
        assert plaintiffs[0]["address"] == ""
        assert plaintiffs[0]["phone"] == ""


# ---------------------------------------------------------------------------
# _apply_execution_party_fallbacks
# ---------------------------------------------------------------------------


class TestApplyExecutionPartyFallbacks:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _apply_execution_party_fallbacks
        return _apply_execution_party_fallbacks

    def test_fills_phone_from_agent(self):
        plaintiffs = [{"client_type": "natural", "phone": "", "address": "addr"}]
        agents = [{"phone": "13800138000"}]
        self._fn()(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == "13800138000"

    def test_does_not_override_existing_phone(self):
        plaintiffs = [{"client_type": "natural", "phone": "13900139000", "address": "addr"}]
        agents = [{"phone": "13800138000"}]
        self._fn()(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == "13900139000"

    def test_skips_legal_client_type(self):
        plaintiffs = [{"client_type": "legal", "phone": "", "address": ""}]
        agents = [{"phone": "13800138000"}]
        self._fn()(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == ""

    def test_agent_phone_invalid(self):
        plaintiffs = [{"client_type": "natural", "phone": "", "address": ""}]
        agents = [{"phone": "invalid"}]
        self._fn()(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == ""

    def test_no_agents(self):
        plaintiffs = [{"client_type": "natural", "phone": "", "address": ""}]
        self._fn()(plaintiffs=plaintiffs, agents=[])
        assert plaintiffs[0]["phone"] == ""

    def test_address_preserved(self):
        plaintiffs = [{"client_type": "natural", "phone": "", "address": "  addr  "}]
        self._fn()(plaintiffs=plaintiffs, agents=[])
        assert plaintiffs[0]["address"] == "addr"  # stripped by the function


# ---------------------------------------------------------------------------
# _build_agent_payloads
# ---------------------------------------------------------------------------


class TestBuildAgentPayloads:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _build_agent_payloads
        return _fn

    def _fn_import(self):
        from plugins.court_automation.filing.helpers import _build_agent_payloads
        return _build_agent_payloads

    def _make_assignment(self, lawyer_id=1, real_name="律师A", username="lv_a",
                         phone="13800138000", id_card="110101199001011234",
                         license_no="12345", firm_name="律所A", firm_addr="地址A"):
        assignment = MagicMock()
        lawyer = MagicMock()
        lawyer.id = lawyer_id
        lawyer.real_name = real_name
        lawyer.username = username
        lawyer.phone = phone
        lawyer.id_card = id_card
        lawyer.license_no = license_no
        firm = MagicMock()
        firm.name = firm_name
        firm.address = firm_addr
        lawyer.law_firm = firm
        assignment.lawyer = lawyer
        return assignment

    def test_single_lawyer(self):
        case = MagicMock()
        case.assignments.select_related.return_value.order_by.return_value = [self._make_assignment()]
        party = MagicMock()
        party.client.phone = "13900139000"
        with patch("apps.organization.models.Lawyer") as mock_lawyer_cls:
            agents = self._fn_import()(case=case, requester_id=None, parties=[party])
        assert len(agents) == 1
        assert agents[0]["name"] == "律师A"
        assert agents[0]["bar_number"] == "12345"
        assert agents[0]["law_firm"] == "律所A"

    def test_duplicate_lawyers_deduped(self):
        case = MagicMock()
        a1 = self._make_assignment(lawyer_id=1)
        a2 = self._make_assignment(lawyer_id=1)
        case.assignments.select_related.return_value.order_by.return_value = [a1, a2]
        with patch("apps.organization.models.Lawyer"):
            agents = self._fn_import()(case=case, requester_id=None, parties=[])
        assert len(agents) == 1

    def test_lawyer_with_no_name_skipped(self):
        case = MagicMock()
        assignment = self._make_assignment(real_name="", username="")
        case.assignments.select_related.return_value.order_by.return_value = [assignment]
        with patch("apps.organization.models.Lawyer"):
            agents = self._fn_import()(case=case, requester_id=None, parties=[])
        assert len(agents) == 0

    def test_requester_added(self):
        case = MagicMock()
        case.assignments.select_related.return_value.order_by.return_value = []
        requester = MagicMock()
        requester.id = 99
        requester.real_name = "请求者"
        requester.username = "req"
        requester.phone = "13800138000"
        requester.id_card = ""
        requester.license_no = ""
        requester.law_firm = MagicMock(name="", address="")
        with patch("apps.organization.models.Lawyer") as mock_cls:
            mock_cls.objects.select_related.return_value.filter.return_value.first.return_value = requester
            agents = self._fn_import()(case=case, requester_id=99, parties=[])
        assert len(agents) == 1
        assert agents[0]["name"] == "请求者"

    def test_requester_not_found(self):
        case = MagicMock()
        case.assignments.select_related.return_value.order_by.return_value = []
        with patch("apps.organization.models.Lawyer") as mock_cls:
            mock_cls.objects.select_related.return_value.filter.return_value.first.return_value = None
            agents = self._fn_import()(case=case, requester_id=99, parties=[])
        assert len(agents) == 0

    def test_fallback_phone_from_party(self):
        case = MagicMock()
        assignment = self._make_assignment(phone="")
        case.assignments.select_related.return_value.order_by.return_value = [assignment]
        party = MagicMock()
        party.client.phone = "13900139000"
        with patch("apps.organization.models.Lawyer"):
            agents = self._fn_import()(case=case, requester_id=None, parties=[party])
        assert agents[0]["phone"] == "13900139000"

    def test_lawyer_no_law_firm(self):
        case = MagicMock()
        assignment = self._make_assignment(firm_name=None, firm_addr=None)
        assignment.lawyer.law_firm = None
        case.assignments.select_related.return_value.order_by.return_value = [assignment]
        with patch("apps.organization.models.Lawyer"):
            agents = self._fn_import()(case=case, requester_id=None, parties=[])
        assert agents[0]["law_firm"] == ""


# ---------------------------------------------------------------------------
# _build_execution_reason_text
# ---------------------------------------------------------------------------


class TestBuildExecutionReasonText:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _build_execution_reason_text
        return _build_execution_reason_text

    def test_with_cause_and_case_number(self):
        case = MagicMock()
        case.cause_of_action = "借款合同纠纷"
        result = self._fn()(case=case, original_case_number="(2025)粤01执1号")
        assert "借款合同纠纷" in result
        assert "(2025)粤01执1号" in result

    def test_without_cause(self):
        case = MagicMock()
        case.cause_of_action = ""
        result = self._fn()(case=case, original_case_number="(2025)粤01执1号")
        assert "被执行" in result
        assert "(2025)粤01执1号" in result

    def test_without_case_number(self):
        case = MagicMock()
        case.cause_of_action = ""
        result = self._fn()(case=case, original_case_number="")
        assert "相关" in result


# ---------------------------------------------------------------------------
# _build_execution_request_text
# ---------------------------------------------------------------------------


class TestBuildExecutionRequestText:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _build_execution_request_text
        return _build_execution_request_text

    def test_generated_text_returned(self):
        case = MagicMock()
        case.id = 1
        with patch("apps.litigation_ai.placeholders.spec.LitigationPlaceholderKeys") as mock_keys:
            mock_keys.ENFORCEMENT_EXECUTION_REQUEST = "key1"
            with patch(
                "apps.documents.services.placeholders.litigation.execution_request_service.ExecutionRequestService"
            ) as mock_svc:
                mock_svc.return_value.generate.return_value = {"key1": "请求事项内容"}
                result = self._fn()(case=case)
        assert "请求事项内容" in result

    def test_generated_text_with_newlines(self):
        case = MagicMock()
        case.id = 1
        with patch("apps.litigation_ai.placeholders.spec.LitigationPlaceholderKeys") as mock_keys:
            mock_keys.ENFORCEMENT_EXECUTION_REQUEST = "key1"
            with patch(
                "apps.documents.services.placeholders.litigation.execution_request_service.ExecutionRequestService"
            ) as mock_svc:
                mock_svc.return_value.generate.return_value = {"key1": "line1\a\nline2\r\nline3"}
                result = self._fn()(case=case)
        assert "line1" in result
        assert "\a" not in result

    def test_exception_falls_back(self):
        case = MagicMock()
        case.id = 1
        case.case_numbers = MagicMock(**{"filter.return_value.order_by.return_value.values_list.return_value.first.return_value": None, "order_by.return_value.values_list.return_value.first.return_value": None})
        with patch(
            "apps.documents.services.placeholders.litigation.execution_request_service.ExecutionRequestService"
        ) as mock_svc:
            mock_svc.side_effect = TypeError("boom")
            result = self._fn()(case=case)
        assert "强制执行" in result

    def test_fallback_with_case_number(self):
        case = MagicMock()
        case.id = 1
        case.case_numbers = MagicMock(**{
            "filter.return_value.order_by.return_value.values_list.return_value.first.return_value": "(2025)粤01执1号"
        })
        with patch(
            "apps.documents.services.placeholders.litigation.execution_request_service.ExecutionRequestService"
        ) as mock_svc:
            mock_svc.side_effect = TypeError("boom")
            result = self._fn()(case=case)
        assert "(2025)粤01执1号" in result


# ---------------------------------------------------------------------------
# _normalize_text
# ---------------------------------------------------------------------------


class TestNormalizeText:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _normalize_text
        return _normalize_text

    def test_strips_special_chars(self):
        result = self._fn()("民事-起诉状 (副本)")
        assert result == "民事起诉状副本"

    def test_empty(self):
        assert self._fn()("") == ""

    def test_none(self):
        assert self._fn()(None) == ""


# ---------------------------------------------------------------------------
# _score_slot_for_signal
# ---------------------------------------------------------------------------


class TestScoreSlotForSignal:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _score_slot_for_signal
        return _score_slot_for_signal

    def test_empty_signal(self):
        assert self._fn()(signal="", strong=(), weak=(), exclude=()) == 0

    def test_strong_hit(self):
        signal = "民事起诉状"
        result = self._fn()(signal=signal, strong=("起诉状",), weak=(), exclude=())
        assert result == 5

    def test_weak_hit(self):
        signal = "诉讼请求"
        result = self._fn()(signal=signal, strong=(), weak=("诉讼请求",), exclude=())
        assert result == 2

    def test_exclude_penalty(self):
        signal = "执行申请书"
        result = self._fn()(signal=signal, strong=(), weak=(), exclude=("执行申请书",))
        assert result == -6

    def test_combined(self):
        signal = "起诉状副本"
        result = self._fn()(signal=signal, strong=("起诉状",), weak=("副本",), exclude=("执行",))
        assert result == 7  # 5 + 2


# ---------------------------------------------------------------------------
# _build_material_slot_signals
# ---------------------------------------------------------------------------


class TestBuildMaterialSlotSignals:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _build_material_slot_signals
        return _build_material_slot_signals

    def test_basic_signals(self):
        material = MagicMock()
        material.type_name = "起诉状"
        material.type = MagicMock()
        material.type.name = "起诉材料"
        material.source_attachment = None
        file_path = Path("/tmp/起诉状.pdf")
        primary, secondary = self._fn()(material=material, file_path=file_path)
        assert any("起诉状" in s for s in primary)
        assert any("起诉材料" in s for s in primary)
        assert any("起诉状" in s for s in secondary) or any("pdf" in s for s in secondary)

    def test_with_attachment(self):
        material = MagicMock()
        material.type_name = "证据"
        material.type = None
        attachment = MagicMock()
        attachment.file.name = "evidence.pdf"
        attachment.log = MagicMock()
        attachment.log.content = "证据内容"
        material.source_attachment = attachment
        file_path = Path("/tmp/evidence.pdf")
        primary, secondary = self._fn()(material=material, file_path=file_path)
        assert any("证据" in s for s in primary)

    def test_dedup_primary_signals(self):
        material = MagicMock()
        material.type_name = "起诉状"
        material.type = MagicMock()
        material.type.name = "起诉状"  # same as type_name
        material.source_attachment = None
        file_path = Path("/tmp/test.pdf")
        primary, _ = self._fn()(material=material, file_path=file_path)
        assert primary.count("起诉状") == 1


# ---------------------------------------------------------------------------
# _score_slot_deduplicated
# ---------------------------------------------------------------------------


class TestScoreSlotDeduplicated:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _score_slot_deduplicated
        return _score_slot_deduplicated

    def test_empty_signals(self):
        assert self._fn()(primary_signals=[], secondary_signals=[], strong=(), weak=(), exclude=()) == 0

    def test_primary_strong_weight(self):
        result = self._fn()(
            primary_signals=["民事起诉状"],
            secondary_signals=[],
            strong=("起诉状",),
            weak=(),
            exclude=(),
        )
        assert result == 10  # 5 * 2

    def test_primary_weak_weight(self):
        result = self._fn()(
            primary_signals=["诉讼请求"],
            secondary_signals=[],
            strong=(),
            weak=("诉讼请求",),
            exclude=(),
        )
        assert result == 4  # 2 * 2

    def test_primary_exclude_penalty(self):
        result = self._fn()(
            primary_signals=["执行申请书"],
            secondary_signals=[],
            strong=(),
            weak=(),
            exclude=("执行申请书",),
        )
        assert result == -12  # -6 * 2

    def test_secondary_dedup(self):
        """Same keyword in multiple secondary signals only counts once."""
        result = self._fn()(
            primary_signals=[],
            secondary_signals=["起诉状a", "起诉状b"],
            strong=("起诉状",),
            weak=(),
            exclude=(),
        )
        assert result == 5  # only counted once

    def test_secondary_exclude_penalty(self):
        result = self._fn()(
            primary_signals=[],
            secondary_signals=["送达地址确认书"],
            strong=(),
            weak=(),
            exclude=("送达地址确认书",),
        )
        assert result == -6


# ---------------------------------------------------------------------------
# _match_slot
# ---------------------------------------------------------------------------


class TestMatchSlot:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _match_slot
        return _match_slot

    def test_returns_default_when_no_signals(self):
        material = MagicMock()
        material.type_name = ""
        material.type = None
        material.source_attachment = None
        file_path = Path("/tmp/random.pdf")
        result = self._fn()(material=material, file_path=file_path, filing_type="civil")
        assert result == "5"  # default for civil

    def test_execution_type_default(self):
        material = MagicMock()
        material.type_name = ""
        material.type = None
        material.source_attachment = None
        file_path = Path("/tmp/random.pdf")
        result = self._fn()(material=material, file_path=file_path, filing_type="execution")
        assert result == "4"  # default for execution

    def test_delivery_address_fallback(self):
        material = MagicMock()
        material.type_name = ""
        material.type = None
        material.source_attachment = None
        file_path = Path("/tmp/送达地址确认书.pdf")
        result = self._fn()(material=material, file_path=file_path, filing_type="civil")
        # Should match via keyword in file path
        assert result in ("4", "5")

    def test_execution_apply_keyword(self):
        material = MagicMock()
        material.type_name = "执行申请书"
        material.type = None
        material.source_attachment = None
        file_path = Path("/tmp/执行申请书.pdf")
        result = self._fn()(material=material, file_path=file_path, filing_type="execution")
        assert result == "0"


# ---------------------------------------------------------------------------
# _build_materials_map
# ---------------------------------------------------------------------------


class TestBuildMaterialsMap:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _build_materials_map
        return _build_materials_map

    @patch("apps.cases.models.CaseMaterial")
    def test_no_materials(self, mock_cm):
        mock_cm.objects.filter.return_value.filter.return_value.select_related.return_value.order_by.return_value.exists.return_value = False
        mock_cm.objects.filter.return_value.select_related.return_value.order_by.return_value = []
        case = MagicMock()
        result = self._fn()(case=case, filing_type="civil")
        assert result == {}

    @patch("apps.cases.models.CaseMaterialCategory")
    @patch("apps.cases.models.CaseMaterialSide")
    @patch("apps.cases.models.CaseMaterial")
    def test_with_pdf_material(self, mock_cm, mock_side, mock_cat):
        material = MagicMock()
        material.source_attachment_id = 1
        attachment = MagicMock()
        attachment.file.path = "/tmp/test.pdf"
        attachment.original_filename = "起诉状.pdf"
        material.source_attachment = attachment

        qs = MagicMock()
        qs.exists.return_value = True
        qs.__iter__ = MagicMock(return_value=iter([material]))
        qs.filter.return_value.select_related.return_value.order_by.return_value = qs
        qs.select_related.return_value.order_by.return_value = qs
        mock_cm.objects.filter.return_value.filter.return_value.select_related.return_value.order_by.return_value = qs

        with patch("plugins.court_automation.filing.helpers._match_slot", return_value="0"):
            with patch.object(Path, "exists", return_value=True):
                result = self._fn()(case=MagicMock(), filing_type="civil")
        assert "0" in result

    @patch("apps.cases.models.CaseMaterialCategory")
    @patch("apps.cases.models.CaseMaterialSide")
    @patch("apps.cases.models.CaseMaterial")
    def test_non_pdf_skipped(self, mock_cm, mock_side, mock_cat):
        material = MagicMock()
        material.source_attachment_id = 1
        attachment = MagicMock()
        attachment.file.path = "/tmp/test.docx"
        material.source_attachment = attachment

        qs = MagicMock()
        qs.exists.return_value = True
        qs.__iter__ = MagicMock(return_value=iter([material]))
        qs.filter.return_value.select_related.return_value.order_by.return_value = qs
        qs.select_related.return_value.order_by.return_value = qs
        mock_cm.objects.filter.return_value.filter.return_value.select_related.return_value.order_by.return_value = qs

        with patch.object(Path, "exists", return_value=True):
            result = self._fn()(case=MagicMock(), filing_type="civil")
        assert result == {}


# ---------------------------------------------------------------------------
# _build_session_status_payload (court filing version)
# ---------------------------------------------------------------------------


class TestBuildSessionStatusPayload:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _build_session_status_payload
        return _build_session_status_payload

    def test_pending_status(self):
        task = MagicMock()
        task.id = 1
        task.status = "pending"
        task.result = {"message": "执行中", "timing": {"t": 1.0}}
        task.error_message = ""
        with patch("apps.automation.models.ScraperTaskStatus") as mock_status:
            mock_status.PENDING = "pending"
            mock_status.RUNNING = "running"
            result = self._fn()(task=task)
        assert result["status"] == "in_progress"
        assert result["timing"] == {"t": 1.0}

    def test_success_status(self):
        task = MagicMock()
        task.id = 2
        task.status = "success"
        task.result = {"message": "完成"}
        task.error_message = ""
        with patch("apps.automation.models.ScraperTaskStatus") as mock_status:
            mock_status.SUCCESS = "success"
            result = self._fn()(task=task)
        assert result["status"] == "completed"
        assert result["success"] is True

    def test_failed_status_with_error_message(self):
        task = MagicMock()
        task.id = 3
        task.status = "failed"
        task.result = {}
        task.error_message = "登录失败"
        with patch("apps.automation.models.ScraperTaskStatus") as mock_status:
            mock_status.PENDING = "pending"
            mock_status.RUNNING = "running"
            mock_status.SUCCESS = "success"
            result = self._fn()(task=task)
        assert result["status"] == "failed"
        assert result["success"] is False
        assert "登录失败" in result["message"]

    def test_failed_status_with_result_message(self):
        task = MagicMock()
        task.id = 4
        task.status = "failed"
        task.result = {"message": "自定义失败消息"}
        task.error_message = ""
        with patch("apps.automation.models.ScraperTaskStatus") as mock_status:
            mock_status.PENDING = "pending"
            mock_status.RUNNING = "running"
            mock_status.SUCCESS = "success"
            result = self._fn()(task=task)
        assert "自定义失败消息" in result["message"]

    def test_failed_status_default_message(self):
        task = MagicMock()
        task.id = 5
        task.status = "failed"
        task.result = None
        task.error_message = ""
        with patch("apps.automation.models.ScraperTaskStatus") as mock_status:
            mock_status.PENDING = "pending"
            mock_status.RUNNING = "running"
            mock_status.SUCCESS = "success"
            result = self._fn()(task=task)
        assert result["message"] == "立案失败"

    def test_pending_with_non_dict_result(self):
        task = MagicMock()
        task.id = 6
        task.status = "pending"
        task.result = "not a dict"
        task.error_message = ""
        with patch("apps.automation.models.ScraperTaskStatus") as mock_status:
            mock_status.PENDING = "pending"
            mock_status.RUNNING = "running"
            result = self._fn()(task=task)
        assert result["message"] == "立案任务执行中..."

    def test_success_with_timing(self):
        task = MagicMock()
        task.id = 7
        task.status = "success"
        task.result = {"timing": {"overall_start": 100.0}}
        task.error_message = ""
        with patch("apps.automation.models.ScraperTaskStatus") as mock_status:
            mock_status.SUCCESS = "success"
            result = self._fn()(task=task)
        assert "timing" in result


# ---------------------------------------------------------------------------
# _update_session_task
# ---------------------------------------------------------------------------


class TestUpdateSessionTask:
    def _fn(self):
        from plugins.court_automation.filing.helpers import _update_session_task
        return _update_session_task

    def test_none_session_id_returns(self):
        self._fn()(session_id=None, status="running")
        # Should not raise

    @patch("plugins.court_automation.filing.helpers.asyncio.get_running_loop")
    @patch("plugins.court_automation.filing.helpers._SESSION_UPDATE_EXECUTOR")
    def test_with_event_loop_submits_to_executor(self, mock_executor, mock_loop):
        mock_loop.return_value = MagicMock()
        self._fn()(session_id=1, status="running", set_started=True, set_finished=True)
        mock_executor.submit.assert_called_once()

    @patch("plugins.court_automation.filing.helpers.asyncio.get_running_loop", side_effect=RuntimeError)
    def test_no_event_loop_runs_sync(self, mock_loop):
        with patch("apps.automation.models.ScraperTask") as mock_task:
            mock_task.objects.filter.return_value.update.return_value = 1
            with patch("django.db.close_old_connections"):
                self._fn()(session_id=1, status="running", error_message="err", result={"key": "val"})
            mock_task.objects.filter.assert_called_once_with(id=1)


# ---------------------------------------------------------------------------
# _get_organization_service
# ---------------------------------------------------------------------------


class TestGetOrganizationService:
    def test_returns_service(self):
        from plugins.court_automation.filing.helpers import _get_organization_service
        with patch("apps.core.dependencies.build_organization_service", return_value="svc"):
            result = _get_organization_service()
            assert result == "svc"
