"""交叉比对 / 分段这两个长阻塞阶段的进度可见性单测。

背景（也是这些用例存在的理由）：164 页卷宗上，取字做完时 `processed_pages`
已经是 164/164、`progress=100`；之后交叉比对（整本再解析一遍）与 LLM 分段
合计要十几分钟，期间 DB 一行不写。前端看到的是「100% 假死」，看门狗
（`job_recovery`）还会把这些正常慢任务判死并重排——整份卷宗的云端费用白花。

本模块锁住三件事：

1. `periodic_heartbeat` 确实在阻塞期间刷新心跳，并且**退出后停止**（不留线程续命）；
2. 心跳线程写库失败不能把主流程带崩；
3. 双引擎阶段真的把 stage 切到 cross_check、进度让出 90→99，收工再还原。
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from django.utils import timezone

from apps.pdf_splitting.models import PdfSplitJob, PdfSplitJobStatus, PdfSplitSourceType, PdfSplitStage
from apps.pdf_splitting.services import heartbeat as heartbeat_module

# transaction=True：心跳对话是在**另一个线程/连接**里写的。默认的 django_db 把整个
# 用例包在一个未提交事务里，别的连接看不到这条用例建的行（实测 update rowcount=0），
# 心跳看上去就像「没生效」。真环境里 worker 写库也不该藏在别人的事务里，所以这里
# 用不带事务包裹的模式更贴近现实。
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _isolated_media_root(tmp_path: Path, settings: Any) -> Path:
    """把 MEDIA_ROOT 钉到临时目录。

    本模块测的阶段切换本身不写盘，但 `PdfSplitService` 构造时就会碰存储层
    （`PdfSplitStorage`）。仓库曾因测试没隔离 MEDIA_ROOT 把开发环境的真实
    media 目录删掉（47 个任务目录，含两份在用卷宗），所以这里一律隔离，
    不给任何用例碰真实 media 的机会。
    """
    settings.MEDIA_ROOT = tmp_path / "media"
    return tmp_path


def _make_job(
    *,
    name: str = "卷宗.pdf",
    status: str = PdfSplitJobStatus.PROCESSING,
    stage: str = PdfSplitStage.EXTRACT,
    progress: int = 100,
    pages: int = 164,
    dual_engines: str = "",
) -> PdfSplitJob:
    return PdfSplitJob.objects.create(
        id=uuid4(),
        source_type=PdfSplitSourceType.UPLOAD,
        source_original_name=name,
        status=status,
        stage=stage,
        progress=progress,
        total_pages=pages,
        processed_pages=pages,
        current_page=pages,
        dual_engines=dual_engines,
    )


class TestPeriodicHeartbeat:
    def test_refreshes_heartbeat_while_blocked(self) -> None:
        """阻塞段里心跳必须往前走——否则看门狗会把在跑的任务判死。"""
        job = _make_job()
        old = timezone.now() - timedelta(hours=1)
        PdfSplitJob.objects.filter(id=job.id).update(heartbeat_at=old, updated_at=old)

        with heartbeat_module.periodic_heartbeat(job.id, interval=0.05):
            time.sleep(0.25)

        job.refresh_from_db()
        assert job.heartbeat_at is not None
        # PG 连接时区是 Asia/Shanghai，读回来是 +08:00；比较前先折算到 UTC。
        assert job.heartbeat_at.astimezone(UTC) > old

    def test_stops_after_block_exits(self) -> None:
        """退出后线程必须停：留着的线程会给已结束的任务续命，看门狗永远看不出它死了。"""
        job = _make_job()
        with heartbeat_module.periodic_heartbeat(job.id, interval=0.05):
            time.sleep(0.2)

        job.refresh_from_db()
        after_exit = job.heartbeat_at
        assert after_exit is not None

        # 再等几个间隔，心跳不该继续被推着走
        time.sleep(0.3)
        job.refresh_from_db()
        assert job.heartbeat_at == after_exit
        assert not [t for t in threading.enumerate() if t.name == f"pdf-split-heartbeat-{job.id}"]

    def test_thread_name_identifies_job(self) -> None:
        job = _make_job()
        with heartbeat_module.periodic_heartbeat(job.id, interval=5):
            names = [t.name for t in threading.enumerate()]
        assert f"pdf-split-heartbeat-{job.id}" in names

    def test_db_error_does_not_break_main_flow(self) -> None:
        """心跳只是存活信号，写库抖动不能把整份卷宗任务弄失败。

        光「没抛异常」不能证明它真的在循环重试——那样一个开场即死的线程也会「通过」。
        所以额外断言它确实被**多次**调用过：错了就记日志继续，而不是错一次就放弃。
        """
        job = _make_job()
        with patch.object(
            heartbeat_module, "touch_heartbeat", side_effect=RuntimeError("db hiccup")
        ) as touch:
            with heartbeat_module.periodic_heartbeat(job.id, interval=0.05):
                time.sleep(0.25)

        # 异常没有从 with 块逃出去（否则这条用例根本到不了这里）
        # 且线程确实坚持重试（0.25s / 0.05s ≈ 5 次，留余量取 >=2）
        assert touch.call_count >= 2


class TestTouchHeartbeat:
    def test_writes_both_timestamps(self) -> None:
        """`QuerySet.update()` 绕过 auto_now，两个时间字段都必须显式写。"""
        job = _make_job()
        old = timezone.now() - timedelta(hours=2)
        PdfSplitJob.objects.filter(id=job.id).update(heartbeat_at=old, updated_at=old)

        heartbeat_module.touch_heartbeat(job_id=job.id)

        job.refresh_from_db()
        assert job.heartbeat_at is not None and job.heartbeat_at.astimezone(UTC) > old
        assert job.updated_at.astimezone(UTC) > old


class _FakeOutcome:
    def __init__(self, summary: dict[str, Any]) -> None:
        self.summary = summary


class TestCrossCheckStage:
    """双引擎阶段必须报出阶段名并让出进度区段。"""

    def _service(self) -> Any:
        from apps.pdf_splitting.services.split.service import PdfSplitService

        return PdfSplitService()

    def _run(self, job: PdfSplitJob, run_dual_engine: Any) -> tuple[dict[str, Any], list[PdfSplitJob]]:
        """跑一次双引擎阶段，返回 (summary, 快照列表)。

        `run_dual_engine` / `plan_dual_engine_factories` 都替身掉：真实现要联网调
        云端，单测里既跑不起来也不该花钱。
        """
        snapshots: list[PdfSplitJob] = []
        service = self._service()
        with (
            patch("apps.pdf_splitting.services.split.service.run_dual_engine", side_effect=run_dual_engine),
            patch(
                "apps.pdf_splitting.services.split.service.plan_dual_engine_factories",
                return_value=([], ["textin"]),
            ),
        ):
            summary = service.cross_check_stage(job, pdf_path=Path("/tmp/fake.pdf"))
        return summary, snapshots

    def test_stage_and_progress_inside_and_outside(self) -> None:
        job = _make_job(dual_engines="mineru,paddleocr_vl")
        seen: dict[str, Any] = {}

        def fake_run(*_args: Any, **_kwargs: Any) -> _FakeOutcome:
            current = PdfSplitJob.objects.get(id=job.id)
            seen["stage"] = current.stage
            seen["progress"] = current.progress
            # processed_pages 是取字真实完成量，不能因为进入比对被回退
            seen["processed_pages"] = current.processed_pages
            return _FakeOutcome({"engine_disagreements": [], "dual_engine": {}})

        summary, _ = self._run(job, fake_run)

        # 比对进行中：阶段名是 cross_check，进度让出 90→99 这一段
        assert seen["stage"] == PdfSplitStage.CROSS_CHECK
        assert seen["progress"] == 90
        assert seen["processed_pages"] == 164

        # 收工后：进度推到 99。
        # **stage 刻意留在 cross_check**：本阶段已拆成独立任务，下一步由
        # two_stage.advance_to_segment_stage 写成 segment。若这里把 stage 写回
        # extract，任务链每推进一次都会先倒退一次，前端会看到阶段来回跳。
        job.refresh_from_db()
        assert job.stage == PdfSplitStage.CROSS_CHECK
        assert job.progress == 99
        assert summary["dual_engine"]["unavailable"] == ["textin"]

    def test_failure_keeps_stage_for_next_hop(self) -> None:
        """比对失败只记日志（分歧是附加信息），阶段不倒退。

        失败时任务仍要往下走分段（tasks.run_cross_check_stage 会兜住并推进），
        所以 stage 留在 cross_check 由推进函数改写是正确语义。
        """
        job = _make_job(dual_engines="mineru,paddleocr_vl")

        def boom(*_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("cloud down")

        summary, _ = self._run(job, boom)

        job.refresh_from_db()
        assert summary == {}
        assert job.stage == PdfSplitStage.CROSS_CHECK
        assert job.progress == 99

    def test_single_engine_is_noop(self) -> None:
        """只勾一个引擎时整段跳过：阶段与进度一字不动。"""
        job = _make_job(dual_engines="mineru")
        with patch("apps.pdf_splitting.services.split.service.run_dual_engine") as run_mock:
            summary, _ = self._run(job, run_mock)
        run_mock.assert_not_called()

        job.refresh_from_db()
        assert summary == {}
        assert job.stage == PdfSplitStage.EXTRACT
        assert job.progress == 100
