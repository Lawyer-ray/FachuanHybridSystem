"""LLM 分段分批的单元测试。

背景：164 页整本一次性交给 LLM 分段，总时长撞上 Django-Q 的 600s worker
超时被杀（实测 499s 被杀）。分批要同时解决两件事：

1. 缩短单次 LLM 调用（否则还是会被杀）；
2. **不能切错段**——分段是跨页语义任务，硬切会让跨批的段被切成两截。

所以用「右侧重叠窗口」：每批多看几页当上下文，但只采纳落在本批负责区间的段。
下面锁住窗口规划与合并的正确性。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from apps.pdf_splitting.services.split import segment_batch


@dataclass
class _FakePage:
    """最简页描述：只需要 page_no（_renumber_page 会浅拷贝改它）。"""

    page_no: int


@dataclass
class _FakeDraft:
    page_start: int
    page_end: int
    order: int = 0
    segment_type: str = "test"


class TestPlanSegmentWindows:
    def test_windows_cover_every_page_exactly_once(self) -> None:
        """负责区间必须无缝无重叠——任何一页遗漏都会让覆盖校验失败。"""
        total = 164
        windows = segment_batch.plan_segment_windows(total, size=25, overlap=8)
        own_ranges = [(start, end) for start, end, _, _ in windows]

        seen: list[int] = []
        for start, end in own_ranges:
            seen.extend(range(start, end + 1))
        assert seen == list(range(1, total + 1))

    def test_window_extends_into_overlap(self) -> None:
        windows = segment_batch.plan_segment_windows(164, size=25, overlap=8)
        first = windows[0]
        assert first == (1, 25, 1, 33)

    def test_last_window_clamped_to_total(self) -> None:
        windows = segment_batch.plan_segment_windows(164, size=25, overlap=8)
        last = windows[-1]
        assert last[3] == 164
        assert last[1] == 164

    def test_single_window_when_small(self) -> None:
        windows = segment_batch.plan_segment_windows(2, size=25, overlap=8)
        assert windows == [(1, 2, 1, 2)]

    def test_zero_pages(self) -> None:
        assert segment_batch.plan_segment_windows(0) == []

    def test_zero_overlap_still_covers(self) -> None:
        windows = segment_batch.plan_segment_windows(10, size=4, overlap=0)
        assert [(s, e) for s, e, _, _ in windows] == [(1, 4), (5, 8), (9, 10)]


class TestMergeBatchDrafts:
    def test_adopts_only_own_range(self) -> None:
        """批 1（负责 1-25，看到 1-33）里起点 30 的段属于批 2，不该被批 1 采纳。"""
        window1 = (1, 25, 1, 33)
        window2 = (26, 50, 26, 58)
        drafts1 = [_FakeDraft(1, 10), _FakeDraft(11, 20), _FakeDraft(30, 40)]
        drafts2 = [_FakeDraft(26, 40), _FakeDraft(41, 50)]

        merged = segment_batch.merge_batch_drafts(
            batch_results=[(window1, drafts1), (window2, drafts2)],
            total_pages=50,
        )

        # 批1 采纳 1-10、11-20；批2 采纳 26-40、41-50
        assert [(d.page_start, d.page_end) for d in merged] == [(1, 10), (11, 20), (26, 40), (41, 50)]

    def test_clips_page_end_to_own_end(self) -> None:
        """跨批的段由起点所在批产出，但终点要裁到本批负责区间。"""
        window1 = (1, 25, 1, 33)
        drafts1 = [_FakeDraft(20, 30)]  # 起点在本批，终点越界

        merged = segment_batch.merge_batch_drafts(
            batch_results=[(window1, drafts1)],
            total_pages=30,
        )

        assert merged[0].page_start == 20
        assert merged[0].page_end == 25  # 裁到批终点

    def test_reorders_after_merge(self) -> None:
        window = (1, 10, 1, 10)
        drafts = [_FakeDraft(5, 8), _FakeDraft(1, 4)]
        merged = segment_batch.merge_batch_drafts(batch_results=[(window, drafts)], total_pages=10)
        assert [d.order for d in merged] == [0, 1]
        assert [d.page_start for d in merged] == [1, 5]


class TestDetectInBatches:
    def test_single_batch_preserves_original_call(self) -> None:
        """页数很少时不走分批，保留原始行为。"""

        class _Detector:
            def __init__(self) -> None:
                self.calls: list[int] = []

            def detect(self, pages: list[Any], *, template_key: str) -> list[Any]:
                self.calls.append(len(pages))
                return [_FakeDraft(1, len(pages))]

        detector = _Detector()
        result = segment_batch.detect_in_batches(
            pages=[_FakePage(i) for i in range(1, 3)],
            template_key="t",
            detector=detector,
            size=25,
            overlap=8,
        )
        assert detector.calls == [2]
        assert len(result) == 1

    def test_multi_batch_offsets_page_numbers(self) -> None:
        """批 2 的模型只看到相对页 1..n，必须映射回绝对页号。"""

        class _Detector:
            def detect(self, pages: list[Any], *, template_key: str) -> list[Any]:
                # 每批都返回「整批一一段」，起点为相对页 1
                return [_FakeDraft(1, len(pages))]

        result = segment_batch.detect_in_batches(
            pages=[_FakePage(i) for i in range(1, 61)],
            template_key="t",
            detector=_Detector(),
            size=25,
            overlap=5,
        )
        # 三段：1-25, 26-50, 51-60
        assert [(d.page_start, d.page_end) for d in result] == [(1, 25), (26, 50), (51, 60)]

    def test_single_batch_failure_falls_back_to_rule(self) -> None:
        """单批失败只让这一批退回规则引擎，其他批的 LLM 成果必须保留。

        真实教训：164 页跑出 82 段质量很好，但 7 批里有 1 批偶发返回非法 JSON，
        旧逻辑「任一批失败即整轮降级」把 6/7 的 LLM 成果全废掉了。
        """
        calls = {"n": 0}

        class _Detector:
            def detect(self, pages: list[Any], *, template_key: str) -> list[Any]:
                calls["n"] += 1
                # 第二批恒失败（含重试）
                if calls["n"] in (2, 3, 4):
                    raise RuntimeError("llm down")
                return [_FakeDraft(1, len(pages))]

        with patch.object(
            segment_batch,
            "_rule_fallback_for_window",
            side_effect=lambda pages, _tk: [_FakeDraft(1, len(pages))],
        ):
            result = segment_batch.detect_in_batches(
                pages=[_FakePage(i) for i in range(1, 61)],
                template_key="t",
                detector=_Detector(),
                size=25,
                overlap=5,
                retries=1,
            )

        # 三批都有结果（第二批来自规则引擎兜底）
        assert len(result) == 3
        assert [(d.page_start, d.page_end) for d in result] == [(1, 25), (26, 50), (51, 60)]

    def test_all_batches_failing_raises_for_global_fallback(self) -> None:
        """全部批都失败时才算 LLM 不可用，让上层整轮降级。"""

        class _Detector:
            def detect(self, pages: list[Any], *, template_key: str) -> list[Any]:
                raise RuntimeError("llm down")

        maybe = []
        try:
            with patch.object(
                segment_batch,
                "_rule_fallback_for_window",
                side_effect=lambda pages, _tk: [_FakeDraft(1, len(pages))],
            ):
                segment_batch.detect_in_batches(
                    pages=[_FakePage(i) for i in range(1, 61)],
                    template_key="t",
                    detector=_Detector(),
                    size=25,
                    overlap=5,
                    retries=0,
                )
        except RuntimeError:
            maybe = [1]
        else:
            raise AssertionError("预期异常未抛出（全批失败应整轮降级）")

    def test_transient_failure_is_retried(self) -> None:
        """偶发抖动必须靠重试解决，不该一失败就退回规则引擎。"""
        state = {"calls": 0}

        class _FlakyDetector:
            def detect(self, pages: list[Any], *, template_key: str) -> list[Any]:
                state["calls"] += 1
                if state["calls"] == 1:
                    raise RuntimeError("transient")
                return [_FakeDraft(1, len(pages))]

        result = segment_batch.detect_in_batches(
            pages=[_FakePage(i) for i in range(1, 61)],
            template_key="t",
            detector=_FlakyDetector(),
            size=25,
            overlap=5,
            retries=2,
        )
        assert len(result) == 3
        # 第一次失败 + 重试成功，说明重试生效
        assert state["calls"] >= 4
