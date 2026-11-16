"""
Tests for apps.pdf_splitting.services — PDF 分割服务
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# ============================================================
# TemplateRegistry 测试
# ============================================================


class TestTemplateRegistry:
    """模板注册表测试"""

    def test_get_template_definition_known_key(self) -> None:
        from apps.pdf_splitting.services.template_registry import get_template_definition

        template = get_template_definition("filing_materials_v1")
        assert template.key == "filing_materials_v1"
        assert len(template.rules) > 0

    def test_get_template_definition_unknown_defaults(self) -> None:
        from apps.pdf_splitting.services.template_registry import get_template_definition

        template = get_template_definition("nonexistent")
        assert template.key == "filing_materials_v1"  # fallback

    def test_get_segment_label_known_type(self) -> None:
        from apps.pdf_splitting.services.template_registry import get_segment_label

        label = get_segment_label("complaint")
        assert label  # should return some label

    def test_get_segment_label_unknown(self) -> None:
        from apps.pdf_splitting.services.template_registry import get_segment_label

        label = get_segment_label("nonexistent_type_xyz")
        assert label == "nonexistent_type_xyz"

    def test_get_default_filename_known(self) -> None:
        from apps.pdf_splitting.services.template_registry import get_default_filename

        filename = get_default_filename("complaint")
        assert filename  # should return something

    def test_get_default_filename_unknown(self) -> None:
        from apps.pdf_splitting.services.template_registry import get_default_filename

        filename = get_default_filename("nonexistent")
        assert filename == "未识别材料"

    def test_filing_materials_rules_count(self) -> None:
        from apps.pdf_splitting.services.template_registry import FILING_MATERIALS_V1

        # 29 = 立案材料类 7 条 + 贷款/利息/买卖类 7 条（借款合同、放款凭证、银行流水、
        # 利息计算表、送货单、收货单、发票）+ 诉讼程序类 9 条（判决书、裁定书、
        # 调解书、上诉状、答辩状、再审申请书、执行申请书、庭审笔录、代理词）
        # + 银行信贷档案类 6 条（贷款申请、抵押估价、抵押登记、不良监控、
        # 贷后检查、催收记录）。
        #
        # 后 9 条是补的：拆包是「收到什么拆什么」，不能只认一审起诉的那几类。
        # 补之前二审答辩包整包 5 段只认出 1 段，其余全落 unrecognized。
        # 此断言用于防止规则被误删。
        #
        # +5 = 民间借贷高频类（借条、转账回单、聊天记录、和解协议、保证合同）：
        # 补之前模型只能硬塞语义不对的既有键（转账回单→放款凭证）或落 unrecognized。
        assert len(FILING_MATERIALS_V1.rules) == 34

    def test_appeal_template_has_own_rules(self) -> None:
        """二审必须有独立模板，不能靠往立案模板里塞类型。

        LLM 的 prompt 会列出「本模板可用的 type 键名」，system prompt 也会
        按模板给出场景身份。若把判决书/上诉状塞进「立案材料模板」，
        模型会判断它们不属于立案材料而一律回 other（实测 5 段只认 1 段）。
        """
        from apps.pdf_splitting.models import PdfSplitSegmentType as T
        from apps.pdf_splitting.services.template_registry import _REGISTRY, get_template_definition

        assert "appeal_defense_v1" in _REGISTRY
        tpl = get_template_definition("appeal_defense_v1")
        types = {r.segment_type for r in tpl.rules}
        assert {T.JUDGMENT, T.APPEAL_PETITION, T.DEFENSE_STATEMENT} <= types
        # 二审模板里不该有起诉状 —— 一审已经起诉过了
        assert T.COMPLAINT not in types

    def test_segment_rule_has_keywords(self) -> None:
        from apps.pdf_splitting.services.template_registry import FILING_MATERIALS_V1

        complaint_rule = FILING_MATERIALS_V1.rules[0]
        assert complaint_rule.segment_type == "complaint"
        assert len(complaint_rule.strong_keywords) > 0
        assert "民事起诉状" in complaint_rule.strong_keywords

    def test_segment_rule_has_negative_keywords(self) -> None:
        from apps.pdf_splitting.services.template_registry import FILING_MATERIALS_V1

        complaint_rule = FILING_MATERIALS_V1.rules[0]
        assert len(complaint_rule.negative_keywords) > 0


# ============================================================
# SplitModels 测试
# ============================================================


class TestSplitModels:
    """PDF 分割数据模型测试"""

    def test_page_descriptor(self) -> None:
        from apps.pdf_splitting.services.split.split_models import PageDescriptor

        desc = PageDescriptor(
            page_no=1,
            text="起诉状内容",
            normalized_text="起诉状内容",
            head_text="起诉状",
            source_method="pdf_text",
            ocr_failed=False,
            top_candidates=[],
        )
        assert desc.page_no == 1
        assert desc.text == "起诉状内容"

    def test_segment_draft(self) -> None:
        from apps.pdf_splitting.services.split.split_models import SegmentDraft

        draft = SegmentDraft(
            order=1,
            page_start=1,
            page_end=5,
            segment_type="complaint",
            filename="起诉状.pdf",
            confidence=0.95,
            source_method="keyword",
            review_flag="ok",
        )
        assert draft.order == 1
        assert draft.page_start == 1
        assert draft.page_end == 5
        assert draft.confidence == 0.95

    def test_ocr_runtime_profile(self) -> None:
        from apps.pdf_splitting.services.split.split_models import OCRRuntimeProfile

        profile = OCRRuntimeProfile(key="test", use_v5=True, dpi=300, workers=4)
        assert profile.key == "test"
        assert profile.use_v5 is True

    def test_ocr_page_result(self) -> None:
        from apps.pdf_splitting.services.split.split_models import OCRPageResult

        result = OCRPageResult(page_no=1, text="OCR text", source_method="ocr", ocr_failed=False)
        assert result.page_no == 1
        assert result.ocr_failed is False

    def test_levenshtein_distance(self) -> None:
        from apps.pdf_splitting.services.split.split_models import _levenshtein_distance

        assert _levenshtein_distance("kitten", "sitting") == 3
        assert _levenshtein_distance("", "abc") == 3
        assert _levenshtein_distance("abc", "abc") == 0
        assert _levenshtein_distance("abc", "") == 3


# ============================================================
# SegmentTemplateRule frozen dataclass 测试
# ============================================================


class TestSegmentTemplateRule:
    """SegmentTemplateRule 测试"""

    def test_rule_basic(self) -> None:
        from apps.pdf_splitting.services.template_registry import SegmentTemplateRule

        rule = SegmentTemplateRule(
            segment_type="test",
            label="Test",
            default_filename="test.pdf",
            strong_keywords=("keyword1",),
        )
        assert rule.segment_type == "test"
        assert rule.weak_keywords == ()
        assert rule.negative_keywords == ()

    def test_rule_frozen(self) -> None:
        from apps.pdf_splitting.services.template_registry import SegmentTemplateRule

        rule = SegmentTemplateRule(
            segment_type="test",
            label="Test",
            default_filename="test.pdf",
            strong_keywords=("kw",),
        )
        with pytest.raises(AttributeError):
            rule.segment_type = "changed"


# ---------------------------------------------------------------------------
# SegmentDetector extended tests
# ---------------------------------------------------------------------------


class TestSegmentDetectorExtended:
    def _make_detector(self):
        from apps.pdf_splitting.services.split.segment_detector import SegmentDetector

        return SegmentDetector()

    def test_normalize_text(self):
        detector = self._make_detector()
        result = detector.normalize_text("  hello  world  ")
        assert result == "helloworld" or "hello" in result

    def test_contains_keyword(self):
        detector = self._make_detector()
        assert detector.contains_keyword("这是一份起诉状", "起诉状") is True
        assert detector.contains_keyword("普通文本", "起诉状") is False

    def test_fuzzy_contains_keyword_exact(self):
        detector = self._make_detector()
        hit, decay = detector.fuzzy_contains_keyword("起诉状内容", "起诉状")
        assert hit is True
        assert decay == 1.0

    def test_fuzzy_contains_keyword_short_no_fuzzy(self):
        detector = self._make_detector()
        # Short keywords (<=3 chars) only do exact match
        hit, decay = detector.fuzzy_contains_keyword("起诉", "起诉")
        assert hit is True  # exact match works

    def test_is_effective_text_true(self):
        detector = self._make_detector()
        assert detector.is_effective_text("这是一段足够长的文本内容") is True

    def test_is_effective_text_false(self):
        detector = self._make_detector()
        assert detector.is_effective_text("短") is False

    def test_fill_unrecognized_gaps(self):
        from apps.pdf_splitting.models import PdfSplitReviewFlag, PdfSplitSegmentType
        from apps.pdf_splitting.services.split.split_models import SegmentDraft

        detector = self._make_detector()
        segments = [
            SegmentDraft(
                order=1,
                page_start=3,
                page_end=5,
                segment_type=PdfSplitSegmentType.COMPLAINT,
                filename="test.pdf",
                confidence=0.8,
                source_method="rule",
                review_flag=PdfSplitReviewFlag.NORMAL,
            )
        ]
        filled = detector.fill_unrecognized_gaps(segments=segments, total_pages=10)
        assert len(filled) == 3  # gap before + segment + gap after
        assert filled[0].page_start == 1
        assert filled[0].page_end == 2
        assert filled[-1].page_start == 6
        assert filled[-1].page_end == 10

    def test_merge_adjacent_pack_segments(self):
        from apps.pdf_splitting.models import PdfSplitReviewFlag, PdfSplitSegmentType
        from apps.pdf_splitting.services.split.split_models import SegmentDraft

        detector = self._make_detector()
        segments = [
            SegmentDraft(
                order=1,
                page_start=1,
                page_end=2,
                segment_type=PdfSplitSegmentType.PARTY_IDENTITY,
                filename="a.pdf",
                confidence=0.8,
                source_method="rule",
                review_flag=PdfSplitReviewFlag.NORMAL,
            ),
            SegmentDraft(
                order=2,
                page_start=3,
                page_end=4,
                segment_type=PdfSplitSegmentType.PARTY_IDENTITY,
                filename="b.pdf",
                confidence=0.9,
                source_method="rule",
                review_flag=PdfSplitReviewFlag.NORMAL,
            ),
        ]
        merged = detector._merge_adjacent_pack_segments(segments)
        assert len(merged) == 1
        assert merged[0].page_start == 1
        assert merged[0].page_end == 4

    def test_merge_different_types_no_merge(self):
        from apps.pdf_splitting.models import PdfSplitReviewFlag, PdfSplitSegmentType
        from apps.pdf_splitting.services.split.split_models import SegmentDraft

        detector = self._make_detector()
        segments = [
            SegmentDraft(
                order=1,
                page_start=1,
                page_end=2,
                segment_type=PdfSplitSegmentType.PARTY_IDENTITY,
                filename="a.pdf",
                confidence=0.8,
                source_method="rule",
                review_flag=PdfSplitReviewFlag.NORMAL,
            ),
            SegmentDraft(
                order=2,
                page_start=3,
                page_end=4,
                segment_type=PdfSplitSegmentType.COMPLAINT,
                filename="b.pdf",
                confidence=0.9,
                source_method="rule",
                review_flag=PdfSplitReviewFlag.NORMAL,
            ),
        ]
        merged = detector._merge_adjacent_pack_segments(segments)
        assert len(merged) == 2


class TestPdfSplitJobServiceNormalize:
    def _make_service(self):
        from apps.pdf_splitting.services.job_service import PdfSplitJobService

        return PdfSplitJobService()

    def test_normalize_split_mode_valid(self):
        svc = self._make_service()
        assert svc._normalize_split_mode("content_analysis") == "content_analysis"

    def test_normalize_split_mode_invalid(self):
        svc = self._make_service()
        assert svc._normalize_split_mode("invalid") == "content_analysis"

    def test_normalize_split_mode_none(self):
        svc = self._make_service()
        assert svc._normalize_split_mode(None) == "content_analysis"

    def test_normalize_ocr_profile_valid(self):
        svc = self._make_service()
        assert svc._normalize_ocr_profile("balanced") == "balanced"

    def test_normalize_ocr_profile_invalid(self):
        svc = self._make_service()
        assert svc._normalize_ocr_profile("invalid") == "balanced"

    def test_is_absolute_path_unix(self):
        svc = self._make_service()
        assert svc._is_absolute_path("/tmp/test.pdf") is True
        assert svc._is_absolute_path("relative/test.pdf") is False


class TestBboxBackendFromActualEngine:
    """两阶段任务的坐标系来源必须是**实际引擎**，不是任务上的平台偏好。

    真 bug：``job.cloud_backend="auto"`` 时 ``resolve_bbox_unit("auto")`` 返回 unknown，
    ``build_positioned_blocks`` 直接返回 []——两阶段 + auto 的任务绿框恒空，
    而单任务入口用的是取字 summary 里的实际 ocr_provider。
    """

    def _pages(self, source_method: str) -> list:
        from apps.pdf_splitting.services.split.split_models import PageDescriptor

        return [
            PageDescriptor(
                page_no=1,
                text="银行流水交易明细",
                normalized_text="银行流水交易明细",
                head_text="银行流水交易明细",
                source_method=source_method,
                ocr_failed=False,
                top_candidates=[],
                layout={
                    "page_no": 1,
                    "blocks": [{"type": "text", "text": "银行流水交易明细", "bbox": [10, 10, 500, 60]}],
                },
            )
        ]

    def test_取字summary里的实际平台优先(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.pdf_splitting.services.split import two_stage
        from apps.pdf_splitting.services.split.service import PdfSplitService

        monkeypatch.setattr(two_stage, "load_extract_summary", lambda storage: {"ocr_provider": "textin"})

        backend = PdfSplitService()._bbox_backend(job_id="job-1", storage=MagicMock(), pages=self._pages("mineru_ocr"))

        assert backend == "textin"

    def test_summary缺失时按页来源推断(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.pdf_splitting.services.split import two_stage
        from apps.pdf_splitting.services.split.service import PdfSplitService

        monkeypatch.setattr(two_stage, "load_extract_summary", lambda storage: {})

        backend = PdfSplitService()._bbox_backend(job_id="job-1", storage=MagicMock(), pages=self._pages("mineru_ocr"))

        assert backend == "mineru"

    def test_summary写着auto也不退回auto(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.pdf_splitting.services.split import two_stage
        from apps.pdf_splitting.services.split.service import PdfSplitService

        monkeypatch.setattr(two_stage, "load_extract_summary", lambda storage: {"ocr_provider": "auto"})

        backend = PdfSplitService()._bbox_backend(job_id="job-1", storage=MagicMock(), pages=self._pages("textin_ocr"))

        assert backend == "textin"

    def test_多平台混用取页数最多的(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.pdf_splitting.services.split import two_stage
        from apps.pdf_splitting.services.split.service import PdfSplitService

        monkeypatch.setattr(two_stage, "load_extract_summary", lambda storage: {})
        pages = self._pages("mineru_ocr") + self._pages("textin_ocr") + self._pages("textin_ocr")

        assert PdfSplitService()._bbox_backend(job_id="job-1", storage=MagicMock(), pages=pages) == "textin"

    def test_纯本地取字报local且无版面画不出框(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.pdf_splitting.services.split import two_stage
        from apps.pdf_splitting.services.split.markdown_builder import build_segments_markdown
        from apps.pdf_splitting.services.split.service import PdfSplitService
        from apps.pdf_splitting.services.split.split_models import SegmentDraft

        monkeypatch.setattr(two_stage, "load_extract_summary", lambda storage: {"ocr_provider": "local"})
        pages = self._pages("ocr")

        backend = PdfSplitService()._bbox_backend(job_id="job-1", storage=MagicMock(), pages=pages)

        # 如实报 local，不冒充云端平台
        assert backend == "local"
        draft = SegmentDraft(
            order=0,
            page_start=1,
            page_end=1,
            segment_type="other",
            filename="材料.pdf",
            confidence=0.9,
            source_method="llm",
            review_flag="normal",
        )
        # 真没有版面的本地引擎（逐行文本、无坐标）：画不出框，也不编坐标
        pages[0].layout = None
        assert build_segments_markdown([draft], pages, bbox_backend=backend)[0]["positioned"] == []

    def test_vl兜底页的版面按千分比画得出框(self) -> None:
        """兜底路径实为 VL API，版面统一写成 1000×1000 千分比（ocr_handler._VL_LAYOUT_SIDE）。

        把 local 一律当 unknown 会让这批刚拿到的坐标被整批丢掉——P2-5 的收益归零。
        """
        from apps.pdf_splitting.services.split.markdown_builder import build_segments_markdown
        from apps.pdf_splitting.services.split.split_models import PageDescriptor, SegmentDraft

        page = PageDescriptor(
            page_no=1,
            text="银行流水交易明细",
            normalized_text="银行流水交易明细",
            head_text="银行流水交易明细",
            source_method="ocr",
            ocr_failed=False,
            top_candidates=[],
            layout={
                "page_no": 1,
                "width": 1000,
                "height": 1000,
                "blocks": [{"type": "text", "text": "银行流水交易明细", "bbox": [100, 100, 600, 200]}],
            },
        )
        draft = SegmentDraft(
            order=0,
            page_start=1,
            page_end=1,
            segment_type="bank_statement",
            filename="银行流水.pdf",
            confidence=0.9,
            source_method="llm",
            review_flag="normal",
        )
        positioned = build_segments_markdown([draft], [page], bbox_backend="local")[0]["positioned"]
        assert positioned
        assert positioned[0]["rect"]["x"] == 0.1
        assert positioned[0]["rect"]["w"] == 0.5

    def test_auto确实画不出框而实际平台能(self) -> None:
        from apps.pdf_splitting.services.split.markdown_builder import build_segments_markdown
        from apps.pdf_splitting.services.split.split_models import SegmentDraft

        draft = SegmentDraft(
            order=0,
            page_start=1,
            page_end=1,
            segment_type="bank_statement",
            filename="银行流水.pdf",
            confidence=0.9,
            source_method="llm",
            review_flag="normal",
        )
        pages = self._pages("mineru_ocr")

        assert build_segments_markdown([draft], pages, bbox_backend="auto")[0]["positioned"] == []
        assert build_segments_markdown([draft], pages, bbox_backend="mineru")[0]["positioned"]
