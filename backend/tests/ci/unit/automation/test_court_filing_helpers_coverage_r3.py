"""Extended coverage tests for automation/api/court_filing_helpers.py - Round 3.

Targets branches NOT covered by existing test files.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
try:
    from plugins.court_automation import filing
except ImportError:
    pytest.skip("court_automation plugin not installed", allow_module_level=True)


from plugins.court_automation.filing.helpers import (
    _apply_execution_party_fallbacks,
    _build_execution_reason_text,
    _build_material_slot_signals,
    _build_session_status_payload,
    _match_slot,
    _normalize_filing_engine,
    _normalize_filing_type,
    _normalize_text,
    _resolve_court_name,
    _resolve_original_case_number,
    _score_slot_deduplicated,
    _score_slot_for_signal,
    _to_valid_mobile,
    _update_session_task,
)
from plugins.court_automation.filing.schemas import (
    _FILING_ENGINE_API,
    _FILING_TYPE_CIVIL,
    _FILING_TYPE_EXECUTION,
)


class TestResolveCourtNameR3:
    def test_already_has_人民法院(self):
        result = _resolve_court_name("广州市天河区人民法院")
        assert result == "广州市天河区人民法院"

    @patch("apps.core.models.Court")
    def test_found_in_db(self, mock_court):
        mock_court.objects.filter.return_value.first.return_value = SimpleNamespace(name="深圳市南山区人民法院")
        result = _resolve_court_name("南山区")
        assert result == "深圳市南山区人民法院"

    @patch("apps.core.models.Court")
    def test_not_found_fallback(self, mock_court):
        mock_court.objects.filter.return_value.first.return_value = None
        result = _resolve_court_name("天河区")
        assert result == "天河区人民法院"


class TestNormalizeFilingTypeR3:
    def test_valid_requested(self):
        case = MagicMock()
        result = _normalize_filing_type(requested_filing_type="civil", case=case, parties=[])
        assert result == "civil"

    def test_valid_execution(self):
        case = MagicMock()
        result = _normalize_filing_type(requested_filing_type="execution", case=case, parties=[])
        assert result == "execution"

    @patch("plugins.court_automation.filing.helpers._infer_filing_type", return_value="civil")
    def test_invalid_falls_back_to_infer(self, mock_infer):
        case = MagicMock()
        result = _normalize_filing_type(requested_filing_type="invalid", case=case, parties=[])
        assert result == "civil"
        mock_infer.assert_called_once()

    @patch("plugins.court_automation.filing.helpers._infer_filing_type", return_value="execution")
    def test_none_falls_back_to_infer(self, mock_infer):
        case = MagicMock()
        result = _normalize_filing_type(requested_filing_type=None, case=case, parties=[])
        assert result == "execution"


class TestNormalizeFilingEngineR3:
    def test_valid_engine(self):
        assert _normalize_filing_engine("api") == "api"

    def test_invalid_defaults_to_api(self):
        assert _normalize_filing_engine("invalid") == _FILING_ENGINE_API

    def test_none_defaults_to_api(self):
        assert _normalize_filing_engine(None) == _FILING_ENGINE_API

    def test_empty_defaults_to_api(self):
        assert _normalize_filing_engine("") == _FILING_ENGINE_API


class TestToValidMobileR3:
    def test_valid_11_digit(self):
        assert _to_valid_mobile("13800138000") == "13800138000"

    def test_with_dashes(self):
        assert _to_valid_mobile("138-0013-8000") == "13800138000"

    def test_too_short(self):
        assert _to_valid_mobile("13800138") == ""

    def test_not_starting_with_1(self):
        assert _to_valid_mobile("23800138000") == ""

    def test_empty(self):
        assert _to_valid_mobile("") == ""


class TestApplyExecutionPartyFallbacksR3:
    def test_fills_phone_from_agent(self):
        plaintiffs = [{"client_type": "natural", "phone": "", "address": ""}]
        agents = [{"phone": "13800138000"}]
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == "13800138000"

    def test_keeps_existing_phone(self):
        plaintiffs = [{"client_type": "natural", "phone": "13900139000", "address": ""}]
        agents = [{"phone": "13800138000"}]
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == "13900139000"

    def test_skips_non_natural(self):
        plaintiffs = [{"client_type": "legal", "phone": "", "address": ""}]
        agents = [{"phone": "13800138000"}]
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == ""

    def test_strips_address(self):
        plaintiffs = [{"client_type": "natural", "phone": "", "address": "  广州  "}]
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=[])
        assert plaintiffs[0]["address"] == "广州"


class TestBuildExecutionReasonTextR3:
    def test_with_cause(self):
        case = SimpleNamespace(cause_of_action="买卖合同纠纷")
        result = _build_execution_reason_text(case=case, original_case_number="(2024)粤01民初123号")
        assert "(2024)粤01民初123号" in result
        assert "买卖合同纠纷" in result

    def test_without_cause(self):
        case = SimpleNamespace(cause_of_action="")
        result = _build_execution_reason_text(case=case, original_case_number="(2024)粤01民初123号")
        assert "被执行人" in result

    def test_empty_case_number(self):
        case = SimpleNamespace(cause_of_action="借款纠纷")
        result = _build_execution_reason_text(case=case, original_case_number="")
        assert "相关" in result


class TestScoreSlotForSignalR3:
    def test_empty_signal(self):
        assert _score_slot_for_signal(signal="", strong=("a",), weak=(), exclude=()) == 0

    def test_strong_match(self):
        score = _score_slot_for_signal(
            signal="这是起诉状的内容",
            strong=("起诉状",),
            weak=(),
            exclude=(),
        )
        assert score == 5

    def test_weak_match(self):
        score = _score_slot_for_signal(
            signal="这是一些内容",
            strong=(),
            weak=("内容",),
            exclude=(),
        )
        assert score == 2

    def test_exclude_match(self):
        score = _score_slot_for_signal(
            signal="这是限制高消费的内容",
            strong=("限制高消费",),
            weak=(),
            exclude=("限制高消费",),
        )
        assert score == -1


class TestScoreSlotDeduplicatedR3:
    def test_empty_signals(self):
        assert _score_slot_deduplicated(
            primary_signals=[], secondary_signals=[], strong=(), weak=(), exclude=()
        ) == 0

    def test_primary_signal_weighted(self):
        score = _score_slot_deduplicated(
            primary_signals=["起诉状"],
            secondary_signals=[],
            strong=("起诉状",),
            weak=(),
            exclude=(),
        )
        assert score == 10

    def test_secondary_not_duplicated(self):
        score = _score_slot_deduplicated(
            primary_signals=[],
            secondary_signals=["起诉状.pdf", "path/起诉状"],
            strong=("起诉状",),
            weak=(),
            exclude=(),
        )
        assert score == 5

    def test_exclude_in_primary_weighted(self):
        score = _score_slot_deduplicated(
            primary_signals=["限制高消费"],
            secondary_signals=[],
            strong=(),
            weak=(),
            exclude=("限制高消费",),
        )
        assert score == -12


class TestMatchSlotR3:
    def test_execution_with_申请执行书(self):
        material = SimpleNamespace(type_name="执行申请书", type=None, source_attachment=None)
        result = _match_slot(material=material, file_path=Path("执行申请书.pdf"), filing_type=_FILING_TYPE_EXECUTION)
        assert result == "0"

    def test_execution_限制高消费_excluded(self):
        material = SimpleNamespace(type_name="限制高消费申请书", type=None, source_attachment=None)
        result = _match_slot(
            material=material,
            file_path=Path("限制高消费.pdf"),
            filing_type=_FILING_TYPE_EXECUTION,
        )
        assert result != "0"

    def test_送达地址_slot(self):
        material = SimpleNamespace(type_name="送达地址确认书", type=None, source_attachment=None)
        result = _match_slot(
            material=material,
            file_path=Path("送达地址确认书.pdf"),
            filing_type=_FILING_TYPE_CIVIL,
        )
        assert result == "4"

    def test_保全_slot(self):
        material = SimpleNamespace(type_name="保全申请", type=None, source_attachment=None)
        result = _match_slot(
            material=material,
            file_path=Path("保全申请.pdf"),
            filing_type=_FILING_TYPE_CIVIL,
        )
        assert result == "5"


class TestBuildMaterialSlotSignalsR3:
    def test_type_name_in_primary(self):
        material = SimpleNamespace(type_name="身份证", type=None, source_attachment=None)
        primary, secondary = _build_material_slot_signals(
            material=material, file_path=Path("/docs/evidence.pdf")
        )
        assert any("身份证" in s for s in primary)

    def test_material_type_name_in_primary(self):
        mock_type = SimpleNamespace(name="合同")
        material = SimpleNamespace(type_name="", type=mock_type, source_attachment=None)
        primary, _ = _build_material_slot_signals(material=material, file_path=Path("test.pdf"))
        assert any("合同" in s for s in primary)

    def test_attachment_signals(self):
        mock_file = SimpleNamespace(name="att.pdf")
        mock_log = SimpleNamespace(content="some log text")
        mock_attachment = SimpleNamespace(file=mock_file, log=mock_log)
        material = SimpleNamespace(type_name="", type=None, source_attachment=mock_attachment)
        _, secondary = _build_material_slot_signals(material=material, file_path=Path("test.pdf"))
        # "att.pdf" gets normalized by _TEXT_NORMALIZE_PATTERN to "attpdf"
        assert any("attpdf" in s for s in secondary)


class TestBuildSessionStatusPayloadR3:
    def test_pending_status(self):
        task = SimpleNamespace(id=1, status="pending", result={}, error_message="")
        result = _build_session_status_payload(task=task)
        assert result["success"] is True
        assert result["status"] == "in_progress"

    def test_success_status(self):
        task = SimpleNamespace(id=1, status="success", result={}, error_message="")
        result = _build_session_status_payload(task=task)
        assert result["status"] == "completed"

    def test_failed_status(self):
        task = SimpleNamespace(id=1, status="failed", result={}, error_message="error occurred")
        result = _build_session_status_payload(task=task)
        assert result["status"] == "failed"
        assert "error occurred" in result["message"]

    def test_failed_no_message_fallback(self):
        task = SimpleNamespace(id=1, status="failed", result={}, error_message="")
        result = _build_session_status_payload(task=task)
        assert "立案失败" in result["message"]

    def test_with_timing(self):
        timing = {"login_end": 1.0}
        task = SimpleNamespace(id=1, status="success", result={"timing": timing}, error_message="")
        result = _build_session_status_payload(task=task)
        assert "timing" in result

    def test_pending_with_result_message(self):
        task = SimpleNamespace(id=1, status="pending", result={"message": "custom msg"}, error_message="")
        result = _build_session_status_payload(task=task)
        assert result["message"] == "custom msg"


class TestUpdateSessionTaskR3:
    def test_none_session_id_does_nothing(self):
        _update_session_task(session_id=None, status="running")

    def test_set_started_and_finished_keys(self):
        # Calls with real session_id will attempt DB access; verify no crash on None path
        _update_session_task(
            session_id=None,
            status="finished",
            error_message=None,
            result={"k": "v"},
            set_started=True,
            set_finished=True,
        )


class TestResolveOriginalCaseNumberR3:
    def test_no_case_numbers(self):
        case = SimpleNamespace(case_numbers=None)
        assert _resolve_original_case_number(case) == ""

    def test_active_number_first(self):
        mock_numbers = MagicMock()
        mock_numbers.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = "(2024)粤01民初1号"
        case = SimpleNamespace(case_numbers=mock_numbers)
        result = _resolve_original_case_number(case)
        assert "(2024)" in result

    def test_fallback_to_first(self):
        mock_numbers = MagicMock()
        mock_numbers.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = None
        mock_numbers.order_by.return_value.values_list.return_value.first.return_value = "(2023)粤01民初2号"
        case = SimpleNamespace(case_numbers=mock_numbers)
        result = _resolve_original_case_number(case)
        assert "(2023)" in result

    def test_no_numbers_at_all(self):
        mock_numbers = MagicMock()
        mock_numbers.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = None
        mock_numbers.order_by.return_value.values_list.return_value.first.return_value = None
        case = SimpleNamespace(case_numbers=mock_numbers)
        assert _resolve_original_case_number(case) == ""
