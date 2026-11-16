"""边界二审（P2-9a）的单元测试。

为什么需要二审：续页合并的序号判据只能救「条款号连续推进」的合同。164 页
真实卷宗里最典型的一份被切开的合同（p116-125 / p126-140）是**半句话跨页**
——p125 末行「5.3 抵押担保的范围为…提前还款补偿」，p126 首行「金、损害赔偿金
和实现债权及抵押权的费用。」，首行根本没有序号，序号判据永远并不回。
而 p126 恰好是批界（164 页 / 25 页一批 → 批首 1, 26, 51, 76, 101, 126, 151）。

二审的硬约束（本文件逐条锁住）：
- 只在有疑点时调用（批界 + 低置信边界），不是每条边界都审；
- 总次数有上限；
- 拿两侧**整页全文**，不是 150+110 摘要；
- 失败 / 非法输出 / 改动不可行 → **保持原边界**，绝不乱切；
- detector 没有二审能力时整段跳过（注入的桩不该触发真实 LLM 调用）。

全部用 stub，不真调 LLM。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.pdf_splitting.services.split import segment_batch, segment_merge
from apps.pdf_splitting.services.split.split_models import SegmentDraft


@dataclass
class _Page:
    page_no: int
    text: str = ""


def _draft(start: int, end: int, *, order: int = 0, flag: str = "normal", conf: float = 0.9) -> SegmentDraft:
    return SegmentDraft(
        order=order,
        page_start=start,
        page_end=end,
        segment_type="loan_contract",
        filename="借款合同.pdf",
        confidence=conf,
        source_method="llm",
        review_flag=flag,
    )


class _Reviewer:
    """二审桩：按后段起始页给结论，记录每次调用拿到的两侧全文。"""

    def __init__(self, verdicts: dict[int, str | None] | None = None, error: Exception | None = None) -> None:
        self.verdicts = verdicts or {}
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def __call__(self, *, left_page: int, right_page: int, left_text: str, right_text: str) -> str | None:
        self.calls.append(
            {"left_page": left_page, "right_page": right_page, "left_text": left_text, "right_text": right_text}
        )
        if self.error is not None:
            raise self.error
        return self.verdicts.get(right_page, "keep")


class _Detector:
    """分段桩：每批只为负责区间产出一段；可选挂上二审能力。"""

    def __init__(self, reviewer: Any = None) -> None:
        if reviewer is not None:
            self.review_boundary = reviewer

    def detect(self, pages: list[Any], *, template_key: str, context_pages: int = 0) -> list[Any]:
        return [_draft(context_pages + 1, len(pages))]


def _pages(n: int, texts: dict[int, str] | None = None) -> list[_Page]:
    texts = texts or {}
    return [_Page(i, text=texts.get(i, f"第{i}页正文")) for i in range(1, n + 1)]


def _spans(drafts: list[Any]) -> list[tuple[int, int]]:
    return [(d.page_start, d.page_end) for d in drafts]


def _covered(drafts: list[Any]) -> list[int]:
    pages: list[int] = []
    for draft in drafts:
        pages.extend(range(draft.page_start, draft.page_end + 1))
    return pages


class TestReviewChangesBoundary:
    def test_批界半句话跨页被二审并回(self) -> None:
        """真实样本的机制复现：p25 末行半句话 → p26 首行接着那半句。"""
        texts = {
            25: "5.3 抵押担保的范围为本合同项下贷款本金及利息、复利、罚息、提前还款补偿",
            26: "金、损害赔偿金和实现债权及抵押权的费用。实现债权及抵押权的费用包括但不限于催收费。",
        }
        reviewer = _Reviewer({26: "merge"})
        result = segment_batch.detect_in_batches(
            pages=_pages(60, texts),
            template_key="t",
            detector=_Detector(reviewer),
            size=25,
            overlap=5,
        )
        assert _spans(result) == [(1, 50), (51, 60)]
        assert _covered(result) == list(range(1, 61))  # 合并不能丢页
        assert [call["right_page"] for call in reviewer.calls] == [26, 51]

    def test_二审拿到的是两侧整页全文而不是摘要(self) -> None:
        long_left = "条款正文\n" * 300 + "5.3 …提前还款补偿"
        long_right = "金、损害赔偿金和实现债权及抵押权的费用。" + "后续正文\n" * 300
        reviewer = _Reviewer({26: "keep"})
        segment_batch.detect_in_batches(
            pages=_pages(60, {25: long_left, 26: long_right}),
            template_key="t",
            detector=_Detector(reviewer),
            size=25,
            overlap=5,
        )
        call = next(c for c in reviewer.calls if c["right_page"] == 26)
        assert call["left_page"] == 25
        assert call["left_text"] == long_left
        assert call["right_text"] == long_right

    def test_move_right_把后段首页划给前段(self) -> None:
        reviewer = _Reviewer({26: "move_right"})
        result = segment_batch.detect_in_batches(
            pages=_pages(60),
            template_key="t",
            detector=_Detector(reviewer),
            size=25,
            overlap=5,
        )
        assert _spans(result) == [(1, 26), (27, 50), (51, 60)]
        assert _covered(result) == list(range(1, 61))

    def test_move_left_把前段末页划给后段(self) -> None:
        reviewer = _Reviewer({26: "move_left"})
        result = segment_batch.detect_in_batches(
            pages=_pages(60),
            template_key="t",
            detector=_Detector(reviewer),
            size=25,
            overlap=5,
        )
        assert _spans(result) == [(1, 24), (25, 50), (51, 60)]
        assert _covered(result) == list(range(1, 61))


class TestReviewKeepsBoundary:
    def test_二审维持则分段不动(self) -> None:
        reviewer = _Reviewer({26: "keep", 51: "keep"})
        result = segment_batch.detect_in_batches(
            pages=_pages(60),
            template_key="t",
            detector=_Detector(reviewer),
            size=25,
            overlap=5,
        )
        assert _spans(result) == [(1, 25), (26, 50), (51, 60)]
        assert all(d.review_flag == "normal" for d in result)  # 复核通过就不该被打扰

    def test_没有疑点就不调用二审(self) -> None:
        """整本一批、只有一段 → 没有边界可审，一次都不该调。"""
        reviewer = _Reviewer()
        result = segment_batch.detect_in_batches(
            pages=_pages(10),
            template_key="t",
            detector=_Detector(reviewer),
            size=25,
            overlap=5,
        )
        assert reviewer.calls == []
        assert _spans(result) == [(1, 10)]

    def test_detector没有二审能力时整段跳过(self) -> None:
        """注入的桩只实现 detect：不能因为分段就触发真实 LLM 调用，
        也不该凭空给段打低置信标记。"""
        stats: dict[str, Any] = {}
        result = segment_batch.detect_in_batches(
            pages=_pages(60),
            template_key="t",
            detector=_Detector(),
            size=25,
            overlap=5,
            stats=stats,
        )
        assert _spans(result) == [(1, 25), (26, 50), (51, 60)]
        assert all(d.review_flag == "normal" for d in result)
        assert stats["boundary_reviews"] == 0


class TestReviewFailureKeepsOriginal:
    def test_二审抛异常保持原边界并标疑点(self) -> None:
        reviewer = _Reviewer(error=RuntimeError("gateway down"))
        result = segment_batch.detect_in_batches(
            pages=_pages(60),
            template_key="t",
            detector=_Detector(reviewer),
            size=25,
            overlap=5,
        )
        assert _spans(result) == [(1, 25), (26, 50), (51, 60)]
        flagged = [d.page_start for d in result if d.review_flag == "low_confidence"]
        assert flagged == [26, 51]  # 未复核成的疑点边界要让人看一眼

    def test_二审返回非法结论保持原边界(self) -> None:
        reviewer = _Reviewer({26: None, 51: None})
        result = segment_batch.detect_in_batches(
            pages=_pages(60),
            template_key="t",
            detector=_Detector(reviewer),
            size=25,
            overlap=5,
        )
        assert _spans(result) == [(1, 25), (26, 50), (51, 60)]
        assert [d.review_flag for d in result] == ["normal", "low_confidence", "low_confidence"]

    def test_不可行的移动保持原边界(self) -> None:
        """后段只有一页时 move_right 会把它移成空段——必须拒绝。"""
        segments = [_draft(1, 25), _draft(26, 26), _draft(27, 60)]
        result = segment_merge.apply_boundary_verdict(segments, boundary_page=26, action="move_right")
        assert _spans(result) == _spans(segments)

    def test_不可行的左移保持原边界(self) -> None:
        segments = [_draft(1, 1), _draft(2, 60)]
        result = segment_merge.apply_boundary_verdict(segments, boundary_page=2, action="move_left")
        assert _spans(result) == _spans(segments)

    def test_超上限的合并不执行(self) -> None:
        segments = [_draft(1, 76), _draft(77, 90)]
        result = segment_merge.apply_boundary_verdict(segments, boundary_page=77, action="merge")
        assert _spans(result) == _spans(segments)  # 90 页 > MAX_MERGED_PAGES

    def test_未知动作保持原边界(self) -> None:
        segments = [_draft(1, 25), _draft(26, 60)]
        assert _spans(segment_merge.apply_boundary_verdict(segments, boundary_page=26, action="explode")) == _spans(
            segments
        )

    def test_边界已不存在时不动(self) -> None:
        """前一条二审改过边界后，后面的候选页号可能已失效——跳过而不是乱改。"""
        segments = [_draft(1, 50), _draft(51, 60)]
        assert _spans(segment_merge.apply_boundary_verdict(segments, boundary_page=26, action="merge")) == _spans(
            segments
        )


class TestReviewBounds:
    def test_总次数封顶(self) -> None:
        reviewer = _Reviewer()
        stats: dict[str, Any] = {}
        result = segment_batch.detect_in_batches(
            pages=_pages(60),
            template_key="t",
            detector=_Detector(reviewer),
            size=5,
            overlap=1,
            stats=stats,
        )
        assert len(reviewer.calls) == segment_merge.MAX_BOUNDARY_REVIEWS == 4
        assert stats["boundary_reviews"] == 4
        assert _covered(result) == list(range(1, 61))  # 二审不改覆盖

    def test_超上限的疑点标低置信(self) -> None:
        reviewer = _Reviewer()
        result = segment_batch.detect_in_batches(
            pages=_pages(60),
            template_key="t",
            detector=_Detector(reviewer),
            size=5,
            overlap=1,
        )
        flagged = [d.page_start for d in result if d.review_flag == "low_confidence"]
        # 12 批 → 11 个批界，审前 4 个（6/11/16/21），其余 7 个标疑点
        assert flagged == [26, 31, 36, 41, 46, 51, 56]

    def test_批界优先于低置信边界(self) -> None:
        """批界是设计已知的薄弱点；低置信只是模型自报、无校准（B6）。"""
        segments = [
            _draft(1, 9, flag="low_confidence"),
            _draft(10, 19, flag="low_confidence"),
            _draft(20, 29),
            _draft(30, 39),
        ]
        suspects = segment_merge.collect_boundary_suspects(segments, batch_start_pages={30})
        assert suspects == [30, 10, 20]

    def test_不相邻的段不算边界(self) -> None:
        segments = [_draft(1, 5), _draft(8, 12)]
        assert segment_merge.collect_boundary_suspects(segments, batch_start_pages={8}) == []

    def test_全正常且无批界则无疑点(self) -> None:
        segments = [_draft(1, 5), _draft(6, 12)]
        assert segment_merge.collect_boundary_suspects(segments, batch_start_pages=set()) == []


class TestUnverifiedMarking:
    def test_只标疑点边界后段且不动置信度数值(self) -> None:
        """B6 保守校准：不凭空调 confidence 数值，只用结构信号补复核标记。"""
        segments = [_draft(1, 25, conf=0.95), _draft(26, 50, conf=0.95), _draft(51, 60, conf=0.95)]
        marked = segment_merge.mark_unverified_boundaries(segments, boundary_pages={26})
        assert [d.review_flag for d in marked] == ["normal", "low_confidence", "normal"]
        assert [d.confidence for d in marked] == [0.95, 0.95, 0.95]

    def test_已有更差标记不被降级覆盖(self) -> None:
        segments = [_draft(1, 25), _draft(26, 50, flag="unrecognized")]
        marked = segment_merge.mark_unverified_boundaries(segments, boundary_pages={26})
        assert marked[1].review_flag == "unrecognized"

    def test_空集合原样返回(self) -> None:
        segments = [_draft(1, 25), _draft(26, 50)]
        assert segment_merge.mark_unverified_boundaries(segments, boundary_pages=set()) == segments
