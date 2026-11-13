"""卡死任务自救机制的单元测试。

背景：某个 164 页真实卷宗任务因 qcluster 被 watchfiles 重启而中断，
数据库停在 processing、无 error_message，前端无限轮询。本模块锁住三件事：

1. 判活口径：心跳优先，超过阈值才算死；
2. 收尾口径：**有分段才转待复核**，没分段一律重排（因为分段是最后才落库的，
   processed_pages 大不代表有成果可交）；
3. 重排上限：反复失败必须停手，不能无限打满队列。
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.pdf_splitting.services import job_recovery


def _job(base: Any = None, **kwargs: Any) -> MagicMock:
    """构造一个足够真实的 job 替身（只带 job_recovery 用到的属性）。

    未显式指定的时间字段统一取同一个 `base`，避免 `_last_liveness` 的 max()
    被测试龫造时新算的 now 干扰（这本身就是它想要的行为，但测试必须可控）。
    """
    base = base or timezone.now()
    defaults = {
        "id": "11111111-1111-1111-1111-111111111111",
        "status": "processing",
        "processed_pages": 0,
        "total_pages": 164,
        "recovery_attempts": 0,
        "heartbeat_at": base,
        "updated_at": base,
        "started_at": base,
        "created_at": base,
    }
    defaults.update(kwargs)
    job = MagicMock()
    for key, value in defaults.items():
        setattr(job, key, value)
    # 默认「没有分段」——大多数卡死任务都还没走到 _persist_page_split
    job.segments.exists.return_value = False
    job.segments.count.return_value = 0
    return job


class TestLastLiveness:
    """判活必须优先看心跳。"""

    def test_heartbeat_wins_over_stale_updated_at(self) -> None:
        now = timezone.now()
        long_ago = now - timedelta(hours=2)
        job = _job(base=long_ago, heartbeat_at=now, updated_at=long_ago)
        assert job_recovery._last_liveness(job) == now

    def test_falls_back_to_updated_at_when_no_heartbeat(self) -> None:
        """老数据没有 heartbeat_at，不能因此判成「没有存活信号」。"""
        old = timezone.now() - timedelta(minutes=30)
        job = _job(base=old, heartbeat_at=None, updated_at=old, started_at=None)
        assert job_recovery._last_liveness(job) == old

    def test_none_everything_returns_none(self) -> None:
        job = _job(heartbeat_at=None, updated_at=None, started_at=None, created_at=None)
        assert job_recovery._last_liveness(job) is None


def _stub_queryset(jobs: list[MagicMock]) -> MagicMock:
    """把 PdfSplitJob.objects.filter(...) 链替换成一个可迭代的假 QuerySet。

    真实实现是 `objects.filter(...).filter(...)`，两层链都返回 QuerySet，
    所以这里用 MagicMock 让链式调用和迭代都成立。
    """
    queryset = MagicMock()
    queryset.filter.return_value = queryset
    queryset.__iter__ = lambda _self: iter(jobs)
    return queryset


class TestFindStaleJobs:
    """只挑 processing 且心跳停了的任务。"""

    def test_recent_heartbeat_is_not_stale(self) -> None:
        now = timezone.now()
        fresh = now - timedelta(seconds=30)
        job = _job(base=fresh, heartbeat_at=fresh)

        with patch.object(job_recovery.PdfSplitJob.objects, "filter", return_value=_stub_queryset([job])):
            assert job_recovery.find_stale_jobs(now=now) == []

    def test_old_heartbeat_is_stale(self) -> None:
        now = timezone.now()
        old = now - timedelta(seconds=job_recovery.STALE_SECONDS + 60)
        job = _job(base=old, heartbeat_at=old)

        with patch.object(job_recovery.PdfSplitJob.objects, "filter", return_value=_stub_queryset([job])):
            assert job_recovery.find_stale_jobs(now=now) == [job]


class TestRecoverJob:
    """三种收尾动作的选取规则——本模块最核心的不变量。"""

    def test_no_segments_requeues_even_with_page_progress(self) -> None:
        """⚠️ 核心回归：processed_pages 很大但 segments 为空时必须重排。

        真实踩过：某次任务显示 135/164 页，但 segments=0（分段是全部解析完
        才 bulk_create 的）。旧逻辑据 processed_pages>0 判「有成果」，结果把一个
        空壳转成待复核，律师打开看到空列表。
        """
        job = _job(processed_pages=135, total_pages=164)
        job.segments.exists.return_value = False

        with patch.object(job_recovery, "_requeue", return_value="requeued") as requeue:
            assert job_recovery.recover_job(job) == "requeued"
            requeue.assert_called_once()

    def test_with_segments_salvages_as_review(self) -> None:
        job = _job(processed_pages=164, total_pages=164)
        job.segments.exists.return_value = True

        with patch.object(job_recovery, "_salvage_as_review", return_value="salvaged") as salvage:
            assert job_recovery.recover_job(job) == "salvaged"
            salvage.assert_called_once()

    def test_gives_up_after_max_attempts(self) -> None:
        """反复失败必须停手，否则坏输入会无限循环打满队列。"""
        job = _job(recovery_attempts=job_recovery.MAX_RECOVERY_ATTEMPTS)

        with patch.object(job_recovery, "_mark_failed_after_retries", return_value="failed") as mark:
            assert job_recovery.recover_job(job) == "failed"
            mark.assert_called_once()


class TestSweepIsolatesFailures:
    """单个任务拯救出错不能拖垮整轮巡检。"""

    def test_one_error_does_not_abort_the_sweep(self) -> None:
        bad = _job(id="bad")
        good = _job(id="good")

        def fake_recover(job: Any) -> str:
            if job.id == "bad":
                raise RuntimeError("boom")
            return "requeued"

        with (
            patch.object(job_recovery, "find_stale_jobs", return_value=[bad, good]),
            patch.object(job_recovery, "recover_job", side_effect=fake_recover),
        ):
            result = job_recovery.sweep_stale_jobs()

        assert result["stale_found"] == 2
        actions = {item["job_id"]: item["action"] for item in result["actions"]}
        assert actions["bad"] == "error"
        assert actions["good"] == "requeued"

    def test_respects_limit(self) -> None:
        jobs = [_job(id=str(index)) for index in range(10)]
        with (
            patch.object(job_recovery, "find_stale_jobs", return_value=jobs),
            patch.object(job_recovery, "recover_job", return_value="requeued"),
        ):
            result = job_recovery.sweep_stale_jobs(limit=3)

        assert len(result["actions"]) == 3


class TestAttemptsIncrement:
    """重排必须留下次数痕迹，否则 MAX_RECOVERY_ATTEMPTS 永远不生效。"""

    def test_requeue_bumps_attempts(self) -> None:
        job = _job(recovery_attempts=0)
        with (
            patch.object(job_recovery, "build_task_submission_service", create=True) as builder,
            patch.object(job_recovery.PdfSplitJob.objects, "filter") as flt,
        ):
            builder.return_value.submit.return_value = "task-123"
            action = job_recovery._requeue(job)

        # 动作串里应能看到 attempt=1
        assert "attempt=1" in action
        # 写库参数里必须带 recovery_attempts=1
        assert flt.return_value.update.call_args.kwargs["recovery_attempts"] == 1


@pytest.mark.parametrize("stale_seconds", [60, 600, 3600])
def test_threshold_is_configurable(stale_seconds: int) -> None:
    """阈值必须可调：不同部署的云端识别耗时差异很大。"""
    now = timezone.now()
    old = now - timedelta(seconds=stale_seconds + 1)
    job = _job(base=old, heartbeat_at=old)
    with patch.object(job_recovery.PdfSplitJob.objects, "filter", return_value=_stub_queryset([job])):
        assert job_recovery.find_stale_jobs(now=now, stale_seconds=stale_seconds) == [job]
