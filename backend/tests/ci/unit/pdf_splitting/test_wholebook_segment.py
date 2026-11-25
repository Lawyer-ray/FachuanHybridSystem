"""整本一次分段：prompt 用料、策略选择、失败降级、边界分歧标记。

价值来自「一次能不能看全」：同一份正文上，分批摘要路径稳定给出 7 段、整本路径
稳定给出 9 段（差在身份证/法代证明书被并进「主体资格材料」）。所以这里锁的是
**行为契约**，不是某次切法的具体结果。
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from apps.pdf_splitting.models import PdfSplitReviewFlag
from apps.pdf_splitting.services.split.pipeline import (
    SEGMENT_STRATEGY_WHOLEBOOK,
    SEGMENT_STRATEGY_WHOLEBOOK_CROSS,
    detect_segments_with_fallback,
    resolve_segment_strategy,
)
from apps.pdf_splitting.services.split.split_models import PageDescriptor
from apps.pdf_splitting.services.split.wholebook_segment_detector import (
    _PAGE_CHAR_LIMIT,
    _TOTAL_CHAR_BUDGET,
    build_wholebook_prompt,
)

TEMPLATE_KEY = "filing_materials_v1"


def _pages(texts: list[str]) -> list[PageDescriptor]:
    return [
        PageDescriptor(
            page_no=index + 1,
            text=text,
            normalized_text=text,
            head_text=text[:240],
            source_method="mineru_ocr",
            ocr_failed=False,
            top_candidates=[],
        )
        for index, text in enumerate(texts)
    ]


class _Detector:
    """可编程分段器：返回预置段，或抛错。"""

    def __init__(self, segments: list[tuple[int, int]], error: Exception | None = None) -> None:
        self.segments = segments
        self.error = error
        self.calls = 0
        self.last_budget: dict[str, Any] = {}

    def detect(self, pages: list[Any], *, template_key: str, **kwargs: Any) -> list[Any]:
        from apps.pdf_splitting.services.split.llm_segment_detector import parse_llm_segments

        self.calls += 1
        if self.error:
            raise self.error
        payload = {
            "segments": [
                {"page_start": start, "page_end": end, "type": "other", "label": f"材料{start}", "confidence": 0.9}
                for start, end in self.segments
            ]
        }
        return parse_llm_segments(json.dumps(payload), total_pages=len(pages), template_key=template_key)


@pytest.fixture
def stub_wholebook(monkeypatch: pytest.MonkeyPatch) -> Any:
    """把整本检测器换成桩（策略层用真类，只是不真调 LLM）。"""

    def _install(detector: _Detector) -> _Detector:
        import apps.pdf_splitting.services.split.wholebook_segment_detector as module

        monkeypatch.setattr(module, "WholeBookSegmentDetector", lambda *a, **k: detector)
        return detector

    return _install


class TestWholeBookPrompt:
    def test_给的是逐页全文而不是首尾摘要(self) -> None:
        body = "第一段" + "中间内容" * 40 + "结尾落款"
        prompt, budget = build_wholebook_prompt(_pages([body]), template_key=TEMPLATE_KEY)

        assert "中间内容" in prompt, "整本路径必须给全文——摘要丢掉的正是判边界要的信息"
        assert "中略" not in prompt
        assert budget["full_text"] is True

    def test_单页超长截尾并标注(self) -> None:
        prompt, budget = build_wholebook_prompt(_pages(["内容" * (_PAGE_CHAR_LIMIT)]), template_key=TEMPLATE_KEY)

        assert budget["truncated_pages"] == [1]
        assert "已截断" in prompt

    def test_总量超预算时中间页退化成摘要_首尾保全文(self) -> None:
        # 4 页各占 1/3 预算 → 总量必超
        each = "开头" + "内容" * (_TOTAL_CHAR_BUDGET // 6)
        prompt, budget = build_wholebook_prompt(_pages([each] * 4), template_key=TEMPLATE_KEY)

        assert budget["full_text"] is False
        assert budget["digest_pages"] == [2, 3], "只退中间页，首尾必须保全文"
        assert "超过" in prompt and "预算" in prompt

    def test_未取到文字的页显式标注(self) -> None:
        pages = _pages(["正常正文"])
        pages[0].ocr_failed = True
        prompt, _budget = build_wholebook_prompt(pages, template_key=TEMPLATE_KEY)
        assert "未取到文字" in prompt


class TestStrategyResolution:
    def test_默认是分批(self) -> None:
        assert resolve_segment_strategy("") in {"batch", "wholebook", "wholebook_cross"}
        assert resolve_segment_strategy("batch") == "batch"

    def test_未知值落回分批(self) -> None:
        assert resolve_segment_strategy("瞎写的") == "batch"

    def test_三种合法值原样透出(self) -> None:
        for value in ("batch", "wholebook", "wholebook_cross"):
            assert resolve_segment_strategy(value) == value


class TestWholeBookStrategy:
    def test_整本成功时来源报llm_wholebook(self, stub_wholebook: Any) -> None:
        stub_wholebook(_Detector([(1, 2), (3, 3)]))
        drafts, summary = detect_segments_with_fallback(
            _pages(["a" * 50, "b" * 50, "c" * 50]), template_key=TEMPLATE_KEY, strategy=SEGMENT_STRATEGY_WHOLEBOOK
        )

        assert [(d.page_start, d.page_end) for d in drafts] == [(1, 2), (3, 3)]
        assert summary["segment_backend"] == "llm_wholebook"
        assert summary["segment_llm_fallback_reason"] == ""

    def test_整本失败降级回分批而不是直接规则引擎(self, stub_wholebook: Any) -> None:
        stub_wholebook(_Detector([], error=RuntimeError("LLM 超时")))
        drafts, summary = detect_segments_with_fallback(
            _pages(["a" * 50, "b" * 50]),
            template_key=TEMPLATE_KEY,
            strategy=SEGMENT_STRATEGY_WHOLEBOOK,
            llm_segment_detector=_Detector([(1, 2)]),
        )

        assert [(d.page_start, d.page_end) for d in drafts] == [(1, 2)]
        assert summary["segment_backend"] == "llm", "分批 LLM 成功时不该掉到 rule"
        assert "LLM 超时" in summary["segment_llm_fallback_reason"]

    def test_交叉核对标出边界分歧并要求裁定(self, stub_wholebook: Any) -> None:
        # 整本说 p3 起新段；分批说 p2 起新段 → p2/p3 是分歧点
        stub_wholebook(_Detector([(1, 2), (3, 4)]))
        drafts, summary = detect_segments_with_fallback(
            _pages(["a" * 50] * 4),
            template_key=TEMPLATE_KEY,
            strategy=SEGMENT_STRATEGY_WHOLEBOOK_CROSS,
            llm_segment_detector=_Detector([(1, 1), (2, 4)]),
        )

        assert summary["segment_backend"] == "llm_wholebook_cross"
        assert summary["segment_boundary_disagreement_pages"] == [2, 3]
        assert summary["segment_boundary_disagreement_total"] == 2
        flagged = [d for d in drafts if d.review_flag == PdfSplitReviewFlag.BOUNDARY_DISAGREEMENT]
        assert flagged, "分歧点附近的段必须被标成待裁定"
        # 整本结果仍是要交付的那份（分批只用来找分歧，不覆盖）
        assert [(d.page_start, d.page_end) for d in drafts] == [(1, 2), (3, 4)]

    def test_两条路径一致时不标任何复核(self, stub_wholebook: Any) -> None:
        stub_wholebook(_Detector([(1, 2), (3, 4)]))
        drafts, summary = detect_segments_with_fallback(
            _pages(["a" * 50] * 4),
            template_key=TEMPLATE_KEY,
            strategy=SEGMENT_STRATEGY_WHOLEBOOK_CROSS,
            llm_segment_detector=_Detector([(1, 2), (3, 4)]),
        )

        assert summary["segment_boundary_disagreement_pages"] == []
        assert all(d.review_flag != PdfSplitReviewFlag.BOUNDARY_DISAGREEMENT for d in drafts)

    def test_分批策略不碰整本检测器(self, stub_wholebook: Any) -> None:
        detector = stub_wholebook(_Detector([(1, 1)]))
        detect_segments_with_fallback(
            _pages(["a" * 50]), template_key=TEMPLATE_KEY, strategy="batch", llm_segment_detector=_Detector([(1, 1)])
        )
        assert detector.calls == 0
