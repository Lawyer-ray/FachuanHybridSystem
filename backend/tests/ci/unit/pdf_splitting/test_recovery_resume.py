"""看门狗的「重排入口选择」与「调度注册」单测。

## 这两个用例存在的原因

看门狗（`job_recovery.sweep_stale_jobs`）写得很完整，但有两个缺口会让
「断网 / 合盖 / worker 被杀后任务自动恢复」这个承诺落空：

### 缺口一：重排会静默丢掉双引擎

`_requeue` 原先一律提交 `execute_pdf_split_job`（旧全量路径 →
`analyze_job` → `pipeline.analyze_pdf`），而那条路径**不包含 `cross_check_stage`**。
于是双引擎任务被重排后会退化成单引擎：任务照样跑完、照样出分段，
**比对结果凭空消失，律师侧看不出任何异常**。

更隐蔽的是——旧路径本身就是为了绕开 600s 硬超时才被拆掉的（164 页实测
499s 被杀）。重排走回去等于等剂量地再死一次。

所以这里锁住：重排必须按 `job.stage` 选续跑入口。

### 缺口二：看门狗根本没被调度

函数在、管理命令在，但 Django-Q 的计划任务表里没有任何一条在调度它。
结果就是任务永远停在 `processing`，必须有人想起来手工跑命令。
这里锁住「调度能被注册、且重复调用幂等」。
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import patch

import pytest

from apps.pdf_splitting.models import PdfSplitJob, PdfSplitJobStatus, PdfSplitMode, PdfSplitSourceType, PdfSplitStage
from apps.pdf_splitting.services import job_recovery
from apps.pdf_splitting.services.recovery_schedule import (
    WATCHDOG_FUNC,
    WATCHDOG_INTERVAL_MINUTES,
    WATCHDOG_SCHEDULE_NAME,
    register_watchdog_schedule,
    run_watchdog,
)
from apps.pdf_splitting.services.split.two_stage import (
    CROSS_CHECK_STAGE_TIMEOUT_SECONDS,
    EXTRACT_STAGE_TIMEOUT_SECONDS,
    SEGMENT_STAGE_TIMEOUT_SECONDS,
)

pytestmark = pytest.mark.django_db

_SUBMIT_PATH = "apps.pdf_splitting.services.job_recovery.build_task_submission_service"
_TASK_EXTRACT = "apps.pdf_splitting.tasks.run_extract_stage"
_TASK_CROSS_CHECK = "apps.pdf_splitting.tasks.run_cross_check_stage"
_TASK_SEGMENT = "apps.pdf_splitting.tasks.run_segment_stage"
_TASK_LEGACY = "apps.pdf_splitting.tasks.execute_pdf_split_job"


def _job(
    *,
    stage: str = PdfSplitStage.EXTRACT,
    split_mode: str = PdfSplitMode.CONTENT_ANALYSIS,
    attempts: int = 0,
) -> PdfSplitJob:
    return PdfSplitJob.objects.create(
        id=uuid.uuid4(),
        source_type=PdfSplitSourceType.UPLOAD,
        source_original_name="重排示例.pdf",
        status=PdfSplitJobStatus.PROCESSING,
        split_mode=split_mode,
        stage=stage,
        total_pages=20,
        recovery_attempts=attempts,
    )


class TestResumeTaskEntry:
    """重排必须按阶段选入口——选错就是静默丢结果或二次超时。"""

    def test_cross_check阶段续跑比对而不是旧全量路径(self) -> None:
        """这是本文件最要紧的一条：双引擎任务被重排后仍是双引擎。"""
        job = _job(stage=PdfSplitStage.CROSS_CHECK)
        path, name, timeout = job_recovery._resume_task_for(job)

        assert path == _TASK_CROSS_CHECK
        assert path != _TASK_LEGACY, "走旧路径 = 双引擎比对静默丢失"
        assert "cross_check" in name
        assert timeout == CROSS_CHECK_STAGE_TIMEOUT_SECONDS

    def test_segment阶段只续跑分段(self) -> None:
        """取字与比对都已落盘，重跑它们等于把云端费用再付一次。"""
        job = _job(stage=PdfSplitStage.SEGMENT)
        path, name, timeout = job_recovery._resume_task_for(job)

        assert path == _TASK_SEGMENT
        assert "segment" in name
        assert timeout == SEGMENT_STAGE_TIMEOUT_SECONDS

    @pytest.mark.parametrize("stage", [PdfSplitStage.EXTRACT, PdfSplitStage.DONE])
    def test_extract及其它阶段从取字重新开始(self, stage: str) -> None:
        job = _job(stage=stage)
        path, _name, timeout = job_recovery._resume_task_for(job)

        assert path == _TASK_EXTRACT
        assert timeout == EXTRACT_STAGE_TIMEOUT_SECONDS

    @pytest.mark.parametrize("mode", [PdfSplitMode.MANUAL_SPLIT, PdfSplitMode.PAGE_SPLIT])
    def test_非内容分析任务仍走旧全量入口(self, mode: str) -> None:
        """手工拆分/按页拆分本来就是单一任务，没有阶段可复原。"""
        job = _job(split_mode=mode)
        path, _name, timeout = job_recovery._resume_task_for(job)

        assert path == _TASK_LEGACY
        # 旧全量路径不归我们管预算，保持集群默认值
        assert timeout is None

    def test_requeue实际提交选中的入口(self) -> None:
        """不能只测选择函数——要确认 `_requeue` 真的用它去 submit。"""
        job = _job(stage=PdfSplitStage.CROSS_CHECK)
        with patch(_SUBMIT_PATH) as submit:
            submit.return_value.submit.return_value = "task-abc"
            action = job_recovery._requeue(job)

        submitted = submit.return_value.submit.call_args.args[0]
        assert submitted == _TASK_CROSS_CHECK
        assert "cross_check" in action
        # 重排必须带上该阶段的预算：不传就会退回集群默认 600s，等于救回来再杀一次
        assert submit.return_value.submit.call_args.kwargs["timeout"] == CROSS_CHECK_STAGE_TIMEOUT_SECONDS

        job.refresh_from_db()
        assert job.status == PdfSplitJobStatus.PENDING
        assert job.recovery_attempts == 1
        assert job.task_id == "task-abc"


class TestWatchdogSchedule:
    """看门狗必须真的被排进 Django-Q，否则「自动恢复」只是文档上的说法。"""

    def test_注册后计划任务存在(self) -> None:
        from django_q.models import Schedule

        Schedule.objects.filter(name=WATCHDOG_SCHEDULE_NAME).delete()
        register_watchdog_schedule()

        entry = Schedule.objects.get(name=WATCHDOG_SCHEDULE_NAME)
        assert entry.func == WATCHDOG_FUNC
        assert entry.minutes == WATCHDOG_INTERVAL_MINUTES

    def test_重复注册不产生第二条(self) -> None:
        """app ready 每次启动都会调一次，不幂等就会越积越多。"""
        from django_q.models import Schedule

        Schedule.objects.filter(name=WATCHDOG_SCHEDULE_NAME).delete()
        register_watchdog_schedule()
        register_watchdog_schedule()
        register_watchdog_schedule()

        assert Schedule.objects.filter(name=WATCHDOG_SCHEDULE_NAME).count() == 1

    def test_注册失败不抛出(self) -> None:
        """app ready 阶段数据库可能未就绪；抛了会让整个 app 加载失败。"""

        class _Boom:
            def schedule_exists(self, _name: str) -> bool:
                raise RuntimeError("db not ready")

        with patch("apps.core.tasking.ScheduleQueryService", return_value=_Boom()):
            register_watchdog_schedule()  # 不应抛出

    def test_定时入口会调用看门狗(self) -> None:
        with patch.object(job_recovery, "sweep_stale_jobs", return_value={"stale_found": 0, "actions": []}) as sweep:
            result = run_watchdog()

        sweep.assert_called_once()
        assert result["stale_found"] == 0

    def test_定时入口吞掉异常(self) -> None:
        """后台定时任务抛异常只会让 Django-Q 记一条失败，对恢复毫无帮助。"""
        with patch.object(job_recovery, "sweep_stale_jobs", side_effect=RuntimeError("boom")):
            result = run_watchdog()

        assert result == {"error": "sweep_failed"}

    def test_什么都没扫到时返回原样(self) -> None:
        with patch.object(job_recovery, "sweep_stale_jobs", return_value={"stale_found": 1, "actions": [{"a": 1}]}):
            result: dict[str, Any] = run_watchdog()

        assert result["stale_found"] == 1
