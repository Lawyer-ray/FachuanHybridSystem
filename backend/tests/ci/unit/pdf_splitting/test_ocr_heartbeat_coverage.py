"""逐页 OCR 的心跳覆盖（缺陷 A）——2026-11-20 事故的直接回归。

## 事故（2026-11-20，一份 93 页扫描卷宗的取字任务；作业 ID 不入库）

    11:40:43  extract 启动
    11:41:56  MinerU 4 批解析完（73s），进度 80/93，一切正常
    11:43:23  **最后一拍心跳**
    11:43-11:57  PaddleOCR 单页 OCR 连续 8 次 `Job 超时（300s）`
    11:57-11:59  OCR 恢复，剩余页跑完（93/93、progress=100）
    12:00:43  django-q 硬超时杀任务（1200s），worker 进程重生

心跳冻结了 **839 秒**：`_ocr_pages_worker` 的逐页 `try/except` 里一次
`touch_heartbeat` 都没有，而进度回调要等**整批**跑完才触发。看门狗
（`job_recovery`）靠 `max(heartbeat_at, updated_at)` 判活，阈值 30 分钟——
心跳再多冻一倍时间，一个**仍在正常重试**的任务就会被判死重排（= 整份卷宗
再付一次云端费用）。

本模块锁住四件事：

1. `_ocr_pages_worker` 每页开始/结束都刷心跳，**失败路径（except）同样刷**；
2. 单页识别阻塞期间由 `heartbeat_block` 的后台线程补拍（不靠页边界）；
3. `parallel_ocr` 的**全部** `_ocr_pages_worker` 调用点都透传心跳/预算
   （漏一个就是「主路径有心跳、补跑路径没有」的黑洞）；
4. `PdfSplitService.extract_stage` 真的把「给这个 job 刷心跳」封成回调下传，
   且心跳实现只有一份（service 的方法转调 heartbeat 模块）。

全部用桩与合成 PDF，不调云端。
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import pymupdf as fitz
import pytest
from django.utils import timezone

from apps.pdf_splitting.models import PdfSplitJob, PdfSplitJobStatus, PdfSplitSourceType, PdfSplitStage
from apps.pdf_splitting.services import heartbeat as heartbeat_module
from apps.pdf_splitting.services.heartbeat import heartbeat_block
from apps.pdf_splitting.services.split import ocr_handler as ocr_handler_module
from apps.pdf_splitting.services.split import service as service_module
from apps.pdf_splitting.services.split.ocr_handler import OCRHandler, OCRStageBudget, _ocr_pages_worker
from apps.pdf_splitting.services.split.service import PdfSplitService
from apps.pdf_splitting.services.split.split_models import OCRRuntimeProfile
from apps.pdf_splitting.services.split.two_stage import (
    EXTRACT_STAGE_TAIL_RESERVE_SECONDS,
    EXTRACT_STAGE_TIMEOUT_SECONDS,
)

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _isolated_media_root(tmp_path: Path, settings: Any) -> Path:
    """MEDIA_ROOT 钉到临时目录：`PdfSplitService` 构造即碰存储层，不能碰真实 media。"""
    settings.MEDIA_ROOT = tmp_path / "media"
    return tmp_path


# ----------------------------------------------------------------------
# 构造件
# ----------------------------------------------------------------------


def _make_scan_pdf(path: Path, pages: int = 3) -> Path:
    """造一份空白页 PDF：无文本层，逐页都会走 OCR 路径（本模块只关心心跳，不关心内容）。"""
    with fitz.open() as doc:
        for _ in range(pages):
            doc.new_page()
        doc.save(path.as_posix())
    return path


class _FakeOCRService:
    """替身 OCRService：`_ocr_pages_worker` 只把它传给 `_recognize_page`（这里已打桩）。"""

    def __init__(self, *, use_v5: bool = False) -> None:
        self.use_v5 = use_v5


class _BeatCounter:
    """心跳回调计数器：顺手记录「这一拍发生在单页识别阻塞期间吗」。"""

    def __init__(self) -> None:
        self.calls = 0
        self.during_block = 0
        self._in_block = False

    def __call__(self) -> None:
        self.calls += 1
        if self._in_block:
            self.during_block += 1

    def enter_block(self) -> None:
        self._in_block = True

    def exit_block(self) -> None:
        self._in_block = False


def _patch_ocr_engine(monkeypatch: pytest.MonkeyPatch, recognize: Any) -> None:
    """把云端 OCR 换成桩：`OCRService` 构造与单页识别都不碰真实 API。"""
    monkeypatch.setattr(ocr_handler_module, "OCRService", _FakeOCRService)
    monkeypatch.setattr(ocr_handler_module, "_recognize_page", recognize)


# ----------------------------------------------------------------------
# 1. 逐页心跳（含失败路径）
# ----------------------------------------------------------------------


class TestPerPageHeartbeat:
    def test_每页开始与结束都刷心跳_失败页也刷(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """事故里 8 次超时全走 `except`，一拍心跳都没刷——这条路径必须补上。"""
        pdf = _make_scan_pdf(tmp_path / "scan.pdf", pages=3)
        counter = _BeatCounter()
        recognized: list[int] = []

        def fake_recognize(_service: Any, _image: bytes, *, page_no: int) -> tuple[str, Any]:
            recognized.append(page_no)
            counter.enter_block()
            try:
                if page_no == 2:
                    # 真实的失败形态：paddleocr_api_service.py:780
                    raise RuntimeError("PaddleOCR API Job 超时（300s）")
                return f"第{page_no}页正文", None
            finally:
                counter.exit_block()

        _patch_ocr_engine(monkeypatch, fake_recognize)

        results = _ocr_pages_worker(
            pdf_path=pdf.as_posix(), page_numbers=[1, 2, 3], use_v5=False, dpi=144, heartbeat=counter
        )

        assert recognized == [1, 2, 3]
        assert [item.source_method for item in results] == ["ocr", "ocr_failed", "ocr"]
        # 每页「开始 + 结束(finally)」各一拍 → 3 页 = 6 拍。失败页的拍必须在内。
        assert counter.calls >= 2 * 3

    def test_单页识别阻塞期间心跳不停(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """单页云端识别可能阻塞 300s：页边界上的心跳救不了这 300s，必须靠后台线程。"""
        pdf = _make_scan_pdf(tmp_path / "scan.pdf", pages=1)
        counter = _BeatCounter()

        def slow_recognize(_service: Any, _image: bytes, *, page_no: int) -> tuple[str, Any]:
            counter.enter_block()
            try:
                time.sleep(0.3)  # 模拟「一次调用卡在轮询里」
                return f"第{page_no}页正文", None
            finally:
                counter.exit_block()

        _patch_ocr_engine(monkeypatch, slow_recognize)
        # 真实间隔是 15s（看门狗阈值的百分之一）；单测里压到 20ms 才可断言。
        monkeypatch.setattr(
            ocr_handler_module,
            "heartbeat_block",
            lambda beat: heartbeat_block(beat, interval=0.02),
        )

        _ocr_pages_worker(pdf_path=pdf.as_posix(), page_numbers=[1], use_v5=False, dpi=144, heartbeat=counter)

        # 阻塞期间至少补了 2 拍（0.3s / 0.02s ≫ 2，留足调度抖动余量）
        assert counter.during_block >= 2

    def test_心跳抛异常不会把整批页判失败(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """用一次写库抖动换一整批页的文字，得不偿失：页边界心跳必须 swallow。"""
        pdf = _make_scan_pdf(tmp_path / "scan.pdf", pages=2)
        _patch_ocr_engine(monkeypatch, lambda _s, _i, *, page_no: (f"第{page_no}页正文", None))

        def boom() -> None:
            raise RuntimeError("db hiccup")

        results = _ocr_pages_worker(pdf_path=pdf.as_posix(), page_numbers=[1, 2], use_v5=False, dpi=144, heartbeat=boom)

        assert [item.source_method for item in results] == ["ocr", "ocr"]
        assert [item.text for item in results] == ["第1页正文", "第2页正文"]

    def test_没传心跳回调时不报错也不额外做事(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """纯函数调用（无任务上下文）不能因为新增参数而改变行为。"""
        pdf = _make_scan_pdf(tmp_path / "scan.pdf", pages=2)
        _patch_ocr_engine(monkeypatch, lambda _s, _i, *, page_no: (f"第{page_no}页", None))

        results = _ocr_pages_worker(pdf_path=pdf.as_posix(), page_numbers=[1, 2], use_v5=False, dpi=144)

        assert [item.source_method for item in results] == ["ocr", "ocr"]


# ----------------------------------------------------------------------
# 2. parallel_ocr 的全部调用点
# ----------------------------------------------------------------------


PROFILE = OCRRuntimeProfile(key="balanced", use_v5=True, dpi=200, workers=2)


class TestParallelOcrCallSites:
    def test_单worker路径透传心跳与预算(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        calls: list[dict[str, Any]] = []

        def fake_worker(**kwargs: Any) -> list[Any]:
            calls.append(dict(kwargs))
            return []

        monkeypatch.setattr(ocr_handler_module, "_ocr_pages_worker", fake_worker)
        budget = OCRStageBudget(deadline_monotonic=time.monotonic() + 600, total_seconds=600, started_monotonic=0.0)
        beat = _BeatCounter()

        OCRHandler().parallel_ocr(
            pdf_path=tmp_path / "scan.pdf",
            page_numbers=[1],
            runtime_profile=OCRRuntimeProfile(key="fast", use_v5=False, dpi=140, workers=1),
            budget=budget,
            heartbeat=beat,
        )

        assert len(calls) == 1
        assert calls[0]["budget"] is budget
        assert calls[0]["heartbeat"] is beat

    def test_线程池重试与补跑分支也透传(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """分片异常重试、结果缺失补跑跑的是同一批可能阻塞 300s 的云端调用——漏传就是黑洞。"""
        calls: list[dict[str, Any]] = []
        # 4 页 / 2 个 worker → 分片 [1,3] 与 [2,4]，各自第一次调用炸（覆盖 except 重试分支）；
        # 重试与“结果缺失补跑”都返回空 → 三条分支都会被走到。
        boom_once: set[tuple[int, ...]] = {(1, 3), (2, 4)}

        def fake_worker(**kwargs: Any) -> list[Any]:
            calls.append(dict(kwargs))
            key = tuple(kwargs["page_numbers"])
            if key in boom_once:
                boom_once.discard(key)
                raise RuntimeError("chunk boom")
            return []

        monkeypatch.setattr(ocr_handler_module, "_ocr_pages_worker", fake_worker)
        budget = OCRStageBudget(deadline_monotonic=time.monotonic() + 600, total_seconds=600, started_monotonic=0.0)
        beat = _BeatCounter()

        OCRHandler().parallel_ocr(
            pdf_path=tmp_path / "scan.pdf",
            page_numbers=[1, 2, 3, 4],
            runtime_profile=PROFILE,
            budget=budget,
            heartbeat=beat,
        )

        # 2 个分片各炸一次 → 2 次重试；结果全缺 → 1 次补跑；合计 ≥ 5 次调用
        assert len(calls) >= 5
        for kwargs in calls:
            assert kwargs["budget"] is budget
            assert kwargs["heartbeat"] is beat


# ----------------------------------------------------------------------
# 3. stage 层下传（为什么是回调、不是 job_id）
# ----------------------------------------------------------------------


def _make_job() -> PdfSplitJob:
    return PdfSplitJob.objects.create(
        id=uuid4(),
        source_type=PdfSplitSourceType.UPLOAD,
        source_original_name="卷宗.pdf",
        status=PdfSplitJobStatus.PENDING,
        stage=PdfSplitStage.EXTRACT,
        total_pages=93,
        processed_pages=0,
        current_page=0,
    )


class TestExtractStageWiring:
    def test_心跳封成回调下传且真能写库(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """线程池拿不到 job_id，所以下传的是「动作」；这里验证那个动作确实指向本 job。"""
        job = _make_job()
        old = timezone.now().replace(year=2020)
        PdfSplitJob.objects.filter(id=job.id).update(heartbeat_at=old, updated_at=old)

        captured: dict[str, Any] = {}

        def fake_extract_pages(_pdf_path: Path, **kwargs: Any) -> tuple[list[Any], dict[str, Any]]:
            captured.update(kwargs)
            return [], {}

        monkeypatch.setattr(service_module, "extract_pages", fake_extract_pages)

        PdfSplitService().extract_stage(job)

        heartbeat = captured["heartbeat"]
        assert callable(heartbeat)
        heartbeat()
        job.refresh_from_db()
        assert job.heartbeat_at is not None and job.heartbeat_at > old

    def test_预算从阶段开始时算并覆盖尾部预留(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """预算必须是「django-q 阀值 - 尾部预留」：尾部（落盘/推进阶段）也要留在预算内。"""
        job = _make_job()
        captured: dict[str, Any] = {}

        def fake_extract_pages(_pdf_path: Path, **kwargs: Any) -> tuple[list[Any], dict[str, Any]]:
            captured.update(kwargs)
            return [], {}

        monkeypatch.setattr(service_module, "extract_pages", fake_extract_pages)

        PdfSplitService().extract_stage(job)

        budget = captured["budget"]
        assert isinstance(budget, OCRStageBudget)
        expected = EXTRACT_STAGE_TIMEOUT_SECONDS - EXTRACT_STAGE_TAIL_RESERVE_SECONDS
        assert budget.total_seconds == expected
        assert 0 < budget.remaining_seconds() <= expected

    def test_service的心跳与模块实现同源(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """同一件事不允许有第二份实现：service 的方法必须转调 heartbeat 模块。

        以前是两份拷贝，逐页 OCR 的线程池又需要第三个入口——三份实现必然漏改其中一份，
        而心跳一旦和看门狗的判据不一致，就是“在跑的任务被判死重排”。
        """
        job = _make_job()
        # ① 导入的就是模块里那一个函数（不是本地又写了一份）
        assert service_module._touch_heartbeat_row is heartbeat_module.touch_heartbeat
        # ② 公开方法确实把它转调出去，而不是自己写一遍 update()
        with monkeypatch.context() as patcher:
            calls: list[Any] = []
            patcher.setattr(service_module, "_touch_heartbeat_row", lambda *, job_id: calls.append(job_id))
            PdfSplitService().touch_heartbeat(job_id=job.id)
        assert calls == [job.id]


# ----------------------------------------------------------------------
# 4. 心跳块本身
# ----------------------------------------------------------------------


class TestHeartbeatBlock:
    def test_阻塞期间补拍且退出后线程停止(self) -> None:
        counter = _BeatCounter()

        with heartbeat_block(counter, interval=0.02):
            time.sleep(0.12)

        during = counter.calls
        assert during >= 2
        # 退出后不许续命：线程还活着就会给已结束的任务刷心跳，看门狗永远看不出它死了。
        time.sleep(0.1)
        assert counter.calls == during
        assert not [t for t in threading.enumerate() if t.name == "pdf-split-heartbeat-block"]

    def test_单拍抛异常不打断主流程(self) -> None:
        """心跳只是存活信号：写库抖动丢掉一拍还有下一拍，不能把整份卷宗弄失败。"""
        calls: list[int] = []

        def boom() -> None:
            calls.append(1)
            raise RuntimeError("db hiccup")

        with heartbeat_block(boom, interval=0.01):
            time.sleep(0.1)

        assert len(calls) >= 2
