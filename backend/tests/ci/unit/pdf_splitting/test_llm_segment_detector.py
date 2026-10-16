"""Tests for pdf_splitting LLM 分段（方案二）：prompt 构造 / JSON 解析校验 / 规则引擎降级。"""

from __future__ import annotations

from typing import Any

import pytest

from apps.pdf_splitting.models import PdfSplitReviewFlag, PdfSplitSegmentType
from apps.pdf_splitting.services.split.llm_segment_detector import (
    LLMSegmentDetector,
    build_page_digests,
    build_user_prompt,
    parse_llm_segments,
)
from apps.pdf_splitting.services.split.service import PdfSplitService
from apps.pdf_splitting.services.split.split_models import PageDescriptor

TEMPLATE_KEY = "filing_materials_v1"


def _page(
    page_no: int,
    text: str = "",
    *,
    ocr_failed: bool = False,
    layout_title: str = "",
    top_candidates: list[dict[str, Any]] | None = None,
) -> PageDescriptor:
    return PageDescriptor(
        page_no=page_no,
        text=text,
        normalized_text=text,
        head_text=text[:240],
        source_method="ocr" if text else "ocr_failed",
        ocr_failed=ocr_failed,
        top_candidates=top_candidates or [],
        layout=None,
        layout_title=layout_title,
    )


def _seg_json(
    page_start: int,
    page_end: int,
    seg_type: str = "complaint",
    label: str = "",
    confidence: float | None = 0.9,
) -> str:
    item = f'{{"page_start": {page_start}, "page_end": {page_end}, "type": "{seg_type}", "label": "{label}"'
    if confidence is not None:
        item += f', "confidence": {confidence}'
    return item + "}"


class _StubLLM:
    def __init__(self, content: str = "") -> None:
        self.content = content
        self.calls: list[dict[str, Any]] = []

    def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> _StubLLM:
        self.calls.append({"messages": messages, **kwargs})
        return self


class _RaisingDetector:
    def detect(self, pages: list[PageDescriptor], *, template_key: str) -> list[Any]:
        raise RuntimeError("供给不可用")


class TestPageDigests:
    def test_标题行优先并标注取字失败页(self) -> None:
        pages = [
            _page(1, "民事起诉状原告张三", layout_title="民事起诉状"),
            _page(2, ocr_failed=True),
        ]
        digests = build_page_digests(pages)
        assert digests[0] == "【第1页｜标题：民事起诉状】民事起诉状原告张三"
        assert digests[1] == "【第2页】（未取到文字）"

    def test_摘要截断到上限(self) -> None:
        digests = build_page_digests([_page(7, "字" * 500)])
        assert digests[0].startswith("【第7页】")
        assert len(digests[0]) <= len("【第7页】") + 200

    def test_user_prompt_含页数类型键与逐页摘要(self) -> None:
        prompt = build_user_prompt([_page(1, "起诉状内容"), _page(2, "证据清单内容")], template_key=TEMPLATE_KEY)
        assert "共 2 页" in prompt
        assert "- complaint：起诉状" in prompt
        assert "- other：其他材料" in prompt
        assert "【第1页】起诉状内容" in prompt
        assert "【第2页】证据清单内容" in prompt


class TestParseLlmSegments:
    def test_正常输出_类型映射与开放命名(self) -> None:
        raw = (
            '{"segments": ['
            + _seg_json(1, 3, "complaint", "民事起诉状", 0.95)
            + ", "
            + _seg_json(4, 10, "other", "借条", 0.7)
            + "]}"
        )
        drafts = parse_llm_segments(raw, total_pages=10, template_key=TEMPLATE_KEY)
        assert len(drafts) == 2
        first, second = drafts
        assert (first.page_start, first.page_end, first.segment_type) == (1, 3, PdfSplitSegmentType.COMPLAINT)
        assert first.filename == "民事起诉状.pdf"
        assert first.source_method == "llm"
        assert first.review_flag == PdfSplitReviewFlag.NORMAL
        assert first.confidence == 0.95
        # other → unrecognized + 开放命名落在 filename，标记低置信度复核
        assert (second.segment_type, second.filename) == (PdfSplitSegmentType.UNRECOGNIZED, "借条.pdf")
        assert second.review_flag == PdfSplitReviewFlag.LOW_CONFIDENCE
        assert [d.order for d in drafts] == [1, 2]

    def test_代码块围栏与裸数组都能解析(self) -> None:
        fenced = "```json\n[" + _seg_json(1, 2) + "]\n```"
        assert len(parse_llm_segments(fenced, total_pages=2, template_key=TEMPLATE_KEY)) == 1
        bare = "[" + _seg_json(1, 2) + "]"
        assert len(parse_llm_segments(bare, total_pages=2, template_key=TEMPLATE_KEY)) == 1

    def test_重叠区间被钳位_钳位后倒置的丢弃(self) -> None:
        raw = "[" + _seg_json(1, 5) + ", " + _seg_json(4, 8) + ", " + _seg_json(6, 6) + "]"
        drafts = parse_llm_segments(raw, total_pages=8, template_key=TEMPLATE_KEY)
        spans = [(d.page_start, d.page_end) for d in drafts]
        assert spans == [(1, 5), (6, 8)]  # 第三段 6-6 被第二段吞没后丢弃，末段并到 8

    def test_页码越界钳位(self) -> None:
        raw = "[" + _seg_json(0, 99, "evidence_list", "证据清单") + "]"
        drafts = parse_llm_segments(raw, total_pages=10, template_key=TEMPLATE_KEY)
        assert (drafts[0].page_start, drafts[0].page_end) == (1, 10)

    def test_未覆盖区间由gap补片兜底(self) -> None:
        raw = "[" + _seg_json(3, 4, "complaint", "起诉状") + "]"
        drafts = parse_llm_segments(raw, total_pages=6, template_key=TEMPLATE_KEY)
        spans = [(d.page_start, d.page_end, d.source_method) for d in drafts]
        assert spans == [
            (1, 2, "gap_fill"),
            (3, 4, "llm"),
            (5, 6, "gap_fill"),
        ]
        assert drafts[0].segment_type == PdfSplitSegmentType.UNRECOGNIZED
        assert drafts[0].review_flag == PdfSplitReviewFlag.UNRECOGNIZED

    def test_置信度钳位与缺省(self) -> None:
        raw = "[" + _seg_json(1, 1, confidence=1.7) + ", " + _seg_json(2, 2, confidence=None) + "]"
        drafts = parse_llm_segments(raw, total_pages=2, template_key=TEMPLATE_KEY)
        assert drafts[0].confidence == 1.0
        assert drafts[1].confidence == 0.5  # 缺省
        assert drafts[1].review_flag == PdfSplitReviewFlag.LOW_CONFIDENCE  # < 0.6

    def test_label缺省回退模板标签或区间名(self) -> None:
        raw = "[" + _seg_json(1, 2, "evidence_list", "") + ", " + _seg_json(3, 3, "other", "") + "]"
        drafts = parse_llm_segments(raw, total_pages=3, template_key=TEMPLATE_KEY)
        assert drafts[0].filename == "证据清单及明细.pdf"
        assert drafts[1].filename == "材料_3-3.pdf"

    @pytest.mark.parametrize(
        "raw",
        [
            "这不是 JSON",
            '{"segments": []}',
            '{"segments": "oops"}',
            '[{"page_start": "x", "page_end": 2}]',
            "[]",
        ],
    )
    def test_非法输出抛ValueError供上层降级(self, raw: str) -> None:
        with pytest.raises(ValueError):
            parse_llm_segments(raw, total_pages=5, template_key=TEMPLATE_KEY)


class TestDetectorDetect:
    def test_端到端_stub_供给返回分段并透传调用参数(self) -> None:
        stub = _StubLLM("[" + _seg_json(1, 2, "complaint", "起诉状", 0.9) + "]")
        detector = LLMSegmentDetector(llm_service=stub)
        drafts = detector.detect([_page(1, "起诉状"), _page(2, "续页")], template_key=TEMPLATE_KEY)
        assert len(drafts) == 1
        assert drafts[0].filename == "起诉状.pdf"
        assert stub.calls and stub.calls[0]["temperature"] == 0.1
        assert stub.calls[0]["messages"][0]["role"] == "system"

    def test_空页面抛错(self) -> None:
        with pytest.raises(Exception):
            LLMSegmentDetector(llm_service=_StubLLM("[]")).detect([], template_key=TEMPLATE_KEY)

    def test_供给异常向上传播(self) -> None:
        class _Boom:
            def chat(self, *args: Any, **kwargs: Any) -> Any:
                raise RuntimeError("gateway down")

        with pytest.raises(RuntimeError, match="gateway down"):
            LLMSegmentDetector(llm_service=_Boom()).detect([_page(1, "x")], template_key=TEMPLATE_KEY)


class TestServiceFallback:
    def test_llm失败降级规则引擎并记录原因(self) -> None:
        pages = [
            _page(1, "民事起诉状", top_candidates=[{
                "segment_type": PdfSplitSegmentType.COMPLAINT,
                "label": "起诉状",
                "score": 0.8,
                "matched_strong": ["起诉状"],
                "matched_weak": [],
            }]),
            _page(2, "证据清单", top_candidates=[{
                "segment_type": PdfSplitSegmentType.EVIDENCE_LIST,
                "label": "证据清单及明细",
                "score": 0.7,
                "matched_strong": ["证据清单"],
                "matched_weak": [],
            }]),
        ]
        service = PdfSplitService(llm_segment_detector=_RaisingDetector())
        drafts, summary = service._detect_segments_with_fallback(pages, template_key=TEMPLATE_KEY)
        assert summary["segment_backend"] == "rule"
        assert "RuntimeError" in summary["segment_llm_fallback_reason"]
        assert drafts and all(d.source_method != "llm" for d in drafts)

    def test_llm成功时summary记录llm后端(self) -> None:
        class _OkDetector:
            def detect(self, pages: list[PageDescriptor], *, template_key: str) -> list[Any]:
                return parse_llm_segments(
                    "[" + _seg_json(1, len(pages), "complaint", "起诉状", 0.9) + "]",
                    total_pages=len(pages),
                    template_key=template_key,
                )

        service = PdfSplitService(llm_segment_detector=_OkDetector())
        drafts, summary = service._detect_segments_with_fallback([_page(1, "起诉状")], template_key=TEMPLATE_KEY)
        assert summary == {"segment_backend": "llm", "segment_llm_fallback_reason": ""}
        assert drafts[0].source_method == "llm"
