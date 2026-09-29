"""document_analyzer + 共享分析降级阶梯 单元测试。

覆盖 2026-09 LLM 路由改造的新契约：
- analyze_document：LLM 不可用/输出不可解析 → 软失败（analysis=None），不抛异常
- 识别服务：同一文本只发一次 LLM 分析（分类与提取共享）
- 降级标记：LLM 失败时 RecognitionResult.degraded=True 且带可观测性字段
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from apps.document_recognition.services.data_classes import DocumentType
from apps.document_recognition.services.document_analyzer import (
    CourtDocumentAnalysis,
    DocumentAnalysisOutcome,
    analyze_document,
)
from apps.document_recognition.services.document_classifier import DocumentClassifier
from apps.document_recognition.services.info_extractor import InfoExtractor
from apps.document_recognition.services.recognition_service import CourtDocumentRecognitionService

# patch 点：recognition_service 内部延迟 import 的 analyze_document 源模块
ANALYZER_PATCH_TARGET = "apps.document_recognition.services.document_analyzer.analyze_document"


def _llm_returning(content: str) -> MagicMock:
    llm = MagicMock()
    llm.chat.return_value.content = content
    llm.chat.return_value.model = "kimi-2.6"
    llm.chat.return_value.backend = "openai_compatible"
    return llm


class TestAnalyzeDocument:
    def test_valid_output(self) -> None:
        llm = _llm_returning(
            '{"document_type": "summons", "case_number": "（2024）粤0604民初41257号", '
            '"court_time": "2024-06-15 09:30", "confidence": 0.9, "reason": "含开庭时间"}'
        )

        outcome = analyze_document("传票内容……", llm_service=llm)

        assert outcome.ok
        assert outcome.analysis is not None
        assert outcome.analysis.document_type == "summons"
        assert outcome.analysis.case_number == "（2024）粤0604民初41257号"
        assert outcome.model == "kimi-2.6"
        assert outcome.backend == "openai_compatible"
        assert outcome.latency_ms is not None

    def test_llm_unavailable_soft_fails(self) -> None:
        from apps.core.llm.exceptions import LLMNetworkError

        llm = MagicMock()
        llm.chat.side_effect = LLMNetworkError("refused")

        outcome = analyze_document("传票内容……", llm_service=llm)

        assert not outcome.ok
        assert outcome.analysis is None
        assert outcome.error == "llm_unavailable: LLMNetworkError"

    def test_unparseable_output_soft_fails(self) -> None:
        llm = _llm_returning("抱歉我无法输出JSON")

        outcome = analyze_document("传票内容……", llm_service=llm, max_attempts=2)

        assert not outcome.ok
        assert outcome.error == "unparseable_output"
        # 首次 + 1 次反馈重试
        assert llm.chat.call_count == 2

    def test_empty_text_no_llm_call(self) -> None:
        llm = MagicMock()
        outcome = analyze_document("   ", llm_service=llm)
        assert not outcome.ok
        assert outcome.error == "empty_text"
        llm.chat.assert_not_called()


class TestSharedAnalysisSingleCall:
    def test_classifier_and_extractor_share_one_llm_call(self) -> None:
        """分类与信息提取共用同一份分析结果：LLM 只被调用一次。"""
        llm = _llm_returning(
            '{"document_type": "summons", "case_number": null, "court_time": "2024-06-15 09:30", "confidence": 0.9}'
        )
        text = "定于2024年6月15日上午9:30开庭审理……"
        cache: dict[str, DocumentAnalysisOutcome] = {}

        def lookup(t: str) -> DocumentAnalysisOutcome:
            if t not in cache:
                cache[t] = analyze_document(t, llm_service=llm)
            return cache[t]

        classifier = DocumentClassifier(analysis_lookup=lookup)
        extractor = InfoExtractor(analysis_lookup=lookup)

        doc_type, _ = classifier.classify(text)
        info = extractor.extract_summons_info(text)

        assert doc_type == DocumentType.SUMMONS
        assert len(cache) == 1
        assert llm.chat.call_count == 1
        # 正则未命中时间时采用 LLM 时间
        assert info["court_time"] == datetime(2024, 6, 15, 9, 30)


class TestDegradedRecognition:
    def test_recognize_from_text_marks_degraded(self) -> None:
        """LLM 分析失败 → degraded=True，分类走关键词，无异常。"""
        failed = DocumentAnalysisOutcome(analysis=None, error="llm_unavailable: LLMNetworkError")
        svc = CourtDocumentRecognitionService()
        with patch(ANALYZER_PATCH_TARGET, return_value=failed):
            result = svc.recognize_document_from_text("传票：定于2024年6月15日开庭")

        assert result.degraded is True
        assert result.llm_model is None
        assert result.document_type == DocumentType.SUMMONS  # 关键词命中"传票"

    def test_recognize_from_text_observability_when_llm_ok(self) -> None:
        """LLM 分析成功 → 带模型、后端与耗时信息，不标记降级。"""
        analysis = CourtDocumentAnalysis(document_type="other", confidence=0.5)
        ok = DocumentAnalysisOutcome(analysis=analysis, model="kimi-2.6", backend="openai_compatible", latency_ms=1200)
        svc = CourtDocumentRecognitionService()
        with patch(ANALYZER_PATCH_TARGET, return_value=ok):
            result = svc.recognize_document_from_text("判决书内容")

        assert result.llm_model == "kimi-2.6"
        assert result.llm_backend == "openai_compatible"
        assert result.llm_latency_ms == 1200
        assert result.degraded is False
        assert result.document_type == DocumentType.OTHER

    def test_extract_summons_regex_wins_on_conflict(self) -> None:
        """正则与 LLM 案号冲突时以正则为准。"""
        analysis = CourtDocumentAnalysis(document_type="summons", case_number="（2024）京01民初999号", court_time=None)
        extractor = InfoExtractor(analysis_lookup=lambda text: DocumentAnalysisOutcome(analysis=analysis))

        info = extractor.extract_summons_info("（2024）粤0604民初123号 于2024年6月15日 9:30 开庭")

        assert info["case_number"] == "（2024）粤0604民初123号"
        assert isinstance(info["court_time"], datetime)
