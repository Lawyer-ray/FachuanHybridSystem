"""extract 阶段的预算感知降级（缺陷 B）——2026-11-20 事故的回归。

## 事故里预算为什么必然不够

单页云端 OCR 的最坏墙钟是 300s（`paddleocr_api_service.py:780`，
`Job 超时（300s）`）。93 页 / 3 个 worker 的最坏情况是
`93 × 300 / 3 = 9300s`——**任何**预算都盖不住，所以主修不是「把
`EXTRACT_STAGE_TIMEOUT_SECONDS` 调大」，而是让逐页 OCR 知道**还剩多少时间**：

    剩余预算 < 单页最坏 300s + 安全余量 60s  →  不再发这一次注定超时的调用

那一页直接标 `ocr_failed`（既有的兜底形态，不是新发明的一条路），于是阶段
能在预算内**自然结束**，而不是被 django-q 硬杀、连 `finally` 都不执行。

本模块锁住：

1. 阈值算术：`剩余 < 360s` 才降级，`>= 360s` 照常发（不误伤正常任务）；
2. 预算耗尽时**一次云端调用都不发**，页标 `ocr_failed` 且不写 OCR 页缓存
   （否则临时降级会被缓存成「这页永久没字」）；
3. 逐页重判：中途耗尽只跳后面几页，已识别的页不受影响；
4. 预算充足时**行为与不传预算完全一致**（结果、顺序、进度事件、缓存写入）；
5. 降级必须在 summary / 日志里可见，并且下游（`build_page_digests`）
   真的把那些页标成「未取到文字」——少页文本会影响分段边界，代价必须看得见。

全部用桩与合成 PDF，不调云端。
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import pymupdf as fitz
import pytest

from apps.pdf_splitting.services.split import ocr_handler as ocr_handler_module
from apps.pdf_splitting.services.split import two_stage
from apps.pdf_splitting.services.split.llm_segment_detector import build_page_digests
from apps.pdf_splitting.services.split.ocr_handler import (
    SINGLE_PAGE_OCR_SAFETY_MARGIN_SECONDS,
    SINGLE_PAGE_OCR_WORST_CASE_SECONDS,
    OCRStageBudget,
    _ocr_pages_worker,
)
from apps.pdf_splitting.services.split.pipeline import PageTextExtractor
from apps.pdf_splitting.services.split.split_models import OCRPageResult, OCRRuntimeProfile

TEMPLATE_KEY = "filing_materials_v1"
PROFILE = OCRRuntimeProfile(key="balanced", use_v5=True, dpi=200, workers=2)

#: 一次单页云端调用「值得发」所需的最小剩余预算（与实现里的阈值同义，独立写一遍是为了
#: 让阈值变化时**两种口径同时**打脸：算术没变但常量被改，这里会红）。
REQUIRED_SECONDS = SINGLE_PAGE_OCR_WORST_CASE_SECONDS + SINGLE_PAGE_OCR_SAFETY_MARGIN_SECONDS


def _make_scan_pdf(path: Path, pages: int = 3) -> Path:
    """造一份无文本层的扫描件（空白页）：逐页都会走 OCR 路径。"""
    with fitz.open() as doc:
        for _ in range(pages):
            doc.new_page()
        doc.save(path.as_posix())
    return path


class _FakeOCRService:
    def __init__(self, *, use_v5: bool = False) -> None:
        self.use_v5 = use_v5


def _budget(*, remaining: float, total: float = 1290.0) -> OCRStageBudget:
    """造一个「还剩 `remaining` 秒」的预算。"""
    now = time.monotonic()
    return OCRStageBudget(deadline_monotonic=now + remaining, total_seconds=total, started_monotonic=now)


def _patch_ocr_engine(monkeypatch: pytest.MonkeyPatch, recognize: Any) -> None:
    monkeypatch.setattr(ocr_handler_module, "OCRService", _FakeOCRService)
    monkeypatch.setattr(ocr_handler_module, "_recognize_page", recognize)


# ----------------------------------------------------------------------
# 1. 阈值算术
# ----------------------------------------------------------------------


class TestBudgetArithmetic:
    def test_阈值等于单页最坏加安全余量(self) -> None:
        """300s（单页最坏）+ 60s（安全余量）= 360s：低于它才降级。"""
        assert REQUIRED_SECONDS == 360.0
        budget = _budget(remaining=REQUIRED_SECONDS + 0.5)
        assert budget.required_seconds() == REQUIRED_SECONDS
        assert budget.allows_single_page_ocr() is True

    def test_刚好不够时降级(self) -> None:
        """剩余 359.9s < 360s：现在发出去，最坏情况会顶穿预算尾部 —— 不发。"""
        assert _budget(remaining=REQUIRED_SECONDS - 0.1).allows_single_page_ocr() is False

    def test_剩余为负一律不允许(self) -> None:
        budget = _budget(remaining=-5)
        assert budget.remaining_seconds() < 0
        assert budget.allows_single_page_ocr() is False

    def test_阶段预算扣掉尾部预留(self) -> None:
        """尾部（写缓存/pages.json/摘要/推进阶段）必须留在预算内，不能被 OCR 吃掉。"""
        budget = two_stage.extract_stage_budget(now=1000.0)
        expected = two_stage.EXTRACT_STAGE_TIMEOUT_SECONDS - two_stage.EXTRACT_STAGE_TAIL_RESERVE_SECONDS
        assert budget.deadline_monotonic == pytest.approx(1000.0 + expected)
        assert budget.total_seconds == pytest.approx(expected)
        assert budget.remaining_seconds(now=1000.0) == pytest.approx(expected)

    def test_取字预算装得下事故实测形态(self) -> None:
        """20 分钟从算术上就装不下那次事故（1096s 干活 + ≥100s 尾部），这是抬到 24 分钟的依据。"""
        incident_work = 1096  # 11:40:43 → 11:59 跑完 93/93
        observed_tail = 104  # 11:59 → 12:00:43 被杀，尾部还没跑完
        assert incident_work + observed_tail < two_stage.EXTRACT_STAGE_TIMEOUT_SECONDS
        assert two_stage.EXTRACT_STAGE_TIMEOUT_SECONDS == 24 * 60
        # 尾部预留必须小于总预算，否则一开局就“没预算可用”
        assert 0 < two_stage.EXTRACT_STAGE_TAIL_RESERVE_SECONDS < two_stage.EXTRACT_STAGE_TIMEOUT_SECONDS


# ----------------------------------------------------------------------
# 2. 逐页 OCR 的降级行为
# ----------------------------------------------------------------------


class TestWorkerDegrade:
    def test_预算耗尽时一次云端调用都不发(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        pdf = _make_scan_pdf(tmp_path / "scan.pdf", pages=3)
        calls: list[int] = []
        _patch_ocr_engine(monkeypatch, lambda _s, _i, *, page_no: calls.append(page_no) or (f"第{page_no}页", None))
        budget = _budget(remaining=-1)

        with caplog.at_level(logging.WARNING, logger="apps.pdf_splitting"):
            results = _ocr_pages_worker(
                pdf_path=pdf.as_posix(),
                page_numbers=[1, 2, 3],
                use_v5=False,
                dpi=144,
                budget=budget,
            )

        assert calls == []  # 一次都没发：不做注定超时的调用
        assert [item.source_method for item in results] == ["ocr_failed"] * 3
        assert all(item.ocr_failed for item in results)
        assert budget.skipped_pages == {1, 2, 3}
        assert budget.skipped_count == 3
        # 逐页留痕：排障时要能对上「哪一页因为剩多少秒被跳过」
        skipped_logs = [r for r in caplog.records if r.msg == "pdf_split_ocr_page_skipped_budget"]
        assert len(skipped_logs) == 3

    def test_预算充足时行为与不传预算完全一致(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """正常扫描件的硬要求：结果、顺序、调用次数一个都不许变。"""
        pdf = _make_scan_pdf(tmp_path / "scan.pdf", pages=3)
        calls: list[int] = []
        _patch_ocr_engine(monkeypatch, lambda _s, _i, *, page_no: calls.append(page_no) or (f"第{page_no}页正文", None))

        baseline = _ocr_pages_worker(pdf_path=pdf.as_posix(), page_numbers=[1, 2, 3], use_v5=False, dpi=144)
        calls.clear()
        budget = _budget(remaining=1200)
        with_budget = _ocr_pages_worker(
            pdf_path=pdf.as_posix(), page_numbers=[1, 2, 3], use_v5=False, dpi=144, budget=budget
        )

        assert calls == [1, 2, 3]
        assert [(item.page_no, item.text, item.source_method, item.ocr_failed) for item in with_budget] == [
            (item.page_no, item.text, item.source_method, item.ocr_failed) for item in baseline
        ]
        assert budget.skipped_pages == set()

    def test_逐页重判_中途耗尽只跳后面(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """预算判断必须在**每页调用前**做一次：不能只在批首算一次就一路放行。"""
        pdf = _make_scan_pdf(tmp_path / "scan.pdf", pages=3)
        budget = _budget(remaining=1200)
        calls: list[int] = []

        def recognize(_service: Any, _image: bytes, *, page_no: int) -> tuple[str, Any]:
            calls.append(page_no)
            if page_no == 1:
                # 模拟“这一页卡掉了大部分预算”（真实形态：一次 300s 超时）
                budget.deadline_monotonic = time.monotonic() - 1
            return f"第{page_no}页正文", None

        _patch_ocr_engine(monkeypatch, recognize)

        results = _ocr_pages_worker(
            pdf_path=pdf.as_posix(), page_numbers=[1, 2, 3], use_v5=False, dpi=144, budget=budget
        )

        assert calls == [1]  # 只有第 1 页真的发了云端调用
        assert [item.source_method for item in results] == ["ocr", "ocr_failed", "ocr_failed"]
        assert budget.skipped_pages == {2, 3}


# ----------------------------------------------------------------------
# 3. 编排层：缓存、summary、下游可见性
# ----------------------------------------------------------------------


class _StubOCRHandler:
    """取字桩：只走本地兜底路径（无云端候选），并按 `degraded_pages` 模拟预算降级。

    降级契约与真实 `_ocr_pages_worker` 一致：在 `budget` 上 `mark_skipped`，并返回
    `source_method="ocr_failed"` 的结果（这是既有兜底形态，不是新造的一条路）。
    """

    def __init__(self, *, pages: int, degraded_pages: set[int] | None = None) -> None:
        self.pages = pages
        self.degraded_pages = degraded_pages or set()
        self.local_calls: list[list[int]] = []
        self.written: list[tuple[str, int, str]] = []
        self.heartbeats = 0

    def resolve_runtime_profile(self, profile_key: str) -> OCRRuntimeProfile:
        return PROFILE

    def resolve_cloud_backends(self, cloud_backend: str | None = None) -> list[str]:
        return []  # 不试云端，直接把所有页交给本地 OCR 兜底

    def sha256_file(self, pdf_path: Path) -> str:
        return "hash-budget"

    def read_ocr_cache(self, *, pdf_hash: str, profile_key: str, page_no: int) -> OCRPageResult | None:
        return None

    def write_ocr_cache(
        self, *, pdf_hash: str, profile_key: str, result: OCRPageResult, page_no: int | None = None
    ) -> None:
        self.written.append((profile_key, result.page_no, result.source_method))

    def parse_cloud_pages(self, *, pdf_path: Path, backend: str) -> dict[int, OCRPageResult]:
        return {}

    def parallel_ocr(
        self,
        *,
        pdf_path: Path,
        page_numbers: list[int],
        runtime_profile: OCRRuntimeProfile,
        budget: OCRStageBudget | None = None,
        heartbeat: Any = None,
    ) -> dict[int, OCRPageResult]:
        self.local_calls.append(list(page_numbers))
        if heartbeat is not None:
            heartbeat()  # 桩也走一遍心跳，验证回调确实下传到了这一层
            self.heartbeats += 1
        out: dict[int, OCRPageResult] = {}
        for page_no in page_numbers:
            if page_no in self.degraded_pages and budget is not None:
                budget.mark_skipped(page_no)
                out[page_no] = OCRPageResult(page_no=page_no, text="", source_method="ocr_failed", ocr_failed=True)
                continue
            out[page_no] = OCRPageResult(
                page_no=page_no, text=f"第{page_no}页正文内容", source_method="ocr", ocr_failed=False
            )
        return out

    def ocr_page_region(self, *, pdf_path: Path, page_no: int, region: list[float], runtime_profile: Any) -> Any:
        return None


class TestPipelineDegrade:
    def _extract(
        self,
        pdf: Path,
        handler: _StubOCRHandler,
        *,
        budget: OCRStageBudget | None,
        progress: list[tuple[int, int]] | None = None,
        heartbeat: Any = None,
    ) -> Any:
        def on_progress(resolved: int, total: int) -> None:
            if progress is not None:
                progress.append((resolved, total))

        extractor = PageTextExtractor(ocr_handler=handler, on_progress=on_progress, budget=budget, heartbeat=heartbeat)
        return extractor.extract(pdf, ocr_profile="balanced", template_key=TEMPLATE_KEY)

    def test_降级页标ocr_failed且不写缓存并计入summary(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """预算是**这一次**的临时状态：写进缓存就变成“这页永久没字”，重跑连重试机会都没有。"""
        pdf = _make_scan_pdf(tmp_path / "scan.pdf", pages=3)
        handler = _StubOCRHandler(pages=3, degraded_pages={2, 3})
        budget = _budget(remaining=1200)

        with caplog.at_level(logging.WARNING, logger="apps.pdf_splitting"):
            pages, summary = self._extract(pdf, handler, budget=budget)

        assert [page.source_method for page in pages] == ["ocr", "ocr_failed", "ocr_failed"]
        assert [page.ocr_failed for page in pages] == [False, True, True]
        # 只有真正识别过的页写缓存
        assert [(profile, page_no) for profile, page_no, _ in handler.written] == [(PROFILE.key, 1)]
        # 计数与页号都进 summary（少页文本影响分段边界，必须可见）
        assert summary["ocr_budget_skipped_count"] == 2
        assert summary["ocr_budget_skipped_pages"] == [2, 3]
        assert summary["stage_budget_seconds"] == pytest.approx(budget.total_seconds)
        assert any(r.msg == "pdf_split_ocr_budget_degraded" for r in caplog.records)

    def test_降级页在下游被标未取到文字(self, tmp_path: Path) -> None:
        """`llm_segment_detector` 会跳过 ocr_failed 页——降级的代价必须在这里现形。"""
        pdf = _make_scan_pdf(tmp_path / "scan.pdf", pages=2)
        handler = _StubOCRHandler(pages=2, degraded_pages={2})

        pages, _summary = self._extract(pdf, handler, budget=_budget(remaining=1200))

        digests = build_page_digests(pages)
        assert "未取到文字" in digests[1]
        assert "未取到文字" not in digests[0]

    def test_预算充足时进度事件与不传预算完全一致(self, tmp_path: Path) -> None:
        """硬要求：正常扫描件上不能有任何行为改变（进度事件序列也不例外）。"""
        pdf = _make_scan_pdf(tmp_path / "scan.pdf", pages=3)

        baseline_progress: list[tuple[int, int]] = []
        baseline_handler = _StubOCRHandler(pages=3)
        baseline_pages, baseline_summary = self._extract(pdf, baseline_handler, budget=None, progress=baseline_progress)

        budgeted_progress: list[tuple[int, int]] = []
        budgeted_handler = _StubOCRHandler(pages=3)
        budgeted_pages, budgeted_summary = self._extract(
            pdf, budgeted_handler, budget=_budget(remaining=1200), progress=budgeted_progress
        )

        assert budgeted_progress == baseline_progress
        assert [(p.page_no, p.text, p.source_method, p.ocr_failed) for p in budgeted_pages] == [
            (p.page_no, p.text, p.source_method, p.ocr_failed) for p in baseline_pages
        ]
        assert budgeted_handler.written == baseline_handler.written
        assert budgeted_handler.local_calls == baseline_handler.local_calls
        # 预算相关字段只在真算了预算时才出现，避免给无预算的纯函数调用凭空加字段
        assert "ocr_budget_skipped_count" not in baseline_summary
        assert budgeted_summary["ocr_budget_skipped_count"] == 0
        assert budgeted_summary["ocr_budget_skipped_pages"] == []

    def test_心跳回调下传到逐页OCR(self, tmp_path: Path) -> None:
        """缺陷 A 的接线在同一层验证一次：心跳必须真的走到线程池那一层。"""
        pdf = _make_scan_pdf(tmp_path / "scan.pdf", pages=2)
        handler = _StubOCRHandler(pages=2)
        beats: list[int] = []

        self._extract(pdf, handler, budget=_budget(remaining=1200), heartbeat=lambda: beats.append(1))

        assert beats and handler.heartbeats == 1
