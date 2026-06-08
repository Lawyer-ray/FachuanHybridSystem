"""court_filing_helpers.py 单元测试 — 纯逻辑函数。"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.api.court_filing_schemas import (
    _DEFAULT_SLOT_BY_FILING_TYPE,
    _DEFENDANT_SIDE_STATUSES,
    _EXECUTION_HINT_STATUSES,
    _FILING_TYPE_CIVIL,
    _FILING_TYPE_EXECUTION,
    _PLAINTIFF_SIDE_STATUSES,
    _TEXT_NORMALIZE_PATTERN,
    _THIRD_SIDE_STATUSES,
    _VALID_FILING_ENGINES,
    _VALID_FILING_TYPES,
)


# ── _to_valid_mobile ─────────────────────────────────────────────────────────

class TestToValidMobile:
    """_to_valid_mobile 手机号校验。"""

    @pytest.mark.parametrize("value,expected", [
        ("13800000000", "13800000000"),
        (" 13800000000 ", "13800000000"),
        ("013800000000", ""),          # 不以1开头
        ("1380013800", ""),            # 少一位
        ("138000000001", ""),          # 多一位
        ("abc", ""),
        ("", ""),
        (None, ""),
        ("138-0000-0000", "13800000000"),
    ])
    def test_to_valid_mobile(self, value, expected):
        from apps.automation.api.court_filing_helpers import _to_valid_mobile
        assert _to_valid_mobile(value) == expected


# ── _normalize_filing_type ───────────────────────────────────────────────────

class TestNormalizeFilingType:

    def test_returns_valid_type_directly(self):
        from apps.automation.api.court_filing_helpers import _normalize_filing_type
        case = SimpleNamespace(name="test", cause_of_action="")
        result = _normalize_filing_type(requested_filing_type="civil", case=case, parties=[])
        assert result == "civil"

    def test_case_insensitive(self):
        from apps.automation.api.court_filing_helpers import _normalize_filing_type
        case = SimpleNamespace(name="test", cause_of_action="")
        result = _normalize_filing_type(requested_filing_type="EXECUTION", case=case, parties=[])
        assert result == "execution"

    @patch("apps.automation.api.court_filing_helpers._infer_filing_type", return_value="execution")
    def test_delegates_to_infer_when_invalid(self, mock_infer):
        from apps.automation.api.court_filing_helpers import _normalize_filing_type
        case = SimpleNamespace()
        result = _normalize_filing_type(requested_filing_type="unknown", case=case, parties=[])
        assert result == "execution"
        mock_infer.assert_called_once()


# ── _normalize_filing_engine ─────────────────────────────────────────────────

class TestNormalizeFilingEngine:

    @pytest.mark.parametrize("requested,expected", [
        ("api", "api"),
        ("playwright", "playwright"),
        ("API", "api"),
        (None, "api"),
        ("", "api"),
        ("unknown", "api"),
    ])
    def test_normalize_filing_engine(self, requested, expected):
        from apps.automation.api.court_filing_helpers import _normalize_filing_engine
        assert _normalize_filing_engine(requested) == expected


# ── _build_execution_reason_text ─────────────────────────────────────────────

class TestBuildExecutionReasonText:

    def test_with_cause_and_number(self):
        from apps.automation.api.court_filing_helpers import _build_execution_reason_text
        case = SimpleNamespace(cause_of_action="借款合同纠纷")
        result = _build_execution_reason_text(case=case, original_case_number="(2024)粤01民初100号")
        assert "借款合同纠纷" in result
        assert "(2024)粤01民初100号" in result
        assert "生效法律文书" in result

    def test_without_cause(self):
        from apps.automation.api.court_filing_helpers import _build_execution_reason_text
        case = SimpleNamespace(cause_of_action="")
        result = _build_execution_reason_text(case=case, original_case_number="(2024)粤01民初100号")
        assert "(2024)粤01民初100号" in result
        assert "相关义务" not in result

    def test_without_number_uses_fallback(self):
        from apps.automation.api.court_filing_helpers import _build_execution_reason_text
        case = SimpleNamespace(cause_of_action="")
        result = _build_execution_reason_text(case=case, original_case_number="")
        assert "相关" in result


# ── _resolve_original_case_number ────────────────────────────────────────────

class TestResolveOriginalCaseNumber:

    def test_returns_active_number(self):
        from apps.automation.api.court_filing_helpers import _resolve_original_case_number
        active = SimpleNamespace(number="(2024)粤01民初100号")
        inactive = SimpleNamespace(number="(2023)粤01民初99号")
        qs = MagicMock()
        qs.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = "(2024)粤01民初100号"
        case = SimpleNamespace(case_numbers=qs)
        result = _resolve_original_case_number(case)
        assert result == "(2024)粤01民初100号"

    def test_no_case_numbers_returns_empty(self):
        from apps.automation.api.court_filing_helpers import _resolve_original_case_number
        case = SimpleNamespace(case_numbers=None)
        assert _resolve_original_case_number(case) == ""


# ── _normalize_text ──────────────────────────────────────────────────────────

class TestNormalizeText:

    def test_strips_and_lowercases(self):
        from apps.automation.api.court_filing_helpers import _normalize_text
        assert _normalize_text("Hello World") == "helloworld"

    def test_removes_special_chars(self):
        from apps.automation.api.court_filing_helpers import _normalize_text
        assert _normalize_text("test/path(name)") == "testpathname"

    def test_empty_input(self):
        from apps.automation.api.court_filing_helpers import _normalize_text
        assert _normalize_text("") == ""
        assert _normalize_text(None) == ""


# ── _score_slot_for_signal ───────────────────────────────────────────────────

class TestScoreSlotForSignal:

    def test_strong_match_scores_5(self):
        from apps.automation.api.court_filing_helpers import _score_slot_for_signal
        score = _score_slot_for_signal(
            signal="民事起诉状", strong=("起诉状",), weak=(), exclude=()
        )
        assert score == 5

    def test_weak_match_scores_2(self):
        from apps.automation.api.court_filing_helpers import _score_slot_for_signal
        score = _score_slot_for_signal(
            signal="something", strong=(), weak=("something",), exclude=()
        )
        assert score == 2

    def test_exclude_subtracts_6(self):
        from apps.automation.api.court_filing_helpers import _score_slot_for_signal
        score = _score_slot_for_signal(
            signal="证据目录", strong=("证据",), weak=(), exclude=("证据目录",)
        )
        assert score == 5 - 6

    def test_empty_signal_returns_0(self):
        from apps.automation.api.court_filing_helpers import _score_slot_for_signal
        score = _score_slot_for_signal(signal="", strong=("a",), weak=("b",), exclude=("c",))
        assert score == 0


# ── _score_slot_deduplicated ─────────────────────────────────────────────────

class TestScoreSlotDeduplicated:

    def test_primary_signal_weight_doubled(self):
        from apps.automation.api.court_filing_helpers import _score_slot_deduplicated
        score = _score_slot_deduplicated(
            primary_signals=["起诉状"],
            secondary_signals=[],
            strong=("起诉状",),
            weak=(),
            exclude=(),
        )
        assert score == 10  # 5 * 2

    def test_secondary_dedup_within_keyword(self):
        from apps.automation.api.court_filing_helpers import _score_slot_deduplicated
        # 同一关键词在多个辅信号中只计一次
        score = _score_slot_deduplicated(
            primary_signals=[],
            secondary_signals=["abc起诉状xyz", "def起诉状uvw"],
            strong=("起诉状",),
            weak=(),
            exclude=(),
        )
        assert score == 5  # 只计一次

    def test_empty_returns_zero(self):
        from apps.automation.api.court_filing_helpers import _score_slot_deduplicated
        assert _score_slot_deduplicated(
            primary_signals=[], secondary_signals=[], strong=("a",), weak=("b",), exclude=()
        ) == 0


# ── _build_material_slot_signals ─────────────────────────────────────────────

class TestBuildMaterialSlotSignals:

    def test_primary_from_type_name(self):
        from apps.automation.api.court_filing_helpers import _build_material_slot_signals
        material = SimpleNamespace(type_name="民事起诉状", type=None, source_attachment=None)
        primary, secondary = _build_material_slot_signals(
            material=material, file_path=Path("/tmp/complaint.pdf")
        )
        assert any("民事起诉状" in s for s in primary)

    def test_secondary_from_filename(self):
        from apps.automation.api.court_filing_helpers import _build_material_slot_signals
        material = SimpleNamespace(type_name="test", type=None, source_attachment=None)
        primary, secondary = _build_material_slot_signals(
            material=material, file_path=Path("/tmp/身份证明.pdf")
        )
        assert any("身份证明" in s for s in secondary)


# ── _build_session_status_payload (filing) ───────────────────────────────────

class TestBuildFilingSessionStatusPayload:

    def test_pending_status(self):
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        from apps.automation.models import ScraperTaskStatus
        task = SimpleNamespace(id=1, status=ScraperTaskStatus.PENDING, result=None, error_message=None)
        payload = _build_session_status_payload(task=task)
        assert payload["success"] is True
        assert payload["status"] == "in_progress"

    def test_success_status(self):
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        from apps.automation.models import ScraperTaskStatus
        task = SimpleNamespace(id=2, status=ScraperTaskStatus.SUCCESS, result={"message": "完成"}, error_message="")
        payload = _build_session_status_payload(task=task)
        assert payload["success"] is True
        assert payload["status"] == "completed"
        assert payload["message"] == "完成"

    def test_failed_status_uses_error_message(self):
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        from apps.automation.models import ScraperTaskStatus
        task = SimpleNamespace(id=3, status=ScraperTaskStatus.FAILED, result=None, error_message="出错了")
        payload = _build_session_status_payload(task=task)
        assert payload["success"] is False
        assert payload["status"] == "failed"
        assert payload["message"] == "出错了"

    def test_failed_status_no_error_message_uses_default(self):
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        from apps.automation.models import ScraperTaskStatus
        task = SimpleNamespace(id=4, status=ScraperTaskStatus.FAILED, result=None, error_message="")
        payload = _build_session_status_payload(task=task)
        assert payload["message"] == "立案失败"

    def test_timing_included(self):
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        from apps.automation.models import ScraperTaskStatus
        task = SimpleNamespace(id=5, status=ScraperTaskStatus.PENDING,
                              result={"timing": {"overall_start": 100.0}}, error_message=None)
        payload = _build_session_status_payload(task=task)
        assert "timing" in payload
        assert payload["timing"]["overall_start"] == 100.0

    def test_result_message_used_for_running(self):
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        from apps.automation.models import ScraperTaskStatus
        task = SimpleNamespace(id=6, status=ScraperTaskStatus.RUNNING,
                              result={"message": "正在立案中..."}, error_message="")
        payload = _build_session_status_payload(task=task)
        assert payload["message"] == "正在立案中..."

    def test_failed_from_result_message(self):
        from apps.automation.api.court_filing_helpers import _build_session_status_payload
        from apps.automation.models import ScraperTaskStatus
        task = SimpleNamespace(id=7, status=ScraperTaskStatus.FAILED,
                              result={"message": "来自result的错误"}, error_message="")
        payload = _build_session_status_payload(task=task)
        assert payload["message"] == "来自result的错误"


# ── _update_session_task ─────────────────────────────────────────────────────

class TestUpdateSessionTask:

    def test_none_session_id_is_noop(self):
        from apps.automation.api.court_filing_helpers import _update_session_task
        # 应该不抛异常
        _update_session_task(session_id=None, status="running")


# ── _build_agent_payloads ────────────────────────────────────────────────────

class TestBuildAgentPayloads:

    def test_no_assignments_returns_empty(self):
        from apps.automation.api.court_filing_helpers import _build_agent_payloads
        case = SimpleNamespace(assignments=MagicMock(select_related=MagicMock(return_value=MagicMock(order_by=MagicMock(return_value=[])))))
        result = _build_agent_payloads(case=case, requester_id=None, parties=[])
        assert result == []

    def test_filters_duplicate_lawyers(self):
        from apps.automation.api.court_filing_helpers import _build_agent_payloads
        lawyer = SimpleNamespace(id=1, real_name="张律师", username="zhang", phone="13800000000",
                                 id_card="110101190001010000", license_no="12345",
                                 law_firm=SimpleNamespace(name="测试所", address="广州市"))
        assignment = SimpleNamespace(lawyer=lawyer)
        case = SimpleNamespace(assignments=MagicMock(
            select_related=MagicMock(return_value=MagicMock(order_by=MagicMock(return_value=[assignment])))
        ))
        result = _build_agent_payloads(case=case, requester_id=None, parties=[])
        assert len(result) == 1
        assert result[0]["name"] == "张律师"


# ── _build_party_payloads ────────────────────────────────────────────────────

class TestBuildPartyPayloads:

    @patch("apps.core.utils.id_card_utils.IdCardUtils.extract_gender", return_value="男")
    def test_natural_person_in_plaintiff(self, mock_extract_gender):
        from apps.automation.api.court_filing_helpers import _build_party_payloads
        client = SimpleNamespace(client_type="natural", name="张三", address="广州市",
                                phone="13800000000", id_number="110101190001010000",
                                id_card="110101190001010000")
        party = SimpleNamespace(client=client, legal_status="plaintiff")
        plaintiffs, defendants, thirds = _build_party_payloads([party])
        assert len(plaintiffs) == 1
        assert plaintiffs[0]["name"] == "张三"
        assert plaintiffs[0]["gender"] == "男"
        assert len(defendants) == 0

    def test_legal_person_in_defendant(self):
        from apps.automation.api.court_filing_helpers import _build_party_payloads
        client = SimpleNamespace(client_type="legal", name="测试公司", address="天河区",
                                phone="02000000000", id_number="91440101MA12345678",
                                legal_representative="李四", legal_representative_id_number="110101190001010001")
        party = SimpleNamespace(client=client, legal_status="defendant")
        plaintiffs, defendants, thirds = _build_party_payloads([party])
        assert len(plaintiffs) == 0
        assert len(defendants) == 1
        assert defendants[0]["uscc"] == "91440101MA12345678"


# ── _apply_execution_party_fallbacks ─────────────────────────────────────────

class TestApplyExecutionPartyFallbacks:

    def test_fills_phone_from_agent(self):
        from apps.automation.api.court_filing_helpers import _apply_execution_party_fallbacks
        plaintiffs = [{"client_type": "natural", "phone": "", "address": "广州"}]
        agents = [{"phone": "13800000000"}]
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == "13800000000"

    def test_does_not_overwrite_existing_phone(self):
        from apps.automation.api.court_filing_helpers import _apply_execution_party_fallbacks
        plaintiffs = [{"client_type": "natural", "phone": "13900000000", "address": "广州"}]
        agents = [{"phone": "13800000000"}]
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == "13900000000"

    def test_skips_legal_person(self):
        from apps.automation.api.court_filing_helpers import _apply_execution_party_fallbacks
        plaintiffs = [{"client_type": "legal", "phone": "", "address": ""}]
        agents = [{"phone": "13800000000"}]
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == ""


# ── _build_execution_request_text ────────────────────────────────────────────

class TestBuildExecutionRequestText:

    @patch("apps.documents.services.placeholders.litigation.execution_request_service.ExecutionRequestService")
    def test_uses_generated_text(self, mock_svc_cls):
        from apps.automation.api.court_filing_helpers import _build_execution_request_text
        mock_svc = MagicMock()
        mock_svc.generate.return_value = {"申请执行事项": "请求执行事项内容"}
        mock_svc_cls.return_value = mock_svc
        case = SimpleNamespace(id=1)
        result = _build_execution_request_text(case=case)
        assert "请求执行事项内容" in result

    @pytest.mark.django_db
    def test_fallback_when_no_service(self):
        from apps.automation.api.court_filing_helpers import _build_execution_request_text
        # 当 ExecutionRequestService 不可用时，使用 fallback 文本
        qs = MagicMock()
        qs.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = "(2024)粤01民初100号"
        case = SimpleNamespace(id=1, case_numbers=qs)
        result = _build_execution_request_text(case=case)
        # 应该包含执行请求相关内容
        assert len(result) > 0
