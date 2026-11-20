"""看门狗「第二判据：阶段硬超时」的单元测试。

## 为什么需要这条判据（2026-11-20 真实事故）

一份 93 页卷宗的取字任务（作业 ID 不入库），`extract` 阶段预算 1200s：

    11:43  PaddleOCR 连续 8 次单页超时（每次 300s）
    11:58  恢复，页面跑到 93/93（progress=100）
    12:00:43  django-q 硬超时杀 worker（TimeoutException，1200 seconds）
    此后   status=processing / stage=extract / progress=100 / 心跳停在 11:58:56
    前端   进度条 100% 永远不动

旧判据只看心跳（`STALE_SECONDS = 1800`），要等到 12:28:56 才认得出它死了，
加上每 5 分钟的扫描间隔，恢复被拖到 12:29~12:34。而「被 django-q 按阶段硬超时
杀掉」这件事是**可以证明**的：django-q 在该阶段 timeout 处一定会销毁 worker
（SIGALRM 抛 `TimeoutException` → worker 置 `timer.value = 0` → guard 循环
`process.terminate()`；兜底的 `timer.value = timeout + 3` 递减同样会 terminate）。
所以「静默超过 该阶段硬超时 + 余量」⇒ 必然已死。

本文件锁住四件事：

1. **判死**：`extract` 静默到「预算 + 余量」之后（事故现场约 1621s，当时旧阈值还
   要再等 3 分钟）时必须已经判死；
2. **不误杀**：硬超时未满 + 余量、阶段没登记预算、非内容分析任务、显式关闭判据，
   以及「心跳还很新但 updated_at 很旧」的任务，一律不许判死；
3. **可区分**：判死原因必须能把「硬超时（云端把预算烧完了）」与「心跳超时
   （可能是网络/worker 被杀）」分开，并且带 stage + 预算 + 最后进度；
4. **映射不漂移**：`default_stage_timeouts()` 的值必须等于 `two_stage.py` 真正
   提交给 django-q 的常量——映射小于真实预算就会把**还在跑**的任务判死。
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.pdf_splitting.models import PdfSplitJob, PdfSplitJobStatus, PdfSplitMode, PdfSplitSourceType, PdfSplitStage
from apps.pdf_splitting.services import job_recovery
from apps.pdf_splitting.services.split.two_stage import (
    CROSS_CHECK_STAGE_TIMEOUT_SECONDS,
    EXTRACT_STAGE_TIMEOUT_SECONDS,
    SEGMENT_STAGE_TIMEOUT_SECONDS,
)

# 合成 UUID（真实作业号不入库：它能反查到具体案件）
_ACCIDENT_JOB_ID = "00000000-0000-4000-8000-000000000000"

#: 事故现场的静默时长（心跳停在 11:58:56，观测时约 1621s）。
#:
#: 用「当前预算 + 余量 + 60s」兜底而不是写死 1621：阶段预算在 `two_stage.py` 里
#: 被调整过（1200s → 更大），判死阈值会随之一同后移，写死的数字会让这条回归用例
#: 莫名其妙变红——而它要锁的是「预算 + 余量之后必判死」这个语义。
_ACCIDENT_SILENT = max(
    1621.0,
    float(EXTRACT_STAGE_TIMEOUT_SECONDS + job_recovery.STAGE_DEAD_GRACE_SECONDS + 60),
)


def _job(
    *,
    stage: str = "extract",
    split_mode: str = PdfSplitMode.CONTENT_ANALYSIS,
    silent_seconds: float = 0.0,
    now: Any = None,
    progress: int = 0,
    processed_pages: int = 0,
    total_pages: int = 93,
    recovery_attempts: int = 0,
    has_segments: bool = False,
    segments: int = 0,
    job_id: str = _ACCIDENT_JOB_ID,
) -> MagicMock:
    """构造一个足够真实的 job 替身（只带 job_recovery 用到的属性）。

    所有时间字段统一取 `now - silent_seconds`：这样 `_last_liveness` 的 max()
    与「最后活动」严格可控（与 `test_job_recovery.py::_job` 同一套路）。
    """
    now = now or timezone.now()
    last = now - timedelta(seconds=silent_seconds)
    job = MagicMock()
    for key, value in {
        "id": job_id,
        "status": "processing",
        "stage": stage,
        "split_mode": split_mode,
        "progress": progress,
        "processed_pages": processed_pages,
        "total_pages": total_pages,
        "recovery_attempts": recovery_attempts,
        "heartbeat_at": last,
        "updated_at": last,
        "started_at": last,
        "created_at": last,
    }.items():
        setattr(job, key, value)
    job.segments.exists.return_value = has_segments
    job.segments.count.return_value = segments
    return job


def _real_job(*, stage: str = PdfSplitStage.EXTRACT, **kwargs: Any) -> PdfSplitJob:
    """建一行真实任务（用于锁住「真 str/int 字段也走同一条判据」）。"""
    fields: dict[str, Any] = {
        "id": uuid.uuid4(),
        "source_type": PdfSplitSourceType.UPLOAD,
        "source_original_name": "事故卷宗.pdf",
        "status": PdfSplitJobStatus.PROCESSING,
        "split_mode": PdfSplitMode.CONTENT_ANALYSIS,
        "stage": stage,
        "total_pages": 93,
        "processed_pages": 93,
        "progress": 100,
    }
    fields.update(kwargs)
    return PdfSplitJob.objects.create(**fields)


def _backdate(job: PdfSplitJob, *, now: Any, silent_seconds: float, keep_heartbeat: bool = True) -> PdfSplitJob:
    """把所有存活信号统一调回 `silent_seconds` 前（`created_at` 也要改：
    它参与 `_last_liveness` 的 max()，留着「刚刚创建」会把任务伪装成活着的）。"""
    last = now - timedelta(seconds=silent_seconds)
    PdfSplitJob.objects.filter(id=job.id).update(
        heartbeat_at=last if keep_heartbeat else None,
        updated_at=last,
        started_at=last,
        created_at=last,
    )
    job.refresh_from_db()
    return job


def _stub_queryset(jobs: list[MagicMock]) -> MagicMock:
    """把 `PdfSplitJob.objects.filter(...)` 链换成可迭代的假 QuerySet（两层链都要成立）。"""
    queryset = MagicMock()
    queryset.filter.return_value = queryset
    queryset.__iter__ = lambda _self: iter(jobs)
    return queryset


def _patch_queryset(jobs: list[MagicMock]) -> Any:
    return patch.object(job_recovery.PdfSplitJob.objects, "filter", return_value=_stub_queryset(jobs))


class TestHardTimeoutVerdict:
    """第二判据：静默超过「阶段硬超时 + 余量」即可证明已死。"""

    def test_事故现场必须已经判死(self) -> None:
        """本文件的回归基准：`extract` 烧完预算后仍静默的任务必须被判死。

        「比旧的心跳判据更早」这一性质单独由
        `TestStageBudgetSourceOfTruth::test_extract的判死阈值确实早于心跳阈值` 锁住（
        它依赖当前预算值），这里只锁「必判死 + 归因为硬超时」这个不随预算漂移的语义。
        """
        now = timezone.now()
        job = _job(now=now, silent_seconds=_ACCIDENT_SILENT, progress=100, processed_pages=93, total_pages=93)

        with _patch_queryset([job]):
            assert job_recovery.find_stale_jobs(now=now) == [job]

        verdict = job_recovery.explain_staleness(job, now=now)
        assert verdict.dead is True
        assert verdict.reason == job_recovery.REASON_HARD_TIMEOUT
        assert verdict.stage == "extract"
        assert verdict.stage_budget_seconds == EXTRACT_STAGE_TIMEOUT_SECONDS
        assert verdict.threshold_seconds == EXTRACT_STAGE_TIMEOUT_SECONDS + job_recovery.STAGE_DEAD_GRACE_SECONDS

    def test_硬超时已到但余量未过不判死(self) -> None:
        """刚好烧完预算还不能判死：SIGALRM 可能还卡在 C 调用里没送到。"""
        now = timezone.now()
        job = _job(now=now, silent_seconds=EXTRACT_STAGE_TIMEOUT_SECONDS + 1)

        with _patch_queryset([job]):
            assert job_recovery.find_stale_jobs(now=now) == []
        assert job_recovery.explain_staleness(job, now=now).dead is False

    def test_静默恰好等于阈值不判死(self) -> None:
        """判据是严格大于：阈值那一秒仍算活着（保守优先）。"""
        now = timezone.now()
        budget = EXTRACT_STAGE_TIMEOUT_SECONDS
        job = _job(now=now, silent_seconds=budget + job_recovery.STAGE_DEAD_GRACE_SECONDS)

        assert job_recovery.explain_staleness(job, now=now).dead is False

    @pytest.mark.parametrize(
        ("stage", "budget"),
        [
            ("cross_check", CROSS_CHECK_STAGE_TIMEOUT_SECONDS),
            ("segment", SEGMENT_STAGE_TIMEOUT_SECONDS),
        ],
    )
    def test_其它阶段用各自的硬超时(self, stage: str, budget: int) -> None:
        """`cross_check` / `segment` 的预算 + 余量都大于 1800s，所以新判据在那两个
        阶段**不会**比旧的心跳判据更早触发（推论见 `explain_staleness` 的注释）。
        它们的收益是「归因准确」：阈值一过就报硬超时，而不是笼统的心跳超时。
        """
        now = timezone.now()
        grace = job_recovery.STAGE_DEAD_GRACE_SECONDS

        # 阶段判据还没成立时，先由心跳判据兜住（不能报成硬超时）
        just_inside = _job(now=now, stage=stage, silent_seconds=budget + grace)
        inside = job_recovery.explain_staleness(just_inside, now=now)
        assert inside.reason == job_recovery.REASON_HEARTBEAT
        assert inside.threshold_seconds == job_recovery.STALE_SECONDS

        # 过了自己的预算 + 余量 → 归因为硬超时，并带上该阶段的预算
        just_outside = _job(now=now, stage=stage, silent_seconds=budget + grace + 1)
        verdict = job_recovery.explain_staleness(just_outside, now=now)
        assert verdict.dead is True
        assert verdict.reason == job_recovery.REASON_HARD_TIMEOUT
        assert verdict.stage_budget_seconds == budget

    def test_心跳很新时即使updated_at很旧也不判死(self) -> None:
        """判活仍以心跳优先：新判据不能把「心跳在跳」的任务判死。"""
        now = timezone.now()
        job = _job(now=now, silent_seconds=EXTRACT_STAGE_TIMEOUT_SECONDS * 4)
        job.heartbeat_at = now - timedelta(seconds=10)

        with _patch_queryset([job]):
            assert job_recovery.find_stale_jobs(now=now) == []
        assert job_recovery.explain_staleness(job, now=now).dead is False


class TestFallbacksNeverKill:
    """没有把握时必须回落到旧判据（只按心跳），绝不套用一个更大的预算假设。"""

    def test_阶段没登记预算时回落心跳阈值(self) -> None:
        now = timezone.now()
        # `done` 是两阶段链的终态，没有自己的提交预算
        not_stale = _job(now=now, stage="done", silent_seconds=_ACCIDENT_SILENT)
        verdict = job_recovery.explain_staleness(not_stale, now=now)
        assert verdict.dead is False
        assert verdict.stage_budget_seconds is None

        stale = _job(now=now, stage="done", silent_seconds=job_recovery.STALE_SECONDS + 1)
        verdict = job_recovery.explain_staleness(stale, now=now)
        assert verdict.dead is True
        assert verdict.reason == job_recovery.REASON_HEARTBEAT
        assert verdict.threshold_seconds == job_recovery.STALE_SECONDS

    @pytest.mark.parametrize("split_mode", [PdfSplitMode.PAGE_SPLIT, PdfSplitMode.MANUAL_SPLIT])
    def test_非内容分析任务不套用阶段预算(self, split_mode: str) -> None:
        """手工/按页拆分是单任务 + 集群默认 timeout，stage 停在 extract 不代表有 1200s。

        集群默认值可被 `DJANGO_Q_TIMEOUT` 调到比 1200 更大，套用阶段预算就会把
        **还在跑**的任务判死——所以这条必须回落到心跳判据。
        """
        now = timezone.now()
        not_stale = _job(now=now, split_mode=split_mode, silent_seconds=_ACCIDENT_SILENT)
        verdict = job_recovery.explain_staleness(not_stale, now=now)
        assert verdict.dead is False
        assert verdict.stage_budget_seconds is None

        stale = _job(now=now, split_mode=split_mode, silent_seconds=job_recovery.STALE_SECONDS + 1)
        assert job_recovery.explain_staleness(stale, now=now).reason == job_recovery.REASON_HEARTBEAT

    def test_显式传空表关闭第二判据(self) -> None:
        """`stage_timeouts={}` = 只看心跳（改动前的行为，运维的逃生阀）。"""
        now = timezone.now()
        job = _job(now=now, silent_seconds=_ACCIDENT_SILENT)

        with _patch_queryset([job]):
            assert job_recovery.find_stale_jobs(now=now, stage_timeouts={}) == []

    def test_超长静默仍按硬超时归因而不是心跳(self) -> None:
        """两条判据同时成立时报更硬的证据（硬超时），运维才知道是预算被烧完。"""
        now = timezone.now()
        job = _job(now=now, silent_seconds=job_recovery.STALE_SECONDS + 600)

        verdict = job_recovery.explain_staleness(job, now=now)
        assert verdict.dead is True
        assert verdict.reason == job_recovery.REASON_HARD_TIMEOUT


class TestStageBudgetSourceOfTruth:
    """映射必须来自 `two_stage.py` 的提交常量——小于真实预算就会误杀活任务。"""

    def test_映射值等于提交常量(self) -> None:
        mapping = job_recovery.default_stage_timeouts()
        assert mapping["extract"] == EXTRACT_STAGE_TIMEOUT_SECONDS
        assert mapping["cross_check"] == CROSS_CHECK_STAGE_TIMEOUT_SECONDS
        assert mapping["segment"] == SEGMENT_STAGE_TIMEOUT_SECONDS

    def test_余量大于django_q的guard缓冲且远小于误杀代价(self) -> None:
        """余量要盖住 django-q 的 `timer.value = timeout + 3` 与 guard 轮询抖动。

        下界 60s：留出 SIGALRM 投递延迟 + guard 一轮 scheduler；
        上界 600s：再多就失去「更早恢复」的意义（重跑一次云端 OCR 要十几分钟）。
        """
        assert 60 <= job_recovery.STAGE_DEAD_GRACE_SECONDS <= 600

    def test_extract的判死阈值确实早于心跳阈值(self) -> None:
        """修复的实际收益就在这里：extract 在「预算 + 余量」处就能判死，而不是等满 1800s。

        ⚠️ 这条断言绑的是**当前预算配置**（事故当时 1200s → 1320s，比 1800s 早 8 分钟）。
        哪天 `extract` 预算被调大到「预算 + 余量 ≥ 1800s」，本用例会红——那是提醒
        重新评估 `STALE_SECONDS` 与预算的关系，**不要**通过放宽容差来消红。
        """
        budget = job_recovery.default_stage_timeouts()["extract"]
        threshold = budget + job_recovery.STAGE_DEAD_GRACE_SECONDS
        assert threshold < job_recovery.STALE_SECONDS, (
            f"extract 判死阈值 {threshold}s 已不早于 {job_recovery.STALE_SECONDS}s"
        )


class TestVerdictIsActionable:
    """判死原因必须能让人一眼分清「网络断了」还是「云端把预算烧完了」。"""

    def test_硬超时原因带阶段预算与最后进度(self) -> None:
        now = timezone.now()
        job = _job(now=now, silent_seconds=_ACCIDENT_SILENT, progress=100, processed_pages=93, total_pages=93)

        text = job_recovery.explain_staleness(job, now=now).describe()

        assert "硬超时" in text
        assert "stage=extract" in text
        assert f"预算 {EXTRACT_STAGE_TIMEOUT_SECONDS}s" in text
        assert "最后进度 93/93 页" in text
        assert "progress=100%" in text
        # 不能混进心跳口径，否则运维会误判成网络问题
        assert "心跳超时" not in text

    def test_心跳原因不被误标成硬超时(self) -> None:
        now = timezone.now()
        job = _job(now=now, stage="done", silent_seconds=job_recovery.STALE_SECONDS + 60, processed_pages=12)

        text = job_recovery.explain_staleness(job, now=now).describe()

        assert "心跳超时" in text
        assert "硬超时" not in text
        assert f"阈值 {job_recovery.STALE_SECONDS}s" in text


class TestReasonLandsInErrorMessage:
    """判死原因必须落库：事故复盘时只有 DB 行可看。"""

    def _verdict(self, **kwargs: Any) -> job_recovery.StalenessVerdict:
        now = timezone.now()
        job = _job(now=now, silent_seconds=_ACCIDENT_SILENT, progress=100, processed_pages=93, total_pages=93, **kwargs)
        return job_recovery.explain_staleness(job, now=now)

    def test_重排把原因写进error_message(self) -> None:
        job = _job(silent_seconds=_ACCIDENT_SILENT, processed_pages=93, progress=100)
        verdict = self._verdict()

        with (
            patch.object(job_recovery, "build_task_submission_service") as builder,
            patch.object(job_recovery.PdfSplitJob.objects, "filter") as flt,
        ):
            builder.return_value.submit.return_value = "task-abc"
            action = job_recovery._requeue(job, reason=verdict.describe())

        message = flt.return_value.update.call_args.kwargs["error_message"]
        assert "硬超时" in message
        assert "stage=extract" in message
        assert "93/93" in message
        assert "重排续跑" in message
        assert "requeued" in action
        # 重排次数照旧要涨，否则 MAX_RECOVERY_ATTEMPTS 永远不生效
        assert flt.return_value.update.call_args.kwargs["recovery_attempts"] == 1

    def test_转待复核把原因写进error_message(self) -> None:
        job = _job(silent_seconds=_ACCIDENT_SILENT, has_segments=True, segments=7)
        verdict = self._verdict()

        with patch.object(job_recovery.PdfSplitJob.objects, "filter") as flt:
            action = job_recovery._salvage_as_review(job, reason=verdict.describe())

        message = flt.return_value.update.call_args.kwargs["error_message"]
        assert "硬超时" in message
        assert "7 个分段" in message
        assert "待复核" in message
        assert "salvaged_as_review" in action

    def test_标记失败把原因写进error_message(self) -> None:
        job = _job(silent_seconds=_ACCIDENT_SILENT, recovery_attempts=job_recovery.MAX_RECOVERY_ATTEMPTS)
        verdict = self._verdict()

        with patch.object(job_recovery.PdfSplitJob.objects, "filter") as flt:
            action = job_recovery._mark_failed_after_retries(job, reason=verdict.describe())

        message = flt.return_value.update.call_args.kwargs["error_message"]
        assert "硬超时" in message
        assert "已停止自动恢复" in message
        assert action == "marked_failed_after_retries"

    def test_不传verdict时与改动前一致(self) -> None:
        """直接对单个任务手动收尾（无判死结论）时，仍然是「清空错误、只重排」。"""
        job = _job(silent_seconds=_ACCIDENT_SILENT)

        with (
            patch.object(job_recovery, "build_task_submission_service") as builder,
            patch.object(job_recovery.PdfSplitJob.objects, "filter") as flt,
        ):
            builder.return_value.submit.return_value = "task-abc"
            job_recovery._requeue(job)

        assert flt.return_value.update.call_args.kwargs["error_message"] == ""

    def test_recover_job把判死原因传给收尾动作(self) -> None:
        """链路要通：sweep → recover_job → 收尾动作都必须带着原因。"""
        job = _job(silent_seconds=_ACCIDENT_SILENT)
        verdict = self._verdict()

        with patch.object(job_recovery, "_requeue", return_value="requeued") as requeue:
            assert job_recovery.recover_job(job, verdict=verdict) == "requeued"

        assert requeue.call_args.kwargs["reason"] == verdict.describe()


@pytest.mark.django_db
class TestAgainstRealRows:
    """判据在真实 ORM 行上同样成立（`stage`/`progress` 是真 str/int，不是测试替身）。"""

    def test_真实行_事故现场会被找到且带全现场(self) -> None:
        now = timezone.now()
        stuck = _backdate(_real_job(), now=now, silent_seconds=_ACCIDENT_SILENT)

        assert job_recovery.find_stale_jobs(now=now) == [stuck]

        verdict = job_recovery.explain_staleness(stuck, now=now)
        assert verdict.reason == job_recovery.REASON_HARD_TIMEOUT
        assert verdict.stage == PdfSplitStage.EXTRACT
        assert (verdict.progress, verdict.processed_pages, verdict.total_pages) == (100, 93, 93)

    def test_真实行_预算未烧完不判死(self) -> None:
        now = timezone.now()
        running = _backdate(_real_job(), now=now, silent_seconds=EXTRACT_STAGE_TIMEOUT_SECONDS + 1)

        assert job_recovery.find_stale_jobs(now=now) == []
        assert job_recovery.explain_staleness(running, now=now).dead is False

    def test_真实行_老数据无心跳也能按硬超时判死(self) -> None:
        """事故前后可能有一批 `heartbeat_at` 为空的老行：回落 `updated_at` 仍须生效。"""
        now = timezone.now()
        legacy = _backdate(_real_job(), now=now, silent_seconds=_ACCIDENT_SILENT, keep_heartbeat=False)

        assert legacy.heartbeat_at is None
        assert job_recovery.find_stale_jobs(now=now) == [legacy]
        assert job_recovery.explain_staleness(legacy, now=now).reason == job_recovery.REASON_HARD_TIMEOUT


class TestSweepLogsTheReason:
    """日志必须带阶段 + 硬超时 + 最后进度（事故时「只看得到心跳停了」）。"""

    def test_日志记录判死依据与现场(self) -> None:
        now = timezone.now()
        job = _job(now=now, silent_seconds=_ACCIDENT_SILENT, progress=100, processed_pages=93, total_pages=93)

        with (
            patch.object(job_recovery, "find_stale_jobs", return_value=[job]),
            patch.object(job_recovery, "recover_job", return_value="requeued"),
            patch.object(job_recovery.logger, "warning") as warning,
            patch.object(job_recovery.logger, "exception"),
        ):
            result = job_recovery.sweep_stale_jobs(now=now)

        extra = warning.call_args.kwargs["extra"]
        assert extra["reason"] == job_recovery.REASON_HARD_TIMEOUT
        assert extra["stage"] == "extract"
        assert extra["stage_budget_seconds"] == EXTRACT_STAGE_TIMEOUT_SECONDS
        assert extra["threshold_seconds"] == EXTRACT_STAGE_TIMEOUT_SECONDS + job_recovery.STAGE_DEAD_GRACE_SECONDS
        assert extra["silent_seconds"] == int(_ACCIDENT_SILENT)
        assert extra["progress"] == 100
        assert extra["processed_pages"] == 93
        assert extra["total_pages"] == 93
        assert "硬超时" in extra["verdict"]

        assert result["stale_found"] == 1
        assert result["actions"][0]["reason"] == job_recovery.REASON_HARD_TIMEOUT
        assert result["actions"][0]["stage"] == "extract"

    def test_巡检路径的判死原因也落进error_message(self) -> None:
        """`sweep → recover_job` 的结论传递：走 `job.staleness_verdict`，不动裸调用签名。

        `recover_job(job)` 是既有调用方（含测试替身）依赖的签名，所以巡检路径
        不能靠额外 kwarg；这条用例锁住「属性传递」那条路真的通。
        """
        now = timezone.now()
        job = _job(now=now, silent_seconds=_ACCIDENT_SILENT, progress=100, processed_pages=93)

        with (
            patch.object(job_recovery, "find_stale_jobs", return_value=[job]),
            patch.object(job_recovery, "build_task_submission_service") as builder,
            patch.object(job_recovery.PdfSplitJob.objects, "filter") as flt,
            patch.object(job_recovery.logger, "warning"),
        ):
            builder.return_value.submit.return_value = "task-xyz"
            result = job_recovery.sweep_stale_jobs(now=now)

        message = flt.return_value.update.call_args.kwargs["error_message"]
        assert "硬超时" in message
        assert "stage=extract" in message
        assert "重排续跑" in message
        assert result["actions"][0]["action"].startswith("requeued")
