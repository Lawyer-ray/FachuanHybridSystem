"""Comprehensive tests for court_filing_helpers data processing functions."""

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
    _build_agent_payloads,
    _build_execution_reason_text,
    _build_material_slot_signals,
    _build_party_payloads,
    _build_session_status_payload,
    _infer_filing_type,
    _match_slot,
    _normalize_filing_engine,
    _normalize_filing_type,
    _normalize_text,
    _resolve_original_case_number,
    _score_slot_deduplicated,
    _score_slot_for_signal,
    _to_valid_mobile,
    _update_session_task,
)


# ---------------------------------------------------------------------------
# _to_valid_mobile
# ---------------------------------------------------------------------------
class TestToValidMobile:
    def test_valid_number(self):
        assert _to_valid_mobile("13812345678") == "13812345678"

    def test_valid_with_dashes(self):
        assert _to_valid_mobile("138-1234-5678") == "13812345678"

    def test_invalid_short(self):
        assert _to_valid_mobile("123") == ""

    def test_invalid_prefix(self):
        assert _to_valid_mobile("23812345678") == ""

    def test_empty_string(self):
        assert _to_valid_mobile("") == ""

    def test_none(self):
        assert _to_valid_mobile(None) == ""  # type: ignore[arg-type]

    def test_with_spaces(self):
        assert _to_valid_mobile("138 1234 5678") == "13812345678"

    def test_letters_mixed(self):
        assert _to_valid_mobile("138abcd5678") == ""
        # With enough digits mixed with letters, becomes valid
        assert _to_valid_mobile("13812345678abc") == "13812345678"


# ---------------------------------------------------------------------------
# _normalize_text
# ---------------------------------------------------------------------------
class TestNormalizeText:
    def test_basic(self):
        result = _normalize_text("Hello World")
        assert result == "helloworld"

    def test_special_chars(self):
        result = _normalize_text("test/path(something)")
        # The pattern replaces path-like chars with empty
        assert "something" in result

    def test_chinese(self):
        result = _normalize_text("民事 起诉状")
        assert result == "民事起诉状"

    def test_empty(self):
        assert _normalize_text("") == ""

    def test_none(self):
        assert _normalize_text(None) == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _score_slot_for_signal
# ---------------------------------------------------------------------------
class TestScoreSlotForSignal:
    def test_strong_match(self):
        score = _score_slot_for_signal(
            signal="民事起诉状和证据目录",
            strong=("起诉状",),
            weak=("证据",),
            exclude=(),
        )
        assert score >= 5

    def test_weak_match(self):
        score = _score_slot_for_signal(
            signal="证据材料",
            strong=(),
            weak=("证据",),
            exclude=(),
        )
        assert score == 2

    def test_exclude_penalty(self):
        score = _score_slot_for_signal(
            signal="执行申请书",
            strong=(),
            weak=(),
            exclude=("执行申请书",),
        )
        assert score < 0

    def test_empty_signal(self):
        score = _score_slot_for_signal(
            signal="",
            strong=("test",),
            weak=(),
            exclude=(),
        )
        assert score == 0


# ---------------------------------------------------------------------------
# _score_slot_deduplicated
# ---------------------------------------------------------------------------
class TestScoreSlotDeduplicated:
    def test_primary_strong_match(self):
        score = _score_slot_deduplicated(
            primary_signals=["民事起诉状"],
            secondary_signals=[],
            strong=("起诉状",),
            weak=(),
            exclude=(),
        )
        assert score >= 10

    def test_secondary_deduplicated(self):
        score = _score_slot_deduplicated(
            primary_signals=[],
            secondary_signals=["证据目录.jpg", "证据目录.pdf"],
            strong=("证据目录",),
            weak=(),
            exclude=(),
        )
        # Should count strong only once for secondary signals
        assert score == 5

    def test_primary_excludes(self):
        score = _score_slot_deduplicated(
            primary_signals=["执行申请书"],
            secondary_signals=[],
            strong=(),
            weak=(),
            exclude=("执行申请书",),
        )
        assert score <= -12

    def test_empty(self):
        score = _score_slot_deduplicated(
            primary_signals=[],
            secondary_signals=[],
            strong=(),
            weak=(),
            exclude=(),
        )
        assert score == 0

    def test_primary_weak_match(self):
        score = _score_slot_deduplicated(
            primary_signals=["证据材料"],
            secondary_signals=[],
            strong=(),
            weak=("证据",),
            exclude=(),
        )
        assert score >= 4


# ---------------------------------------------------------------------------
# _normalize_filing_type
# ---------------------------------------------------------------------------
class TestNormalizeFilingType:
    def test_valid_civil(self):
        case = SimpleNamespace(name="test", cause_of_action="")
        result = _normalize_filing_type(requested_filing_type="civil", case=case, parties=[])
        assert result == "civil"

    def test_valid_execution(self):
        case = SimpleNamespace(name="test", cause_of_action="")
        result = _normalize_filing_type(requested_filing_type="execution", case=case, parties=[])
        assert result == "execution"

    def test_none_uses_infer(self):
        case = SimpleNamespace(id=1, name="test", cause_of_action="")
        parties = [SimpleNamespace(legal_status="plaintiff", client=SimpleNamespace(client_type="natural", name="A", address="", phone="", id_number="", legal_representative="", legal_representative_id_number=""))]
        with patch("apps.cases.models.CaseMaterial.objects.filter") as mock_filter:
            mock_filter.return_value.values_list.return_value = []
            result = _normalize_filing_type(requested_filing_type=None, case=case, parties=parties)
        assert result in ("civil", "execution")


# ---------------------------------------------------------------------------
# _normalize_filing_engine
# ---------------------------------------------------------------------------
class TestNormalizeFilingEngine:
    def test_api(self):
        assert _normalize_filing_engine("api") == "api"

    def test_playwright(self):
        assert _normalize_filing_engine("playwright") == "playwright"

    def test_unknown_defaults_api(self):
        assert _normalize_filing_engine("unknown") == "api"

    def test_none(self):
        assert _normalize_filing_engine(None) == "api"

    def test_whitespace(self):
        assert _normalize_filing_engine("  API  ") == "api"


# ---------------------------------------------------------------------------
# _build_execution_reason_text
# ---------------------------------------------------------------------------
class TestBuildExecutionReasonText:
    def test_with_cause(self):
        case = SimpleNamespace(cause_of_action="借款合同纠纷")
        result = _build_execution_reason_text(case=case, original_case_number="(2023)粤01民初1号")
        assert "借款合同纠纷" in result
        assert "(2023)粤01民初1号" in result

    def test_without_cause(self):
        case = SimpleNamespace(cause_of_action="")
        result = _build_execution_reason_text(case=case, original_case_number="")
        assert "相关" in result

    def test_with_none_cause(self):
        case = SimpleNamespace(cause_of_action=None)
        result = _build_execution_reason_text(case=case, original_case_number="(2023)粤01民初1号")
        assert "生效法律文书" in result


# ---------------------------------------------------------------------------
# _build_session_status_payload (court filing version)
# ---------------------------------------------------------------------------
class TestBuildSessionStatusPayload:
    def test_pending_status(self):
        from apps.automation.models import ScraperTaskStatus
        task = SimpleNamespace(
            id=1, status=ScraperTaskStatus.PENDING,
            result=None, error_message=None,
        )
        payload = _build_session_status_payload(task=task)
        assert payload["status"] == "in_progress"
        assert payload["success"] is True

    def test_running_with_message(self):
        from apps.automation.models import ScraperTaskStatus
        task = SimpleNamespace(
            id=2, status=ScraperTaskStatus.RUNNING,
            result={"message": "正在处理", "timing": {"start": 1.0}},
            error_message=None,
        )
        payload = _build_session_status_payload(task=task)
        assert payload["message"] == "正在处理"
        assert "timing" in payload

    def test_success_status(self):
        from apps.automation.models import ScraperTaskStatus
        task = SimpleNamespace(
            id=3, status=ScraperTaskStatus.SUCCESS,
            result={"message": "完成"}, error_message=None,
        )
        payload = _build_session_status_payload(task=task)
        assert payload["status"] == "completed"
        assert payload["success"] is True

    def test_failed_status_with_error(self):
        from apps.automation.models import ScraperTaskStatus
        task = SimpleNamespace(
            id=4, status=ScraperTaskStatus.FAILED,
            result=None, error_message="登录失败",
        )
        payload = _build_session_status_payload(task=task)
        assert payload["status"] == "failed"
        assert payload["success"] is False
        assert "登录失败" in payload["message"]

    def test_failed_no_error_uses_default(self):
        from apps.automation.models import ScraperTaskStatus
        task = SimpleNamespace(
            id=5, status=ScraperTaskStatus.FAILED,
            result=None, error_message="",
        )
        payload = _build_session_status_payload(task=task)
        assert "立案失败" in payload["message"]

    def test_failed_with_result_message(self):
        from apps.automation.models import ScraperTaskStatus
        task = SimpleNamespace(
            id=6, status=ScraperTaskStatus.FAILED,
            result={"message": "具体错误信息"}, error_message="",
        )
        payload = _build_session_status_payload(task=task)
        assert "具体错误信息" in payload["message"]


# ---------------------------------------------------------------------------
# _resolve_original_case_number
# ---------------------------------------------------------------------------
class TestResolveOriginalCaseNumber:
    def test_active_number(self):
        mock_qs = MagicMock()
        mock_qs.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = "(2023)粤01民初1号"
        case = SimpleNamespace(case_numbers=mock_qs)
        result = _resolve_original_case_number(case)
        assert result == "(2023)粤01民初1号"

    def test_no_case_numbers(self):
        case = SimpleNamespace(case_numbers=None)
        result = _resolve_original_case_number(case)
        assert result == ""

    def test_fallback_number(self):
        mock_qs = MagicMock()
        mock_qs.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = None
        mock_qs.order_by.return_value.values_list.return_value.first.return_value = "(2023)粤01民初2号"
        case = SimpleNamespace(case_numbers=mock_qs)
        result = _resolve_original_case_number(case)
        assert result == "(2023)粤01民初2号"

    def test_empty_numbers(self):
        mock_qs = MagicMock()
        mock_qs.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = None
        mock_qs.order_by.return_value.values_list.return_value.first.return_value = None
        case = SimpleNamespace(case_numbers=mock_qs)
        result = _resolve_original_case_number(case)
        assert result == ""


# ---------------------------------------------------------------------------
# _build_material_slot_signals
# ---------------------------------------------------------------------------
class TestBuildMaterialSlotSignals:
    def test_with_type_name_and_file(self):
        material = SimpleNamespace(
            type_name="起诉状",
            type=SimpleNamespace(name="民事起诉状"),
            source_attachment=None,
        )
        file_path = Path("/some/path/起诉状.pdf")
        primary, secondary = _build_material_slot_signals(material=material, file_path=file_path)
        assert any("起诉状" in s for s in primary)
        assert any("起诉状" in s for s in secondary)

    def test_with_attachment(self):
        att_file = SimpleNamespace(name="证据清单.pdf")
        att_log = SimpleNamespace(content="some log")
        attachment = SimpleNamespace(file=att_file, log=att_log)
        material = SimpleNamespace(
            type_name="证据",
            type=None,
            source_attachment=attachment,
        )
        file_path = Path("/some/path/file.pdf")
        primary, secondary = _build_material_slot_signals(material=material, file_path=file_path)
        assert any("证据" in s for s in primary)
        assert any("证据清单" in s for s in secondary)


# ---------------------------------------------------------------------------
# _match_slot
# ---------------------------------------------------------------------------
class TestMatchSlot:
    def test_civil_complaint(self):
        material = SimpleNamespace(
            type_name="民事起诉状",
            type=SimpleNamespace(name="起诉状"),
            source_attachment=None,
        )
        file_path = Path("/test/起诉状.pdf")
        slot = _match_slot(material=material, file_path=file_path, filing_type="civil")
        assert slot == "0"

    def test_default_slot(self):
        material = SimpleNamespace(
            type_name="未知材料",
            type=None,
            source_attachment=None,
        )
        file_path = Path("/test/random.pdf")
        slot = _match_slot(material=material, file_path=file_path, filing_type="civil")
        # Should return default or some slot
        assert isinstance(slot, str)

    def test_execution_apply_slot(self):
        material = SimpleNamespace(
            type_name="执行申请书",
            type=SimpleNamespace(name="申请执行"),
            source_attachment=None,
        )
        file_path = Path("/test/执行申请书.pdf")
        slot = _match_slot(material=material, file_path=file_path, filing_type="execution")
        assert slot == "0"


# ---------------------------------------------------------------------------
# _apply_execution_party_fallbacks
# ---------------------------------------------------------------------------
class TestApplyExecutionPartyFallbacks:
    def test_fallback_phone(self):
        plaintiffs = [
            {"client_type": "natural", "phone": "", "address": "北京市"},
        ]
        agents = [{"phone": "13800138000"}]
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == "13800138000"

    def test_no_fallback_needed(self):
        plaintiffs = [
            {"client_type": "natural", "phone": "13900139000", "address": "北京市"},
        ]
        agents = [{"phone": "13800138000"}]
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == "13900139000"

    def test_skip_legal_type(self):
        plaintiffs = [
            {"client_type": "legal", "phone": "", "address": ""},
        ]
        agents = [{"phone": "13800138000"}]
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == ""

    def test_invalid_agent_phone(self):
        plaintiffs = [
            {"client_type": "natural", "phone": "", "address": ""},
        ]
        agents = [{"phone": "invalid"}, {"phone": "13800138000"}]
        _apply_execution_party_fallbacks(plaintiffs=plaintiffs, agents=agents)
        assert plaintiffs[0]["phone"] == "13800138000"


# ---------------------------------------------------------------------------
# _update_session_task
# ---------------------------------------------------------------------------
class TestUpdateSessionTask:
    def test_none_session_id(self):
        # Should not raise
        _update_session_task(session_id=None, status="running")

    def test_update_with_result_and_error(self):
        # Verify parameters are accepted without error
        _update_session_task(session_id=None, status="running", error_message="err", result={"key": "val"}, set_started=False, set_finished=False)


# ---------------------------------------------------------------------------
# _infer_filing_type
# ---------------------------------------------------------------------------
class TestInferFilingType:
    def test_execution_by_status(self):
        party = SimpleNamespace(legal_status="applicant")
        case = SimpleNamespace(id=1, name="test", cause_of_action="")
        with patch("apps.cases.models.CaseMaterial.objects.filter") as mock_filter:
            mock_filter.return_value.values_list.return_value = []
            result = _infer_filing_type(case=case, parties=[party])
        assert result == "execution"

    def test_execution_by_cause(self):
        party = SimpleNamespace(legal_status="plaintiff")
        case = SimpleNamespace(id=1, name="申请执行案件", cause_of_action="申请执行")
        with patch("apps.cases.models.CaseMaterial.objects.filter") as mock_filter:
            mock_filter.return_value.values_list.return_value = []
            result = _infer_filing_type(case=case, parties=[party])
        assert result == "execution"

    def test_civil_default(self):
        party = SimpleNamespace(legal_status="plaintiff")
        case = SimpleNamespace(id=1, name="test case", cause_of_action="借款合同")
        with patch("apps.cases.models.CaseMaterial.objects.filter") as mock_filter:
            mock_filter.return_value.values_list.return_value = []
            result = _infer_filing_type(case=case, parties=[party])
        assert result == "civil"

    def test_execution_by_material_type(self):
        party = SimpleNamespace(legal_status="plaintiff")
        case = SimpleNamespace(id=1, name="test", cause_of_action="")
        with patch("apps.cases.models.CaseMaterial.objects.filter") as mock_filter:
            mock_filter.return_value.values_list.return_value = ["执行申请书"]
            result = _infer_filing_type(case=case, parties=[party])
        assert result == "execution"


# ---------------------------------------------------------------------------
# _build_party_payloads
# ---------------------------------------------------------------------------
class TestBuildPartyPayloads:
    def _make_natural_party(self, legal_status="plaintiff", **kwargs):
        client = SimpleNamespace(
            client_type="natural",
            name=kwargs.get("name", "张三"),
            address=kwargs.get("address", "北京市朝阳区"),
            phone=kwargs.get("phone", "13800138000"),
            id_number=kwargs.get("id_number", "110101199003071234"),
            legal_representative="",
            legal_representative_id_number="",
        )
        return SimpleNamespace(
            legal_status=legal_status,
            client=client,
        )

    def _make_legal_party(self, legal_status="defendant", **kwargs):
        client = SimpleNamespace(
            client_type="legal",
            name=kwargs.get("name", "某公司"),
            address=kwargs.get("address", "广州市天河区"),
            phone=kwargs.get("phone", "020-12345678"),
            id_number=kwargs.get("id_number", "91440101MA59TEST"),
            legal_representative=kwargs.get("legal_rep", "李四"),
            legal_representative_id_number=kwargs.get("legal_rep_id", "440101199001011234"),
        )
        return SimpleNamespace(
            legal_status=legal_status,
            client=client,
        )

    def test_plaintiff_natural(self):
        parties = [self._make_natural_party("plaintiff")]
        p, d, t = _build_party_payloads(parties)
        assert len(p) == 1
        assert len(d) == 0
        assert p[0]["name"] == "张三"

    def test_defendant_legal(self):
        parties = [self._make_legal_party("defendant")]
        p, d, t = _build_party_payloads(parties)
        assert len(d) == 1
        assert d[0]["uscc"] == "91440101MA59TEST"

    def test_third_party(self):
        parties = [self._make_natural_party("third")]
        p, d, t = _build_party_payloads(parties)
        assert len(t) == 1

    def test_mixed_parties(self):
        parties = [
            self._make_natural_party("plaintiff"),
            self._make_legal_party("defendant"),
            self._make_natural_party("third"),
        ]
        p, d, t = _build_party_payloads(parties)
        assert len(p) == 1
        assert len(d) == 1
        assert len(t) == 1
