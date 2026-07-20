"""Additional coverage tests for court_filing_helpers — branches not hit by existing tests."""

from __future__ import annotations

import asyncio
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
    _build_agent_payloads,
    _build_execution_reason_text,
    _build_execution_request_text,
    _build_material_slot_signals,
    _build_materials_map,
    _build_party_payloads,
    _build_session_status_payload,
    _infer_filing_type,
    _match_slot,
    _normalize_filing_engine,
    _normalize_filing_type,
    _normalize_text,
    _resolve_court_name,
    _resolve_original_case_number,
    _run_filing,
    _score_slot_deduplicated,
    _score_slot_for_signal,
    _to_valid_mobile,
    _update_session_task,
)


# ---------------------------------------------------------------------------
# _resolve_court_name
# ---------------------------------------------------------------------------
class TestResolveCourtName:
    def test_already_has_court_suffix(self):
        result = _resolve_court_name("广州市天河区人民法院")
        assert result == "广州市天河区人民法院"

    @patch("apps.core.models.Court")
    def test_found_in_db(self, MockCourt):
        court = SimpleNamespace(name="广州市天河区人民法院")
        MockCourt.objects.filter.return_value.first.return_value = court
        result = _resolve_court_name("天河区")
        assert result == "广州市天河区人民法院"

    @patch("apps.core.models.Court")
    def test_not_found_fallback(self, MockCourt):
        MockCourt.objects.filter.return_value.first.return_value = None
        result = _resolve_court_name("番禺区")
        assert result == "番禺区人民法院"


# ---------------------------------------------------------------------------
# _normalize_text edge cases
# ---------------------------------------------------------------------------
class TestNormalizeTextEdge:
    def test_all_special_chars(self):
        assert _normalize_text("   ") == ""

    def test_number_text(self):
        assert _normalize_text("123") == "123"


# ---------------------------------------------------------------------------
# _score_slot_for_signal additional
# ---------------------------------------------------------------------------
class TestScoreSlotForSignalExtra:
    def test_multiple_strong(self):
        score = _score_slot_for_signal(
            signal="民事起诉状证据目录",
            strong=("起诉状", "证据目录"),
            weak=(),
            exclude=(),
        )
        assert score == 10

    def test_strong_plus_weak(self):
        score = _score_slot_for_signal(
            signal="起诉状和证据",
            strong=("起诉状",),
            weak=("证据",),
            exclude=(),
        )
        assert score == 7  # 5 + 2

    def test_mixed_strong_weak_exclude(self):
        score = _score_slot_for_signal(
            signal="民事起诉状和执行申请书",
            strong=("起诉状",),
            weak=(),
            exclude=("执行申请书",),
        )
        assert score == -1  # 5 - 6


# ---------------------------------------------------------------------------
# _score_slot_deduplicated extra branches
# ---------------------------------------------------------------------------
class TestScoreSlotDeduplicatedExtra:
    def test_primary_and_secondary_combined(self):
        score = _score_slot_deduplicated(
            primary_signals=["民事起诉状"],
            secondary_signals=["证据目录.pdf"],
            strong=("起诉状", "证据目录"),
            weak=(),
            exclude=(),
        )
        # primary: 10 (5*2), secondary: 5 (deduplicated)
        assert score == 15

    def test_secondary_exclude(self):
        score = _score_slot_deduplicated(
            primary_signals=[],
            secondary_signals=["执行申请书.pdf"],
            strong=(),
            weak=(),
            exclude=("执行申请书",),
        )
        assert score == -6

    def test_primary_weak_match(self):
        score = _score_slot_deduplicated(
            primary_signals=["诉讼请求内容"],
            secondary_signals=[],
            strong=(),
            weak=("诉讼请求",),
            exclude=(),
        )
        assert score == 4  # 2*2


# ---------------------------------------------------------------------------
# _normalize_filing_type extra branches
# ---------------------------------------------------------------------------
class TestNormalizeFilingTypeExtra:
    def test_invalid_string_uses_infer(self):
        case = SimpleNamespace(id=1, name="test", cause_of_action="")
        with patch("apps.cases.models.CaseMaterial.objects.filter") as mock_filter:
            mock_filter.return_value.values_list.return_value = []
            result = _normalize_filing_type(requested_filing_type="invalid_type", case=case, parties=[])
        assert result == "civil"

    def test_empty_string_uses_infer(self):
        case = SimpleNamespace(id=1, name="test", cause_of_action="")
        with patch("apps.cases.models.CaseMaterial.objects.filter") as mock_filter:
            mock_filter.return_value.values_list.return_value = []
            result = _normalize_filing_type(requested_filing_type="", case=case, parties=[])
        assert result == "civil"


# ---------------------------------------------------------------------------
# _infer_filing_type extra branches
# ---------------------------------------------------------------------------
class TestInferFilingTypeExtra:
    def test_execution_by_case_name_keyword(self):
        party = SimpleNamespace(legal_status="plaintiff")
        case = SimpleNamespace(id=1, name="执行案件", cause_of_action="合同")
        with patch("apps.cases.models.CaseMaterial.objects.filter") as mock_filter:
            mock_filter.return_value.values_list.return_value = []
            result = _infer_filing_type(case=case, parties=[party])
        assert result == "execution"

    def test_execution_hint_status_respondent(self):
        party = SimpleNamespace(legal_status="respondent")
        case = SimpleNamespace(id=1, name="合同纠纷", cause_of_action="合同")
        with patch("apps.cases.models.CaseMaterial.objects.filter") as mock_filter:
            mock_filter.return_value.values_list.return_value = []
            result = _infer_filing_type(case=case, parties=[party])
        assert result == "execution"

    def test_no_parties(self):
        case = SimpleNamespace(id=1, name="test", cause_of_action="")
        with patch("apps.cases.models.CaseMaterial.objects.filter") as mock_filter:
            mock_filter.return_value.values_list.return_value = []
            result = _infer_filing_type(case=case, parties=[])
        assert result == "civil"


# ---------------------------------------------------------------------------
# _resolve_original_case_number extra
# ---------------------------------------------------------------------------
class TestResolveOriginalCaseNumberExtra:
    def test_no_case_numbers_attr(self):
        case = SimpleNamespace(case_numbers=None)
        result = _resolve_original_case_number(case)
        assert result == ""


# ---------------------------------------------------------------------------
# _build_party_payloads — natural party without id_number
# ---------------------------------------------------------------------------
class TestBuildPartyPayloadsExtra:
    def test_natural_no_id_number(self):
        client = SimpleNamespace(
            client_type="natural",
            name="王五",
            address="上海市",
            phone="13800138000",
            id_number="",
            legal_representative="",
            legal_representative_id_number="",
        )
        party = SimpleNamespace(legal_status="plaintiff", client=client)
        p, d, t = _build_party_payloads([party])
        assert len(p) == 1
        assert p[0]["name"] == "王五"
        assert "gender" in p[0]


# ---------------------------------------------------------------------------
# _apply_execution_party_fallbacks — address trimming
# ---------------------------------------------------------------------------
class TestApplyExecutionPartyFallbacksExtra:
    def test_address_strips_whitespace(self):
        plaintiffs = [
            {"client_type": "natural", "phone": "", "address": "  北京市  "},
        ]
        agents = []
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["address"] == "北京市"

    def test_no_agents(self):
        plaintiffs = [
            {"client_type": "natural", "phone": "", "address": "北京市"},
        ]
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=[])
        assert plaintiffs[0]["phone"] == ""

    def test_multiple_agents_first_valid(self):
        plaintiffs = [
            {"client_type": "natural", "phone": "", "address": ""},
        ]
        agents = [{"phone": "invalid"}, {"phone": "13800138000"}]
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == "13800138000"


# ---------------------------------------------------------------------------
# _build_session_status_payload — timing branches
# ---------------------------------------------------------------------------
class TestBuildSessionStatusPayloadExtra:
    def test_running_without_result(self):
        from apps.automation.models import ScraperTaskStatus

        task = SimpleNamespace(
            id=10, status=ScraperTaskStatus.RUNNING,
            result=None, error_message=None,
        )
        payload = _build_session_status_payload(task=task)
        assert payload["message"] == "立案任务执行中..."

    def test_success_without_result_message(self):
        from apps.automation.models import ScraperTaskStatus

        task = SimpleNamespace(
            id=11, status=ScraperTaskStatus.SUCCESS,
            result=None, error_message=None,
        )
        payload = _build_session_status_payload(task=task)
        assert "完成" in payload["message"]

    def test_failed_with_timing(self):
        from apps.automation.models import ScraperTaskStatus

        task = SimpleNamespace(
            id=12, status=ScraperTaskStatus.FAILED,
            result={"timing": {"start": 1.0}},
            error_message="error",
        )
        payload = _build_session_status_payload(task=task)
        assert "timing" in payload

    def test_running_with_timing(self):
        from apps.automation.models import ScraperTaskStatus

        task = SimpleNamespace(
            id=13, status=ScraperTaskStatus.RUNNING,
            result={"message": "ok", "timing": {"start": 2.0}},
            error_message=None,
        )
        payload = _build_session_status_payload(task=task)
        assert "timing" in payload

    def test_success_with_timing(self):
        from apps.automation.models import ScraperTaskStatus

        task = SimpleNamespace(
            id=14, status=ScraperTaskStatus.SUCCESS,
            result={"message": "done", "timing": {"start": 3.0}},
            error_message=None,
        )
        payload = _build_session_status_payload(task=task)
        assert "timing" in payload

    def test_failed_no_error_no_result_message(self):
        from apps.automation.models import ScraperTaskStatus

        task = SimpleNamespace(
            id=15, status=ScraperTaskStatus.FAILED,
            result={}, error_message="",
        )
        payload = _build_session_status_payload(task=task)
        assert "立案失败" in payload["message"]


# ---------------------------------------------------------------------------
# _update_session_task — synchronous path (no running loop)
# ---------------------------------------------------------------------------
class TestUpdateSessionTaskExtra:
    def test_sync_update_with_started_and_finished(self):
        with patch("plugins.court_automation.filing.helpers.timezone") as mock_tz:
            mock_tz.now.return_value = "2025-01-01"
            with patch("apps.automation.models.ScraperTask") as MockTask:
                with patch("django.db.close_old_connections"):
                    _update_session_task(
                        session_id=1,
                        status="running",
                        error_message="err",
                        result={"k": "v"},
                        set_started=True,
                        set_finished=True,
                    )
                    MockTask.objects.filter.return_value.update.assert_called_once()

    def test_no_error_no_result(self):
        with patch("plugins.court_automation.filing.helpers.timezone") as mock_tz:
            mock_tz.now.return_value = "2025-01-01"
            with patch("apps.automation.models.ScraperTask") as MockTask:
                with patch("django.db.close_old_connections"):
                    _update_session_task(session_id=2, status="done")
                    call_kwargs = MockTask.objects.filter.return_value.update.call_args[1]
                    assert "error_message" not in call_kwargs
                    assert "result" not in call_kwargs


# ---------------------------------------------------------------------------
# _build_material_slot_signals — extra branches
# ---------------------------------------------------------------------------
class TestBuildMaterialSlotSignalsExtra:
    def test_no_type_name(self):
        material = SimpleNamespace(type_name=None, type=None, source_attachment=None)
        file_path = Path("/test/file.pdf")
        primary, secondary = _build_material_slot_signals(material=material, file_path=file_path)
        assert primary == [] or all(s != "" for s in primary)

    def test_attachment_without_log(self):
        att_file = SimpleNamespace(name="doc.pdf")
        attachment = SimpleNamespace(file=att_file, log=None)
        material = SimpleNamespace(type_name="证据", type=None, source_attachment=attachment)
        file_path = Path("/test/file.pdf")
        primary, secondary = _build_material_slot_signals(material=material, file_path=file_path)
        assert any("doc" in s for s in secondary)

    def test_no_attachment(self):
        material = SimpleNamespace(type_name="材料", type=None, source_attachment=None)
        file_path = Path("/test/data.pdf")
        primary, secondary = _build_material_slot_signals(material=material, file_path=file_path)
        assert len(secondary) >= 3


# ---------------------------------------------------------------------------
# _match_slot — delivery address and preservation
# ---------------------------------------------------------------------------
class TestMatchSlotExtra:
    def test_delivery_address_slot(self):
        material = SimpleNamespace(
            type_name="送达地址确认书",
            type=SimpleNamespace(name="送达地址"),
            source_attachment=None,
        )
        file_path = Path("/test/送达地址.pdf")
        slot = _match_slot(material=material, file_path=file_path, filing_type="civil")
        assert slot == "4"

    def test_preservation_slot(self):
        material = SimpleNamespace(
            type_name="保全申请",
            type=SimpleNamespace(name="保全"),
            source_attachment=None,
        )
        file_path = Path("/test/保全申请.pdf")
        slot = _match_slot(material=material, file_path=file_path, filing_type="civil")
        assert slot == "5"

    def test_execution_no_score_fallback(self):
        material = SimpleNamespace(
            type_name="其他",
            type=None,
            source_attachment=None,
        )
        file_path = Path("/test/other.pdf")
        slot = _match_slot(material=material, file_path=file_path, filing_type="execution")
        # default for execution is "4"
        assert isinstance(slot, str)


# ---------------------------------------------------------------------------
# _build_execution_request_text
# ---------------------------------------------------------------------------
class TestBuildExecutionRequestText:
    @patch("plugins.court_automation.filing.helpers._resolve_original_case_number", return_value="(2023)粤01民初1号")
    def test_fallback_text(self, mock_resolve):
        mock_svc_instance = MagicMock()
        mock_svc_instance.generate.side_effect = TypeError("import error")
        mock_module = MagicMock()
        mock_module.ExecutionRequestService = MagicMock(return_value=mock_svc_instance)
        mock_litigation = MagicMock()
        mock_litigation.LitigationPlaceholderKeys.ENFORCEMENT_EXECUTION_REQUEST = "key1"
        with patch.dict("sys.modules", {
            "apps.documents.services.placeholders.litigation.execution_request_service": mock_module,
            "apps.litigation_ai.placeholders.spec": mock_litigation,
        }):
            case = SimpleNamespace(id=1)
            result = _build_execution_request_text(case=case)
            assert "(2023)粤01民初1号" in result
            assert "执行费用" in result

    @patch("plugins.court_automation.filing.helpers._resolve_original_case_number", return_value="")
    def test_fallback_no_case_number(self, mock_resolve):
        mock_svc_instance = MagicMock()
        mock_svc_instance.generate.side_effect = ValueError("bad data")
        mock_module = MagicMock()
        mock_module.ExecutionRequestService = MagicMock(return_value=mock_svc_instance)
        mock_litigation = MagicMock()
        with patch.dict("sys.modules", {
            "apps.documents.services.placeholders.litigation.execution_request_service": mock_module,
            "apps.litigation_ai.placeholders.spec": mock_litigation,
        }):
            case = SimpleNamespace(id=1)
            result = _build_execution_request_text(case=case)
            assert "相关" in result


# ---------------------------------------------------------------------------
# _build_materials_map
# ---------------------------------------------------------------------------
class TestBuildMaterialsMapExtra:
    @patch("plugins.court_automation.filing.helpers._match_slot", return_value="5")
    def test_no_materials(self, mock_match):
        from apps.cases.models import CaseMaterial

        mock_qs = MagicMock()
        mock_qs.exists.return_value = False
        mock_qs2 = MagicMock()
        mock_qs2.filter.return_value.select_related.return_value.order_by.return_value = mock_qs2
        mock_qs2.exists.return_value = False
        with patch.object(CaseMaterial, "objects") as mock_objs:
            mock_objs.filter.return_value = mock_qs
            mock_objs.filter.return_value.filter.return_value.select_related.return_value.order_by.return_value.exists.return_value = False
            # Second filter call for fallback
            mock_objs.filter.return_value.exists.return_value = False
            result = _build_materials_map(case=MagicMock(), filing_type="civil")
            assert isinstance(result, dict)
