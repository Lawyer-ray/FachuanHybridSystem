"""LLM 分段分批的单元测试。

背景：164 页整本一次性交给 LLM 分段，总时长撞上 Django-Q 的 600s worker
超时被杀（实测 499s 被杀）。分批要同时解决两件事：

1. 缩短单次 LLM 调用（否则还是会被杀）；
2. **不能切错段**——分段是跨页语义任务，硬切会让跨批的段被切成两截。

所以用「左右重叠窗口」：每批向前向后各多看几页当上下文，但只采纳落在本批
负责区间的段。左上下文是后补的（P1-3）：只有右上下文时批首没有左邻页，
模型看不到上一批的收尾信号，164 页 = 6 个结构性错切点。

下面锁住窗口规划、上下文标注、页号偏移、合并、重试、stats 口径与批级落盘续跑。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

from apps.pdf_splitting.services.split import segment_batch
from apps.pdf_splitting.services.split.split_models import SegmentDraft


@dataclass
class _FakePage:
    """最简页描述：只需要 page_no（_renumber_page 会浅拷贝改它）。"""

    page_no: int
    text: str = ""


@dataclass
class _FakeDraft:
    page_start: int
    page_end: int
    order: int = 0
    segment_type: str = "test"


def _draft(start: int, end: int, *, order: int = 0, flag: str = "normal") -> SegmentDraft:
    return SegmentDraft(
        order=order,
        page_start=start,
        page_end=end,
        segment_type="loan_contract",
        filename="借款合同.pdf",
        confidence=0.9,
        source_method="llm",
        review_flag=flag,
    )


class _OwnRangeDetector:
    """按分批契约产出的桩：只为「负责区间」产出一段，上下文页不产出。

    这是 P1-3 之后 detector 的正确行为——旧桩「整批一段、起点相对页 1」
    在有左上下文时会把段起点落到上下文区，被 merge 过滤掉，固化的是旧行为。
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def detect(self, pages: list[Any], *, template_key: str, context_pages: int = 0) -> list[Any]:
        self.calls.append(
            {
                "size": len(pages),
                "context_pages": context_pages,
                "page_nos": [p.page_no for p in pages],
            }
        )
        return [_FakeDraft(context_pages + 1, len(pages))]


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
        assert first == (1, 25, 1, 33)  # 第一批没有左邻页

    def test_批首带左上下文(self) -> None:
        """P1-3 的核心：批 2 起 win_start = own_start - overlap，批首不再是盲切。"""
        windows = segment_batch.plan_segment_windows(164, size=25, overlap=8)
        assert windows[1] == (26, 50, 18, 58)
        assert windows[2] == (51, 75, 43, 83)
        for own_start, _own_end, win_start, _win_end in windows[1:]:
            assert win_start == own_start - 8

    def test_左上下文不越过第一页(self) -> None:
        windows = segment_batch.plan_segment_windows(10, size=4, overlap=8)
        assert windows[0] == (1, 4, 1, 10)
        assert windows[1] == (5, 8, 1, 10)
        assert windows[2] == (9, 10, 1, 10)

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
        assert windows[1] == (5, 8, 5, 8)


class TestMergeBatchDrafts:
    def test_adopts_only_own_range(self) -> None:
        """批 1（负责 1-25，看到 1-33）里起点 30 的段属于批 2，不该被批 1 采纳。"""
        window1 = (1, 25, 1, 33)
        window2 = (26, 50, 18, 58)
        drafts1 = [_FakeDraft(1, 10), _FakeDraft(11, 20), _FakeDraft(30, 40)]
        drafts2 = [_FakeDraft(26, 40), _FakeDraft(41, 50)]

        merged = segment_batch.merge_batch_drafts(
            batch_results=[(window1, drafts1), (window2, drafts2)],
            total_pages=50,
        )

        assert [(d.page_start, d.page_end) for d in merged] == [(1, 10), (11, 20), (26, 40), (41, 50)]

    def test_左上下文区的段不被采纳(self) -> None:
        """批 2 看到 18-58，但只负责 26-50：起点落在左上下文（18-25）的段必须丢掉，
        否则会和批 1 的成果重复。"""
        window = (26, 50, 18, 58)
        drafts = [_FakeDraft(18, 25), _FakeDraft(26, 40), _FakeDraft(41, 58)]
        merged = segment_batch.merge_batch_drafts(batch_results=[(window, drafts)], total_pages=58)
        assert [(d.page_start, d.page_end) for d in merged] == [(26, 40), (41, 50)]

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
        """页数很少时不走分批；且**不传 context_pages**——整本一次调用没有上下文页，
        detector 协议的基础签名不该被要求接受扩展参数。"""

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
        """批 2 的模型只看到相对页 1..n（含左上下文），必须映射回绝对页号。

        断言与 P1-3 之前一样严格：三段 1-25 / 26-50 / 51-60，段界不许多也不许少。
        """
        detector = _OwnRangeDetector()
        result = segment_batch.detect_in_batches(
            pages=[_FakePage(i) for i in range(1, 61)],
            template_key="t",
            detector=detector,
            size=25,
            overlap=5,
        )
        assert [(d.page_start, d.page_end) for d in result] == [(1, 25), (26, 50), (51, 60)]

    def test_每批拿到正确的左上下文与相对页号(self) -> None:
        detector = _OwnRangeDetector()
        segment_batch.detect_in_batches(
            pages=[_FakePage(i) for i in range(1, 61)],
            template_key="t",
            detector=detector,
            size=25,
            overlap=5,
        )
        by_size = {call["size"]: call for call in detector.calls}
        # 批1 送 1-30（30 页，无左上下文）；批2 送 21-55（35 页，左 5）；批3 送 46-60（15 页，左 5）
        assert by_size[30]["context_pages"] == 0
        assert by_size[35]["context_pages"] == 5
        assert by_size[15]["context_pages"] == 5
        for call in detector.calls:
            assert call["page_nos"] == list(range(1, call["size"] + 1))

    def test_single_batch_failure_falls_back_to_rule(self) -> None:
        """单批失败只让这一批退回规则引擎，其他批的 LLM 成果必须保留。

        真实教训：164 页跑出 82 段质量很好，但 7 批里有 1 批偶发返回非法 JSON，
        旧逻辑「任一批失败即整轮降级」把 6/7 的 LLM 成果全废掉了。
        """

        class _Detector:
            def detect(self, pages: list[Any], *, template_key: str, context_pages: int = 0) -> list[Any]:
                # 批 2 的窗口是 35 页（21-55）：按窗口特征恒失败，不依赖并行调用顺序
                if len(pages) == 35:
                    raise RuntimeError("llm down")
                return [_FakeDraft(context_pages + 1, len(pages))]

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

        assert len(result) == 3
        assert [(d.page_start, d.page_end) for d in result] == [(1, 25), (26, 50), (51, 60)]

    def test_规则降级批仍整覆盖不留缺口(self) -> None:
        """加左上下文后，规则降级批必须只覆盖负责区间。

        用**真实**规则引擎（不是桩）才抓得出页号索引错位：它按 pages[page_no-1]
        取页、按 len(pages) 补 gap，喂带左上下文的切片会取错页并在批首留缺口。
        """
        from apps.pdf_splitting.services.split.pipeline import build_page_descriptor

        texts = ["民事起诉状 诉讼请求 事实与理由 原告 被告"] * 25
        texts += ["证据清单 证明内容 页码 原件 复印件"] * 25
        texts += ["银行交易明细 交易日期 账户余额 借方发生额"] * 10
        pages = [
            build_page_descriptor(page_no=i, text=text, source_method="ocr", ocr_failed=False, template_key="t")
            for i, text in enumerate(texts, start=1)
        ]

        class _Detector:
            def detect(self, pages: list[Any], *, template_key: str, context_pages: int = 0) -> list[Any]:
                if len(pages) == 35:  # 批 2 的窗口
                    raise RuntimeError("llm down")
                return [_FakeDraft(context_pages + 1, len(pages))]

        result = segment_batch.detect_in_batches(
            pages=pages, template_key="t", detector=_Detector(), size=25, overlap=5, retries=0
        )
        covered: list[int] = []
        for draft in result:
            covered.extend(range(draft.page_start, draft.page_end + 1))
        assert covered == list(range(1, 61))  # 无缝、无重叠、无缺口

    def test_all_batches_failing_raises_for_global_fallback(self) -> None:
        """全部批都失败时才算 LLM 不可用，让上层整轮降级。"""

        class _Detector:
            def detect(self, pages: list[Any], *, template_key: str, context_pages: int = 0) -> list[Any]:
                raise RuntimeError("llm down")

        stats: dict[str, Any] = {}
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
                    stats=stats,
                )
        except RuntimeError:
            pass
        else:
            raise AssertionError("预期异常未抛出（全批失败应整轮降级）")
        # 抛异常前也要填好口径，调用方才能诚实写「全部降级」而不是空 stats
        assert stats["llm_batches"] == 0
        assert stats["rule_batches"] == stats["total_batches"] == 3

    def test_transient_failure_is_retried(self) -> None:
        """偶发抖动必须靠重试解决，不该一失败就退回规则引擎。"""
        state = {"calls": 0}

        class _FlakyDetector:
            def detect(self, pages: list[Any], *, template_key: str, context_pages: int = 0) -> list[Any]:
                state["calls"] += 1
                if state["calls"] == 1:
                    raise RuntimeError("transient")
                return [_FakeDraft(context_pages + 1, len(pages))]

        result = segment_batch.detect_in_batches(
            pages=[_FakePage(i) for i in range(1, 61)],
            template_key="t",
            detector=_FlakyDetector(),
            size=25,
            overlap=5,
            retries=2,
        )
        assert len(result) == 3
        assert state["calls"] == 4  # 三批各一次 + 一次重试


class TestSingleBatchRetry:
    """P1-9：≤25 页的单批路径过去直调 detect 无重试，一次非法 JSON 整轮降级——
    小卷宗反而比大卷宗更脆弱。"""

    def test_单批偶发失败靠重试救回(self) -> None:
        state = {"calls": 0}

        class _Flaky:
            def detect(self, pages: list[Any], *, template_key: str) -> list[Any]:
                state["calls"] += 1
                if state["calls"] == 1:
                    raise ValueError("LLM 输出不是合法 JSON")
                return [_FakeDraft(1, len(pages))]

        stats: dict[str, Any] = {}
        result = segment_batch.detect_in_batches(
            pages=[_FakePage(i) for i in range(1, 11)],
            template_key="t",
            detector=_Flaky(),
            size=25,
            retries=2,
            stats=stats,
        )
        assert state["calls"] == 2
        assert [(d.page_start, d.page_end) for d in result] == [(1, 10)]
        assert stats["single_batch"] is True
        assert stats["llm_batches"] == 1

    def test_单批重试耗尽仍抛给上层整轮降级(self) -> None:
        class _Dead:
            def detect(self, pages: list[Any], *, template_key: str) -> list[Any]:
                raise ValueError("LLM 输出不是合法 JSON")

        try:
            segment_batch.detect_in_batches(
                pages=[_FakePage(i) for i in range(1, 11)],
                template_key="t",
                detector=_Dead(),
                size=25,
                retries=1,
            )
        except ValueError:
            pass
        else:
            raise AssertionError("重试耗尽应抛出，让上层整轮降级")


class TestStats:
    def test_全llm批口径(self) -> None:
        stats: dict[str, Any] = {}
        segment_batch.detect_in_batches(
            pages=[_FakePage(i) for i in range(1, 61)],
            template_key="t",
            detector=_OwnRangeDetector(),
            size=25,
            overlap=5,
            stats=stats,
        )
        assert stats["total_batches"] == 3
        assert stats["llm_batches"] == 3
        assert stats["rule_batches"] == 0
        assert stats["single_batch"] is False
        assert stats["resumed_batches"] == 0

    def test_混用批口径不再冒充纯llm(self) -> None:
        class _Detector:
            def detect(self, pages: list[Any], *, template_key: str, context_pages: int = 0) -> list[Any]:
                if len(pages) == 35:
                    raise RuntimeError("llm down")
                return [_FakeDraft(context_pages + 1, len(pages))]

        stats: dict[str, Any] = {}
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
                stats=stats,
            )
        assert stats["llm_batches"] == 2
        assert stats["rule_batches"] == 1

    def test_不传stats也能跑(self) -> None:
        result = segment_batch.detect_in_batches(
            pages=[_FakePage(i) for i in range(1, 61)],
            template_key="t",
            detector=_OwnRangeDetector(),
            size=25,
            overlap=5,
        )
        assert len(result) == 3


class TestCheckpoint:
    """P2-7：每批完成即落盘，worker 被杀后重跑不再重付 LLM 费。"""

    def _pages(self, n: int = 60) -> list[_FakePage]:
        return [_FakePage(i, text=f"第{i}页正文") for i in range(1, n + 1)]

    def test_round_trip_落盘后重跑不再调LLM(self, tmp_path: Path) -> None:
        path = tmp_path / "segB_ckpt_roundtrip.json"
        first = _OwnRangeDetector()
        stats1: dict[str, Any] = {}
        result1 = segment_batch.detect_in_batches(
            pages=self._pages(),
            template_key="t",
            detector=first,
            size=25,
            overlap=5,
            stats=stats1,
            checkpoint_path=path,
        )
        assert path.exists()
        assert len(first.calls) == 3
        assert stats1["resumed_batches"] == 0

        # 重跑：一个 LLM 调用都不该发生，结果必须逐字段一致
        second = _OwnRangeDetector()
        stats2: dict[str, Any] = {}
        result2 = segment_batch.detect_in_batches(
            pages=self._pages(),
            template_key="t",
            detector=second,
            size=25,
            overlap=5,
            stats=stats2,
            checkpoint_path=path,
        )
        assert second.calls == []
        assert stats2["resumed_batches"] == 3
        assert [(d.page_start, d.page_end) for d in result2] == [(d.page_start, d.page_end) for d in result1]

    def test_落盘形状含窗口四元组与路径与可序列化draft(self, tmp_path: Path) -> None:
        path = tmp_path / "segB_ckpt_shape.json"
        segment_batch.detect_in_batches(
            pages=self._pages(),
            template_key="t",
            detector=_OwnRangeDetector(),
            size=25,
            overlap=5,
            checkpoint_path=path,
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["version"] == 1
        assert payload["total_pages"] == 60
        assert payload["size"] == 25 and payload["overlap"] == 5
        assert len(payload["batches"]) == 3
        for batch in payload["batches"]:
            assert len(batch["window"]) == 4
            assert batch["path"] in ("llm", "rule")
            assert batch["drafts"]
            for draft in batch["drafts"]:
                assert set(draft) == {
                    "order",
                    "page_start",
                    "page_end",
                    "segment_type",
                    "filename",
                    "confidence",
                    "source_method",
                    "review_flag",
                }
        # 落盘的是**已偏移**的绝对页号，重跑不能再偏移一次
        assert payload["batches"][1]["window"] == [26, 50, 21, 55]
        assert payload["batches"][1]["drafts"][0]["page_start"] == 26

    def test_部分完成时只补跑剩下的批(self, tmp_path: Path) -> None:
        path = tmp_path / "segB_ckpt_partial.json"
        segment_batch.detect_in_batches(
            pages=self._pages(),
            template_key="t",
            detector=_OwnRangeDetector(),
            size=25,
            overlap=5,
            checkpoint_path=path,
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["batches"] = payload["batches"][:1]  # 只留批 1，模拟批 2/3 还没跑完就被杀
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        detector = _OwnRangeDetector()
        stats: dict[str, Any] = {}
        result = segment_batch.detect_in_batches(
            pages=self._pages(),
            template_key="t",
            detector=detector,
            size=25,
            overlap=5,
            stats=stats,
            checkpoint_path=path,
        )
        assert len(detector.calls) == 2
        assert stats["resumed_batches"] == 1
        assert [(d.page_start, d.page_end) for d in result] == [(1, 25), (26, 50), (51, 60)]

    def test_损坏文件按无checkpoint处理(self, tmp_path: Path) -> None:
        path = tmp_path / "segB_ckpt_corrupt.json"
        path.write_text("{这不是合法 JSON", encoding="utf-8")
        detector = _OwnRangeDetector()
        stats: dict[str, Any] = {}
        result = segment_batch.detect_in_batches(
            pages=self._pages(),
            template_key="t",
            detector=detector,
            size=25,
            overlap=5,
            stats=stats,
            checkpoint_path=path,
        )
        assert len(detector.calls) == 3
        assert stats["resumed_batches"] == 0
        assert len(result) == 3
        # 重跑后文件被修好
        assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1

    def test_参数变了旧checkpoint作废(self, tmp_path: Path) -> None:
        path = tmp_path / "segB_ckpt_stale.json"
        segment_batch.detect_in_batches(
            pages=self._pages(),
            template_key="t",
            detector=_OwnRangeDetector(),
            size=25,
            overlap=5,
            checkpoint_path=path,
        )
        detector = _OwnRangeDetector()
        stats: dict[str, Any] = {}
        segment_batch.detect_in_batches(
            pages=self._pages(),
            template_key="t",
            detector=detector,
            size=20,  # 批大小变了 → 窗口变了 → 旧批结果不能用
            overlap=5,
            stats=stats,
            checkpoint_path=path,
        )
        assert stats["resumed_batches"] == 0
        assert len(detector.calls) == 3

    def test_单条批记录损坏只丢那一批(self, tmp_path: Path) -> None:
        path = tmp_path / "segB_ckpt_badbatch.json"
        segment_batch.detect_in_batches(
            pages=self._pages(),
            template_key="t",
            detector=_OwnRangeDetector(),
            size=25,
            overlap=5,
            checkpoint_path=path,
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["batches"][1]["drafts"][0]["page_start"] = "坏页号"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        detector = _OwnRangeDetector()
        stats: dict[str, Any] = {}
        segment_batch.detect_in_batches(
            pages=self._pages(),
            template_key="t",
            detector=detector,
            size=25,
            overlap=5,
            stats=stats,
            checkpoint_path=path,
        )
        assert stats["resumed_batches"] == 2
        assert len(detector.calls) == 1

    def test_不传checkpoint_path不落盘(self, tmp_path: Path) -> None:
        stats: dict[str, Any] = {}
        segment_batch.detect_in_batches(
            pages=self._pages(),
            template_key="t",
            detector=_OwnRangeDetector(),
            size=25,
            overlap=5,
            stats=stats,
        )
        assert stats["resumed_batches"] == 0

    def test_真实SegmentDraft逐字段round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "segB_ckpt_fields.json"
        window = (1, 10, 1, 12)
        done = {window: ("llm", [_draft(1, 5, order=0, flag="low_confidence"), _draft(6, 10, order=1)])}
        segment_batch._save_checkpoint(
            path, template_key="filing_materials_v1", total_pages=10, size=10, overlap=2, done=done
        )
        loaded = segment_batch._load_checkpoint(
            path, template_key="filing_materials_v1", total_pages=10, size=10, overlap=2
        )
        assert loaded[window][0] == "llm"
        assert loaded[window][1] == done[window][1]
        path.unlink(missing_ok=True)
