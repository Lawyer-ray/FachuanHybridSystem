"""`find_inflight_job` 与 `elapsed_seconds` 的单测。

两件事的存在理由：

1. **幽灵任务**：任务一旦发起就只活在发起页面的内存里。换浏览器/刷新/同事先跑过
   一次，阅读器毫不知情会再建一个，同一份 164 页卷宗并行跑两遍（钱翻倍）。
   `find_inflight_job` 让前端能接管「别人发起的、还在跑的」那个任务。
2. **已耗时**：前端要显示「已耗时 6 分 12 秒」。终态后这个数字必须**停止增长**，
   否则律师刷新页面会以为任务没结束。
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from django.utils import timezone

from apps.pdf_splitting.models import PdfSplitJob, PdfSplitJobStatus, PdfSplitSourceType, PdfSplitStage
from apps.pdf_splitting.services.job_service import PdfSplitJobService, _elapsed_seconds_for
from apps.testing.factories import LawyerFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _isolated_media_root(tmp_path: Path, settings: Any) -> Path:
    """把 MEDIA_ROOT 钉到临时目录，绝不碰开发环境真实 media。

    本模块只用 DB，但 `build_job_payload` 会读 storage 下的 Markdown 产物路径；
    隔离后即使将来有人给用例加了落盘断言，也不会写/删到真实目录。
    """
    settings.MEDIA_ROOT = tmp_path / "media"
    return tmp_path


def _make_job(
    *,
    name: str = "卷宗.pdf",
    status: str = PdfSplitJobStatus.PROCESSING,
    pages: int = 164,
    cancel_requested: bool = False,
    minutes_ago: int = 0,
    stage: str = PdfSplitStage.EXTRACT,
    created_by: Any = None,
    pack_message_id: int | None = None,
) -> PdfSplitJob:
    job = PdfSplitJob.objects.create(
        id=uuid4(),
        source_type=PdfSplitSourceType.UPLOAD,
        source_original_name=name,
        pack_message_id=pack_message_id,
        status=status,
        stage=stage,
        total_pages=pages,
        processed_pages=pages,
        current_page=pages,
        cancel_requested=cancel_requested,
        created_by=created_by,
    )
    if minutes_ago:
        # created_at 是 auto_now_add，只能绕过 save() 回填
        PdfSplitJob.objects.filter(id=job.id).update(created_at=timezone.now() - timedelta(minutes=minutes_ago))
        job.refresh_from_db()
    return job


class TestFindInflightJob:
    def test_finds_processing_job(self) -> None:
        job = _make_job(status=PdfSplitJobStatus.PROCESSING)
        found = PdfSplitJobService().find_inflight_job(source_name="卷宗.pdf")
        assert found is not None and found.id == job.id

    def test_finds_pending_job(self) -> None:
        """还在排队（pending）也算进行中：worker 只是还没捡起来。"""
        job = _make_job(status=PdfSplitJobStatus.PENDING)
        found = PdfSplitJobService().find_inflight_job(source_name="卷宗.pdf")
        assert found is not None and found.id == job.id

    @pytest.mark.parametrize(
        "status",
        [
            PdfSplitJobStatus.REVIEW_REQUIRED,
            PdfSplitJobStatus.COMPLETED,
            PdfSplitJobStatus.FAILED,
            PdfSplitJobStatus.CANCELLED,
        ],
    )
    def test_ignores_settled_jobs(self, status: str) -> None:
        """终态不该被当成「进行中」——那会让前端去轮询一个已经结束的任务。"""
        _make_job(status=status)
        assert PdfSplitJobService().find_inflight_job(source_name="卷宗.pdf") is None

    def test_ignores_cancel_requested(self) -> None:
        """已按取消的任务马上就会变 cancelled，接管它只会白转圈。"""
        _make_job(status=PdfSplitJobStatus.PROCESSING, cancel_requested=True)
        assert PdfSplitJobService().find_inflight_job(source_name="卷宗.pdf") is None

    def test_total_pages_filter(self) -> None:
        """同名不同件：页数不符必须 miss，否则会接管别人的文件。"""
        _make_job(pages=164)
        service = PdfSplitJobService()
        assert service.find_inflight_job(source_name="卷宗.pdf", total_pages=164) is not None
        assert service.find_inflight_job(source_name="卷宗.pdf", total_pages=300) is None

    def test_returns_latest(self) -> None:
        """同一文件被并发发起两次时，接管最新那个（旧的大概已经没人看了）。"""
        _make_job(minutes_ago=10)
        newer = _make_job(minutes_ago=1)
        found = PdfSplitJobService().find_inflight_job(source_name="卷宗.pdf")
        assert found is not None and found.id == newer.id

    def test_other_source_name_miss(self) -> None:
        _make_job(name="别的卷宗.pdf")
        assert PdfSplitJobService().find_inflight_job(source_name="卷宗.pdf") is None

    def test_empty_source_name_returns_none(self) -> None:
        """没给文件名时宁可 miss，也不能返回「随便一个任务」。"""
        _make_job()
        assert PdfSplitJobService().find_inflight_job(source_name="") is None


class TestPackScopedMatching:
    """同名同页数的两份文件分属两个材料包时，**不许互相串**。

    2026-11-26 实测缺陷（用户报障）：律师打开材料包 601（37 页），底部进度条
    显示的却是材料包 617 那份任务的「0/37 页」——两个包里各有一份同名同页数的
    PDF（真实卷宗里极常见：都叫「材料.pdf」都 37 页）。旧口径只按
    「文件名 + 页数」匹配，而这两维**不唯一**，于是任务被认成了另一个包的。

    判据：包主键是「同一份文件」的权威认据；传了它就只认这个包提交的任务。
    存量任务这一列为 NULL，在传了包过滤时一律不命中（宁可少接管，不冒充）。
    """

    OTHER_PACK = 601
    MY_PACK = 617

    def test_inflight_只认自己的包(self) -> None:
        _make_job(name="材料.pdf", pages=37, pack_message_id=self.OTHER_PACK)
        mine = _make_job(name="材料.pdf", pages=37, pack_message_id=self.MY_PACK)

        found = PdfSplitJobService().find_inflight_job(
            source_name="材料.pdf", total_pages=37, pack_message_id=self.MY_PACK
        )

        assert found is not None and found.id == mine.id

    def test_inflight_只命中别的包时返回None(self) -> None:
        """这是用户看到的那个 bug：宁可没进度条，也不能显示另一个包的任务。"""
        _make_job(name="材料.pdf", pages=37, pack_message_id=self.OTHER_PACK)

        assert (
            PdfSplitJobService().find_inflight_job(source_name="材料.pdf", total_pages=37, pack_message_id=self.MY_PACK)
            is None
        )

    def test_inflight_存量任务包为空时在包过滤下一律不命中(self) -> None:
        _make_job(name="材料.pdf", pages=37, pack_message_id=None)

        assert (
            PdfSplitJobService().find_inflight_job(source_name="材料.pdf", total_pages=37, pack_message_id=self.MY_PACK)
            is None
        )

    def test_inflight_不传包过滤时保持旧口径(self) -> None:
        """老客户端 / 脚本不传包主键：退回「文件名 + 页数」，行为与改动前一致。"""
        job = _make_job(name="材料.pdf", pages=37, pack_message_id=None)

        found = PdfSplitJobService().find_inflight_job(source_name="材料.pdf", total_pages=37)

        assert found is not None and found.id == job.id

    def test_reusable_只认自己的包(self) -> None:
        owner = LawyerFactory()
        _make_job(
            name="材料.pdf",
            pages=37,
            pack_message_id=self.OTHER_PACK,
            status=PdfSplitJobStatus.REVIEW_REQUIRED,
            created_by=owner,
        )
        mine = _make_job(
            name="材料.pdf",
            pages=37,
            pack_message_id=self.MY_PACK,
            status=PdfSplitJobStatus.REVIEW_REQUIRED,
            created_by=owner,
        )

        found = PdfSplitJobService().find_reusable_job(
            source_name="材料.pdf",
            total_pages=37,
            user=owner,
            pack_message_id=self.MY_PACK,
        )

        assert found is not None and found.id == mine.id

    def test_reusable_只命中别的包时返回None(self) -> None:
        """复用错的包 = 把另一份材料的识别正文写进这个包的草稿，比多跑一遍贵得多。"""
        owner = LawyerFactory()
        _make_job(
            name="材料.pdf",
            pages=37,
            pack_message_id=self.OTHER_PACK,
            status=PdfSplitJobStatus.REVIEW_REQUIRED,
            created_by=owner,
        )

        assert (
            PdfSplitJobService().find_reusable_job(
                source_name="材料.pdf",
                total_pages=37,
                user=owner,
                pack_message_id=self.MY_PACK,
            )
            is None
        )


class TestElapsedSeconds:
    def test_none_without_started_at(self) -> None:
        """老数据/未开始时没有计时起点，返回 None 而不是编一个数字。"""
        job = _make_job()
        assert job.started_at is None
        assert _elapsed_seconds_for(job) is None

    def test_counts_from_started_while_processing(self) -> None:
        job = _make_job()
        PdfSplitJob.objects.filter(id=job.id).update(started_at=timezone.now() - timedelta(seconds=372))
        job.refresh_from_db()

        elapsed = _elapsed_seconds_for(job)
        assert elapsed is not None
        assert 370 <= elapsed <= 375

    def test_freezes_at_finished_for_terminal_status(self) -> None:
        """终态后必须停下：按 now 算的话，刷新页面会看到还在涨的「已耗时」。"""
        job = _make_job(status=PdfSplitJobStatus.REVIEW_REQUIRED)
        started = timezone.now() - timedelta(minutes=10)
        finished = started + timedelta(minutes=6)
        PdfSplitJob.objects.filter(id=job.id).update(started_at=started, finished_at=finished)
        job.refresh_from_db()

        assert _elapsed_seconds_for(job) == 360

    def test_terminal_without_finished_at_falls_back(self) -> None:
        """终态但没写 finished_at（老数据/异常路径）时按 now 算，不让前端整块计时消失。"""
        job = _make_job(status=PdfSplitJobStatus.FAILED)
        PdfSplitJob.objects.filter(id=job.id).update(started_at=timezone.now() - timedelta(seconds=60))
        job.refresh_from_db()

        elapsed = _elapsed_seconds_for(job)
        assert elapsed is not None and 58 <= elapsed <= 63


class TestBuildJobPayloadStageFields:
    def test_payload_carries_stage_and_timing(self) -> None:
        job = _make_job(stage=PdfSplitStage.CROSS_CHECK)
        PdfSplitJob.objects.filter(id=job.id).update(started_at=timezone.now() - timedelta(seconds=120))
        job.refresh_from_db()

        payload = PdfSplitJobService().build_job_payload(job)

        assert payload["stage"] == PdfSplitStage.CROSS_CHECK
        assert payload["started_at"] is not None
        assert payload["finished_at"] is None
        assert payload["elapsed_seconds"] is not None and payload["elapsed_seconds"] >= 119

    def test_payload_stage_defaults_when_missing(self) -> None:
        job = _make_job()
        PdfSplitJob.objects.filter(id=job.id).update(stage="")
        job.refresh_from_db()
        assert PdfSplitJobService().build_job_payload(job)["stage"] == PdfSplitStage.EXTRACT


class TestFileNameNormalisationAsymmetry:
    """附件原名 vs 库里清洗后的名字：不复用就会一遍遍重跑。

    2026-11-20 实测事故：附件原名 …（某某工伤行政复议案件）_20261120收.pdf
    被 ``sanitize_upload_filename`` 清洗成 …_某某工伤行政复议案件__20261120收.pdf
    存进 ``source_original_name``；而前端拿**原名**来查复用 → 精确匹配永远 miss
    → 点一次「自动识别」就从零重跑 93 页（两小时内同一份文件跑了三遍）。
    """

    def test_reusable_job_matches_raw_attachment_name(self) -> None:
        sanitized = "行政复议听取意见通知书_某某案件__20261120收.pdf"
        raw = "行政复议听取意见通知书（某某案件）_20261120收.pdf"
        owner = LawyerFactory()
        job = _make_job(name=sanitized, status=PdfSplitJobStatus.REVIEW_REQUIRED, pages=93, created_by=owner)

        found = PdfSplitJobService().find_reusable_job(source_name=raw, total_pages=93, user=owner)

        assert found is not None and found.id == job.id

    def test_inflight_job_matches_raw_attachment_name(self) -> None:
        sanitized = "行政复议听取意见通知书_某某案件__20261120收.pdf"
        raw = "行政复议听取意见通知书（某某案件）_20261120收.pdf"
        job = _make_job(name=sanitized, status=PdfSplitJobStatus.PROCESSING, pages=93)

        found = PdfSplitJobService().find_inflight_job(source_name=raw, total_pages=93)

        assert found is not None and found.id == job.id

    def test_sanitized_name_still_matches(self) -> None:
        """反向也要成立：调用方直接给清洗后的名字不能因此 miss。"""
        owner = LawyerFactory()
        job = _make_job(name="卷宗_A_B.pdf", status=PdfSplitJobStatus.REVIEW_REQUIRED, created_by=owner)
        found = PdfSplitJobService().find_reusable_job(source_name="卷宗_A_B.pdf", user=owner)
        assert found is not None and found.id == job.id

    def test_different_pages_still_miss(self) -> None:
        """放宽的只是**文件名**形态，页数判据不能被顺手放宽（同名不同件）。"""
        _make_job(name="卷宗_A_B.pdf", status=PdfSplitJobStatus.REVIEW_REQUIRED, pages=93)
        assert PdfSplitJobService().find_reusable_job(source_name="卷宗（A）B.pdf", total_pages=94) is None
