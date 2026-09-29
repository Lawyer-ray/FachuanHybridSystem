"""recognition_service._build_binding 新分支 / RecognitionResponse 序列化 / 通知文案 —
多日期人工确认改造的新增行为测试。全部无 DB。
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

from apps.document_recognition.services.data_classes import (
    BindingResult,
    DocumentType,
    RecognitionResponse,
    RecognitionResult,
)
from apps.document_recognition.services.notification_service import DocumentRecognitionNotificationService
from apps.document_recognition.services.recognition_service import CourtDocumentRecognitionService


def _make_service(**overrides):
    return CourtDocumentRecognitionService(
        text_extraction=overrides.get("text_extraction", MagicMock()),
        classifier=overrides.get("classifier", MagicMock()),
        extractor=overrides.get("extractor", MagicMock()),
        binding_service=overrides.get("binding_service", MagicMock()),
        document_renamer=overrides.get("document_renamer", MagicMock()),
        matching_service=overrides.get("matching_service", MagicMock()),
    )


# ---------------------------------------------------------------------------
# _build_binding：prebound / 无案号 / 未命中 / 命中
# ---------------------------------------------------------------------------


class TestBuildBindingPrebound:
    def test_prebound_log_returns_success_without_rename_or_bind(self):
        """管线预绑定（法院短信入口）：直接成功，不重命名、不建日志、不调绑定服务。"""
        svc = _make_service()
        svc.binding_service.case_service.get_case_by_id_internal.return_value = MagicMock(name_x="n")
        svc._rename_document = MagicMock(return_value="/tmp/should-not-happen.pdf")

        binding, renamed = svc._build_binding(
            DocumentType.SUMMONS,
            "（2024）京01民初123号",
            "/tmp/test.pdf",
            "text",
            None,
            prebound_case_id=3,
            prebound_case_log_id=30,
        )

        assert binding.success is True
        assert binding.case_id == 3
        assert binding.case_log_id == 30
        assert "法院短信" in binding.message
        assert renamed == "/tmp/test.pdf"
        svc._rename_document.assert_not_called()
        svc.matching_service.auto_match.assert_not_called()
        svc.binding_service.bind_document_to_case.assert_not_called()

    def test_prebound_without_case_id_keeps_empty_name(self):
        svc = _make_service()

        binding, _renamed = svc._build_binding(
            DocumentType.OTHER, None, "/tmp/test.pdf", "text", None, prebound_case_log_id=77
        )

        assert binding.success is True
        assert binding.case_id is None
        assert binding.case_name == ""
        assert binding.case_log_id == 77


class TestBuildBindingBranches:
    def test_no_case_number_returns_case_number_not_found(self):
        svc = _make_service()

        binding, renamed = svc._build_binding(DocumentType.SUMMONS, None, "/tmp/test.pdf", "text", None)

        assert binding.success is False
        assert binding.error_code == "CASE_NUMBER_NOT_FOUND"
        assert renamed == "/tmp/test.pdf"

    def test_auto_match_miss_returns_pending_manual_binding(self):
        svc = _make_service()
        svc.matching_service.auto_match.return_value = None

        binding, renamed = svc._build_binding(
            DocumentType.SUMMONS, "（2024）京01民初123号", "/tmp/test.pdf", "text", None
        )

        assert binding.success is False
        assert binding.error_code == "PENDING_MANUAL_BINDING"
        assert "手动选择案件" in binding.message
        assert renamed == "/tmp/test.pdf"

    def test_auto_match_hit_invokes_rename_and_bind(self):
        svc = _make_service()
        svc.matching_service.auto_match.return_value = (8, "匹配案")
        svc._rename_document = MagicMock(return_value="/tmp/renamed.pdf")
        svc.binding_service.format_log_content.return_value = "log"
        svc.binding_service.bind_document_to_case.return_value = BindingResult.success_result(
            case_id=8, case_name="匹配案", case_log_id=88
        )

        binding, renamed = svc._build_binding(
            DocumentType.EXECUTION_RULING, "（2024）京01执123号", "/tmp/test.pdf", "text", None, date_count=4
        )

        assert binding.success is True
        assert renamed == "/tmp/renamed.pdf"
        rename_kwargs = svc._rename_document.call_args[1]
        assert rename_kwargs["case_name"] == "匹配案"
        fmt_kwargs = svc.binding_service.format_log_content.call_args[1]
        assert fmt_kwargs["date_count"] == 4
        assert fmt_kwargs["case_number"] == "（2024）京01执123号"
        bind_kwargs = svc.binding_service.bind_document_to_case.call_args[1]
        assert bind_kwargs["case_id"] == 8
        assert bind_kwargs["file_path"] == "/tmp/renamed.pdf"


# ---------------------------------------------------------------------------
# recognize_document：date_candidates / party_names / key_time 兜底
# ---------------------------------------------------------------------------


class TestRecognizeDocumentDateCandidates:
    def _ext_result(self, text: str) -> MagicMock:
        ext_result = MagicMock()
        ext_result.success = True
        ext_result.text = text
        ext_result.extraction_method = "pdf_direct"
        return ext_result

    def test_key_time_falls_back_to_first_candidate(self):
        """extractor 未取到 key_time 时，用 candidates[0] 的 due_at 兜底。"""
        svc = _make_service()
        svc.text_extraction.extract_text.return_value = self._ext_result("传票内容")
        svc.classifier.classify.return_value = (DocumentType.SUMMONS, 0.9)
        svc.extractor.extract_summons_info.return_value = {"case_number": "123", "court_time": None}
        svc.matching_service.auto_match.return_value = None
        svc._build_date_candidates = MagicMock(
            return_value=[
                {
                    "due_at": "2026-10-15T09:30:00",
                    "reminder_type": "hearing",
                    "context_text": "开庭",
                    "source": "regex",
                    "confidence": 0.85,
                },
                {
                    "due_at": "2026-11-01T10:00:00",
                    "reminder_type": "evidence_deadline",
                    "context_text": "举证",
                    "source": "llm",
                    "confidence": 0.7,
                },
            ]
        )

        response = svc.recognize_document("/tmp/test.pdf")

        from django.utils.timezone import make_aware

        assert response.recognition.key_time == make_aware(datetime(2026, 10, 15, 9, 30))
        assert len(response.date_candidates) == 2
        assert response.date_candidates[0]["reminder_type"] == "hearing"
        # 绑定失败但日期候选仍透出（转人工后律师可继续确认日期）
        assert response.binding.error_code == "PENDING_MANUAL_BINDING"

    def test_party_names_from_cached_analysis(self):
        """party_names 来自共享 LLM 分析缓存（去空白）。"""
        from apps.document_recognition.services.document_analyzer import CourtDocumentAnalysis, DocumentAnalysisOutcome

        text = "张三与李四纠纷传票"
        analysis = CourtDocumentAnalysis(document_type="summons", party_names=["张三", " 李四 ", ""])
        svc = _make_service()
        svc.text_extraction.extract_text.return_value = self._ext_result(text)
        svc.classifier.classify.return_value = (DocumentType.SUMMONS, 0.9)
        svc.extractor.extract_summons_info.return_value = {"case_number": None, "court_time": None}
        svc.matching_service.auto_match.return_value = None
        svc._analysis_cache[text] = DocumentAnalysisOutcome(analysis=analysis)
        svc._analysis_attempted = True

        response = svc.recognize_document("/tmp/test.pdf")

        assert response.party_names == ["张三", "李四"]
        # 分析缓存透出降级可观测性
        assert response.recognition.degraded is False

    def test_no_candidates_keeps_key_time_none(self):
        svc = _make_service()
        svc.text_extraction.extract_text.return_value = self._ext_result("传票内容")
        svc.classifier.classify.return_value = (DocumentType.SUMMONS, 0.9)
        svc.extractor.extract_summons_info.return_value = {"case_number": None, "court_time": None}
        svc.matching_service.auto_match.return_value = None
        svc._build_date_candidates = MagicMock(return_value=[])

        response = svc.recognize_document("/tmp/test.pdf")

        assert response.recognition.key_time is None
        assert response.date_candidates == []
        assert response.party_names == []


# ---------------------------------------------------------------------------
# RecognitionResponse 序列化往返（date_candidates / party_names）
# ---------------------------------------------------------------------------


class TestRecognitionResponseRoundTrip:
    def _response(self) -> RecognitionResponse:
        recognition = RecognitionResult(
            document_type=DocumentType.SUMMONS,
            case_number="（2024）京01民初123号",
            key_time=datetime(2026, 10, 15, 9, 30),
            raw_text="text",
            confidence=0.9,
            extraction_method="pdf_direct",
        )
        binding = BindingResult.success_result(case_id=1, case_name="案", case_log_id=10)
        return RecognitionResponse(
            recognition=recognition,
            binding=binding,
            file_path="/tmp/f.pdf",
            date_candidates=[
                {
                    "due_at": "2026-10-15T09:30:00",
                    "reminder_type": "hearing",
                    "context_text": "开庭",
                    "source": "merged",
                    "confidence": 0.85,
                }
            ],
            party_names=["张三", "李四"],
        )

    def test_to_dict_contains_new_fields(self):
        payload = self._response().to_dict()

        assert payload["date_candidates"][0]["reminder_type"] == "hearing"
        assert payload["date_candidates"][0]["source"] == "merged"
        assert payload["party_names"] == ["张三", "李四"]

    def test_round_trip_preserves_new_fields(self):
        restored = RecognitionResponse.from_dict(self._response().to_dict())

        assert restored.date_candidates == self._response().date_candidates
        assert restored.party_names == ["张三", "李四"]

    def test_defaults_for_new_fields(self):
        recognition = RecognitionResult(
            document_type=DocumentType.OTHER,
            case_number=None,
            key_time=None,
            raw_text="",
            confidence=0.0,
            extraction_method="",
        )
        resp = RecognitionResponse(recognition=recognition, binding=None, file_path="/f")

        assert resp.date_candidates == []
        assert resp.party_names == []
        restored = RecognitionResponse.from_dict(resp.to_dict())
        assert restored.date_candidates == []
        assert restored.party_names == []


# ---------------------------------------------------------------------------
# 通知文案：date_count
# ---------------------------------------------------------------------------


class TestNotificationDateCount:
    def setup_method(self):
        self.svc = DocumentRecognitionNotificationService()

    def test_date_count_positive_uses_pending_confirm_wording(self):
        msg = self.svc.build_notification_message(
            document_type="summons",
            case_number="（2024）京01民初123号",
            key_time=datetime(2026, 10, 15, 9, 30),
            case_name="张三诉李四",
            date_count=3,
        )
        assert "已识别 3 个关键日期，待律师确认后写入重要日期提醒" in msg
        # 不再出现关键时间行，避免暗示提醒已写入
        assert "关键时间" not in msg

    def test_date_count_zero_falls_back_to_key_time_line(self):
        msg = self.svc.build_notification_message(
            document_type="execution",
            case_number=None,
            key_time=datetime(2026, 12, 31),
            case_name="王五案",
            date_count=0,
        )
        assert "关键时间：2026年12月31日 00:00" in msg
        assert "待律师确认" not in msg

    def test_date_count_zero_without_key_time_has_no_date_line(self):
        msg = self.svc.build_notification_message(
            document_type="other",
            case_number=None,
            key_time=None,
            case_name="测试案",
        )
        assert "关键时间" not in msg
        assert "待律师确认" not in msg

    def test_send_notification_passes_date_count_through(self):
        chat_service = MagicMock()
        chat = MagicMock()
        chat.chat_id = "chat_1"
        chat_service.get_or_create_chat.return_value = chat
        send_result = MagicMock()
        send_result.success = True
        send_result.message = "文件发送成功"
        chat_service.send_document_notification.return_value = send_result

        svc = DocumentRecognitionNotificationService(case_chat_service=chat_service)
        svc.build_notification_message = MagicMock(return_value="msg")  # type: ignore[method-assign]

        result = svc.send_notification(
            case_id=1,
            document_type="summons",
            case_number=None,
            key_time=None,
            file_path="/tmp/f.pdf",
            case_name="案",
            date_count=5,
        )

        assert result.success is True
        build_kwargs = svc.build_notification_message.call_args[1]
        assert build_kwargs["date_count"] == 5
