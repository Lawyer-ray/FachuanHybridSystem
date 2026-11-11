"""Tests for split_models (levenshtein, dataclasses) and segment_detector helpers."""

from __future__ import annotations

import pytest

from apps.pdf_splitting.services.split.split_models import (
    OCRPageResult,
    OCRRuntimeProfile,
    PageDescriptor,
    SegmentDraft,
    _levenshtein_distance,
)

# ---------------------------------------------------------------------------
# _levenshtein_distance
# ---------------------------------------------------------------------------


class TestLevenshteinDistance:
    def test_identical(self):
        assert _levenshtein_distance("abc", "abc") == 0

    def test_empty_vs_empty(self):
        assert _levenshtein_distance("", "") == 0

    def test_empty_vs_string(self):
        assert _levenshtein_distance("", "abc") == 3

    def test_single_substitution(self):
        assert _levenshtein_distance("abc", "axc") == 1

    def test_insertion(self):
        assert _levenshtein_distance("ac", "abc") == 1

    def test_deletion(self):
        assert _levenshtein_distance("abc", "ac") == 1

    def test_completely_different(self):
        assert _levenshtein_distance("abc", "xyz") == 3

    def test_longer_first(self):
        assert _levenshtein_distance("kitten", "sitting") == 3

    def test_single_char(self):
        assert _levenshtein_distance("a", "") == 1
        assert _levenshtein_distance("", "a") == 1


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


class TestDataclasses:
    def test_page_descriptor(self):
        pd = PageDescriptor(
            page_no=1,
            text="hello",
            normalized_text="hello",
            head_text="he",
            source_method="pdf",
            ocr_failed=False,
            top_candidates=[],
        )
        assert pd.page_no == 1

    def test_segment_draft(self):
        sd = SegmentDraft(
            order=1,
            page_start=1,
            page_end=5,
            segment_type="complaint",
            filename="test.pdf",
            confidence=0.9,
            source_method="pdf",
            review_flag="auto",
        )
        assert sd.confidence == 0.9

    def test_ocr_runtime_profile(self):
        profile = OCRRuntimeProfile(key="default", use_v5=True, dpi=300, workers=4)
        assert profile.dpi == 300

    def test_ocr_page_result(self):
        result = OCRPageResult(page_no=1, text="text", source_method="pdf", ocr_failed=False)
        assert result.ocr_failed is False


# ---------------------------------------------------------------------------
# SegmentDetector — pure methods
# ---------------------------------------------------------------------------


class TestSegmentDetectorNormalizeText:
    def test_basic(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        sd = SegmentDetector()
        assert sd.normalize_text("hello world") == "helloworld"

    def test_empty(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        sd = SegmentDetector()
        assert sd.normalize_text("") == ""


class TestSegmentDetectorContainsKeyword:
    def test_found(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        sd = SegmentDetector()
        assert sd.contains_keyword("this is a test", "test") is True

    def test_not_found(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        sd = SegmentDetector()
        assert sd.contains_keyword("this is a test", "missing") is False


class TestSegmentDetectorIsEffectiveText:
    def test_short(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        sd = SegmentDetector()
        assert sd.is_effective_text("short") is False

    def test_long(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        sd = SegmentDetector()
        assert sd.is_effective_text("this is a long enough text") is True


class TestSegmentDetectorFuzzyContainsKeyword:
    def test_exact_match(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        sd = SegmentDetector()
        found, coeff = sd.fuzzy_contains_keyword("this is a test", "test")
        assert found is True
        assert coeff == 1.0

    def test_no_match(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        sd = SegmentDetector()
        found, coeff = sd.fuzzy_contains_keyword("hello world", "xyz")
        assert found is False
        assert coeff == 0.0

    def test_empty_keyword(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        sd = SegmentDetector()
        found, coeff = sd.fuzzy_contains_keyword("hello", "")
        assert found is False
        assert coeff == 0.0

    def test_short_keyword_no_fuzzy(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        sd = SegmentDetector()
        found, coeff = sd.fuzzy_contains_keyword("hello", "xyz")
        assert found is False

    def test_fuzzy_match_medium_keyword(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        sd = SegmentDetector()
        # keyword "测试文本" (len 4) -> max_dist=1, "测试文" (len 3) is within edit distance 1
        found, coeff = sd.fuzzy_contains_keyword("这是测试文本的内容", "测试文本")
        assert found is True
        assert coeff == 1.0  # exact match via normalization

    def test_fuzzy_match_long_keyword(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        sd = SegmentDetector()
        # keyword "证据清单" (len 8 normalized) -> max_dist=2
        found, coeff = sd.fuzzy_contains_keyword("提交了证据清单明细", "证据清单")
        assert found is True
        assert coeff == 1.0


# ---------------------------------------------------------------------------
# classify_pdf_material：混合材料包的取字选路判定
# ---------------------------------------------------------------------------


class _FakePage:
    def __init__(self, text: str) -> None:
        self._text = text

    def get_text(self, _mode: str) -> str:
        return self._text


class _FakeDoc:
    """只暴露分类函数用到的两个成员，避免为判定去构造真实 PDF。"""

    def __init__(self, texts: list[str]) -> None:
        self._pages = [_FakePage(t) for t in texts]
        self.page_count = len(texts)
        self.loaded: list[int] = []

    def load_page(self, index: int) -> _FakePage:
        self.loaded.append(index)
        return self._pages[index]


def _effective(value: str) -> bool:
    """与 SegmentDetector.is_effective_text 同口径：去空白后 >= 12 字。"""
    return len("".join(value.split())) >= 12


class TestClassifyPdfMaterial:
    def test_all_pages_have_text_layer_is_digital(self) -> None:
        from apps.pdf_splitting.services.split.split_models import MATERIAL_KIND_DIGITAL_PDF, classify_pdf_material

        doc = _FakeDoc(["这是一份电子版判决书的正文内容"] * 5)
        assert classify_pdf_material(doc, is_effective_text=_effective) == MATERIAL_KIND_DIGITAL_PDF

    def test_no_page_has_text_layer_is_scanned(self) -> None:
        from apps.pdf_splitting.services.split.split_models import MATERIAL_KIND_SCANNED_PDF, classify_pdf_material

        # 真实扫描件：文本层为空（164 页全彩卷宗的实测形态）
        doc = _FakeDoc([""] * 5)
        assert classify_pdf_material(doc, is_effective_text=_effective) == MATERIAL_KIND_SCANNED_PDF

    def test_some_pages_text_some_blank_is_mixed(self) -> None:
        from apps.pdf_splitting.services.split.split_models import MATERIAL_KIND_MIXED_PDF, classify_pdf_material

        # 首=电子页，中/尾=扫描页：附件里夹扫描件的常态
        doc = _FakeDoc(["电子版封面与目录的正文内容", "", ""])
        assert classify_pdf_material(doc, is_effective_text=_effective) == MATERIAL_KIND_MIXED_PDF

    def test_only_samples_first_middle_last(self) -> None:
        from apps.pdf_splitting.services.split.split_models import classify_pdf_material

        # 判定只是选路，不能把整本扫一遍（那是把最贵的 IO 做两遍）
        doc = _FakeDoc(["正文内容够长的一页文字"] * 100)
        classify_pdf_material(doc, is_effective_text=_effective)
        assert doc.loaded == [0, 50, 99]

    def test_empty_document_is_scanned_not_crash(self) -> None:
        from apps.pdf_splitting.services.split.split_models import MATERIAL_KIND_SCANNED_PDF, classify_pdf_material

        assert classify_pdf_material(_FakeDoc([]), is_effective_text=_effective) == MATERIAL_KIND_SCANNED_PDF

    def test_single_page_document_dedupes_sample(self) -> None:
        from apps.pdf_splitting.services.split.split_models import MATERIAL_KIND_DIGITAL_PDF, classify_pdf_material

        doc = _FakeDoc(["只有一页但文字足够长的正文"])
        assert classify_pdf_material(doc, is_effective_text=_effective) == MATERIAL_KIND_DIGITAL_PDF
        assert doc.loaded == [0]

    def test_broken_page_does_not_abort_classification(self) -> None:
        from apps.pdf_splitting.services.split.split_models import MATERIAL_KIND_SCANNED_PDF, classify_pdf_material

        class _Boom(_FakeDoc):
            def load_page(self, index: int):  # type: ignore[no-untyped-def]
                if index == 0:
                    raise RuntimeError("页损坏")
                return super().load_page(index)

        # 首页读不出来 → 其余全是空 → 按扫描件处理，不抛异常拖垮整份解析
        got = classify_pdf_material(_Boom(["", "", ""]), is_effective_text=_effective)
        assert got == MATERIAL_KIND_SCANNED_PDF
