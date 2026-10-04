"""InfoExtractor 单元测试 — 传票/执行裁定书信息提取（正则 + 共享分析交叉校验）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from apps.document_recognition.services.document_analyzer import CourtDocumentAnalysis, DocumentAnalysisOutcome
from apps.document_recognition.services.info_extractor import InfoExtractor

_SUMMONS_TEXT = "（2026）粤0604民初41257号传票：定于2026年3月15日上午9时30分在本院第一审判庭开庭审理。"
_EXECUTION_TEXT = "（2026）粤0604执保88号执行裁定书：冻结被申请人银行存款。"


def _outcome(analysis: CourtDocumentAnalysis | None) -> DocumentAnalysisOutcome:
    return DocumentAnalysisOutcome(analysis=analysis)


class TestSharedAnalysis:
    def test_no_lookup_returns_none(self) -> None:
        assert InfoExtractor()._shared_analysis("文本") is None

    def test_lookup_returns_analysis(self) -> None:
        analysis = CourtDocumentAnalysis(case_number="（2026）粤0604民初1号")
        extractor = InfoExtractor(analysis_lookup=lambda text: _outcome(analysis))
        assert extractor._shared_analysis("文本") is analysis

    def test_lookup_returning_none_outcome(self) -> None:
        extractor = InfoExtractor(analysis_lookup=lambda text: DocumentAnalysisOutcome(analysis=None))
        assert extractor._shared_analysis("文本") is None


class TestExtractSummonsInfo:
    def test_empty_text(self) -> None:
        result = InfoExtractor().extract_summons_info("")
        assert result == {"case_number": None, "court_time": None, "extraction_method": None}

    def test_regex_case_number_wins(self) -> None:
        analysis = CourtDocumentAnalysis(case_number="（2020）京01民初1号")
        extractor = InfoExtractor(analysis_lookup=lambda text: _outcome(analysis))
        result = extractor.extract_summons_info(_SUMMONS_TEXT)
        assert result["case_number"] == "（2026）粤0604民初41257号"

    def test_llm_case_number_when_regex_misses(self) -> None:
        analysis = CourtDocumentAnalysis(case_number="（2026）粤0604民初1号")
        extractor = InfoExtractor(analysis_lookup=lambda text: _outcome(analysis))
        result = extractor.extract_summons_info("传票正文无案号")
        assert result["case_number"] == "（2026）粤0604民初1号"

    def test_llm_null_case_number_ignored(self) -> None:
        analysis = CourtDocumentAnalysis(case_number="null")
        extractor = InfoExtractor(analysis_lookup=lambda text: _outcome(analysis))
        result = extractor.extract_summons_info("无案号文本")
        assert result["case_number"] is None

    def test_llm_datetime_used_when_no_regex_datetime(self) -> None:
        analysis = CourtDocumentAnalysis(case_number="（2026）粤0604民初1号", court_time="2026-03-15 09:30")
        extractor = InfoExtractor(analysis_lookup=lambda text: _outcome(analysis))
        result = extractor.extract_summons_info("无日期正文的传票（2026）粤0604民初1号")
        assert result["court_time"] == datetime(2026, 3, 15, 9, 30)
        assert result["extraction_method"] is not None and "ollama" in result["extraction_method"]

    def test_no_datetime_anywhere(self) -> None:
        result = InfoExtractor().extract_summons_info("（2026）粤0604民初1号传票")
        assert result["court_time"] is None
        assert result["extraction_method"] == "无法提取"

    def test_long_text_truncated_for_analysis(self) -> None:
        seen: dict[str, int] = {}

        def lookup(text: str) -> DocumentAnalysisOutcome:
            seen["len"] = len(text)
            return _outcome(CourtDocumentAnalysis(case_number="（2026）粤0604民初9号"))

        extractor = InfoExtractor(analysis_lookup=lookup)
        # 案号在 4000 字截断窗口之外 → 正则不可见，回退 LLM 结果
        result = extractor.extract_summons_info("长" * 5000 + "（2026）粤0604民初41257号")
        assert seen["len"] == 4000
        assert result["case_number"] == "（2026）粤0604民初9号"


class TestExtractExecutionInfo:
    def test_empty_text(self) -> None:
        result = InfoExtractor().extract_execution_info("")
        assert result == {"case_number": None, "preservation_deadline": None}

    def test_regex_case_number(self) -> None:
        result = InfoExtractor().extract_execution_info(_EXECUTION_TEXT)
        assert result["case_number"] == "（2026）粤0604执保88号"
        assert result["preservation_deadline"] is None

    def test_llm_case_number_when_regex_misses(self) -> None:
        analysis = CourtDocumentAnalysis(case_number="（2026）粤0604执保1号")
        extractor = InfoExtractor(analysis_lookup=lambda text: _outcome(analysis))
        result = extractor.extract_execution_info("执行裁定书正文")
        assert result["case_number"] == "（2026）粤0604执保1号"

    def test_llm_deadline_parsed(self) -> None:
        analysis = CourtDocumentAnalysis(case_number=None, court_time="2027-01-31")
        extractor = InfoExtractor(analysis_lookup=lambda text: _outcome(analysis))
        result = extractor.extract_execution_info("执行裁定书正文")
        assert result["preservation_deadline"] == datetime(2027, 1, 31)

    def test_regex_wins_over_llm_case_number(self) -> None:
        analysis = CourtDocumentAnalysis(case_number="（2020）沪01执保1号")
        extractor = InfoExtractor(analysis_lookup=lambda text: _outcome(analysis))
        result = extractor.extract_execution_info(_EXECUTION_TEXT)
        assert result["case_number"] == "（2026）粤0604执保88号"


class TestLegacyConstructorArgs:
    def test_compat_args_stored_without_db_access(self) -> None:
        extractor = InfoExtractor(ollama_model="qwen", ollama_base_url="http://localhost", llm_service=object())
        assert extractor.ollama_model == "qwen"
        assert extractor.ollama_base_url == "http://localhost"
