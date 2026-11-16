"""三段任务链（extract → cross_check → segment）的推进逻辑单测。

背景（这些用例的存在理由）：双引擎交叉比对以前内联在取字阶段里，164 页整本
再解析两遍要十几分钟，而 `Q_CLUSTER.timeout` 默认 600s 是**单任务**硬阈值——
超时直接杀 worker 进程，连 finally 都不执行。实测后果是 DB 里只剩一个
`stage=cross_check` 的僵尸，`django_q_task` 里一行记录都没有。

所以交叉比对必须拆成独立任务，与 extract / segment 平级，各自拥有完整 600s。
本文件锁住「拆开之后推进关系还对」这件事。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest

from apps.pdf_splitting.models import PdfSplitJob, PdfSplitJobStatus, PdfSplitStage
from apps.pdf_splitting.services.split import two_stage

pytestmark = pytest.mark.django_db


def _job(*, dual_engines: str = "") -> PdfSplitJob:
    return PdfSplitJob.objects.create(
        id=uuid4(),
        source_type="upload",
        source_original_name="示例卷宗.pdf",
        status=PdfSplitJobStatus.PROCESSING,
        total_pages=10,
        processed_pages=10,
        progress=100,
        stage=PdfSplitStage.EXTRACT,
        dual_engines=dual_engines,
    )


class TestAdvanceAfterExtract:
    def test_双引擎时推进到交叉比对而不是分段(self) -> None:
        job = _job(dual_engines="mineru,paddleocr_vl")
        with (
            patch.object(two_stage, "submit_cross_check_stage", return_value="tid-xc") as xc,
            patch.object(two_stage, "submit_segment_stage", return_value="tid-seg") as seg,
        ):
            two_stage.advance_after_extract(job, pages_count=10)

        xc.assert_called_once()
        seg.assert_not_called()
        job.refresh_from_db()
        assert job.stage == PdfSplitStage.CROSS_CHECK
        # 取字确实做完了，但整条流水线没完：progress 让出 90 这一段，
        # processed_pages 是真实完成量，不回退
        assert job.progress == 90
        assert job.processed_pages == 10
        assert job.task_id == "tid-xc"

    @pytest.mark.parametrize("dual_engines", ["", "mineru", "  "])
    def test_单引擎或空时直接去分段(self, dual_engines: str) -> None:
        """没开双引擎却多排一个空阶段，只是白跑一趟 worker。"""
        job = _job(dual_engines=dual_engines)
        with (
            patch.object(two_stage, "submit_cross_check_stage", return_value="tid-xc") as xc,
            patch.object(two_stage, "submit_segment_stage", return_value="tid-seg") as seg,
        ):
            two_stage.advance_after_extract(job, pages_count=10)

        xc.assert_not_called()
        seg.assert_called_once()
        job.refresh_from_db()
        assert job.stage == PdfSplitStage.SEGMENT


class TestCrossCheckTask:
    def test_跑完把分歧落盘并推进到分段(self) -> None:
        """交叉比对的产出必须落盘：分段阶段只读 pages.json，拿不到就白跑一次云端。"""
        job = _job(dual_engines="mineru,paddleocr_vl")
        summary: dict[str, Any] = {
            "engine_disagreements": [{"page_no": 1, "kind": "char"}],
            "engine_disagree_summary": {"high": 1},
            "dual_engine": {"engines": {"mineru": {"ok": True}}},
        }

        with (
            patch(
                "apps.pdf_splitting.tasks.PdfSplitService.cross_check_stage",
                return_value=summary,
            ),
            patch.object(two_stage, "save_engine_disagreements") as save,
            patch.object(two_stage, "submit_segment_stage", return_value="tid-seg"),
        ):
            from apps.pdf_splitting.tasks import run_cross_check_stage

            run_cross_check_stage(str(job.id))

        save.assert_called_once()
        written = save.call_args.args[1]
        assert written["engine_disagreements"] == summary["engine_disagreements"]
        assert written["dual_engine"] == summary["dual_engine"]

        job.refresh_from_db()
        assert job.stage == PdfSplitStage.SEGMENT

    def test_比对抛异常仍然推进到分段(self) -> None:
        """分歧是附加信息，交叉校验挂了不该把整份卷宗判失败。"""
        job = _job(dual_engines="mineru,paddleocr_vl")

        with (
            patch(
                "apps.pdf_splitting.tasks.PdfSplitService.cross_check_stage",
                side_effect=RuntimeError("cloud down"),
            ),
            patch.object(two_stage, "submit_segment_stage", return_value="tid-seg"),
        ):
            from apps.pdf_splitting.tasks import run_cross_check_stage

            run_cross_check_stage(str(job.id))

        job.refresh_from_db()
        assert job.status == PdfSplitJobStatus.PROCESSING
        assert job.stage == PdfSplitStage.SEGMENT

    def test_已取消的任务不再推进(self) -> None:
        job = _job(dual_engines="mineru,paddleocr_vl")
        PdfSplitJob.objects.filter(id=job.id).update(cancel_requested=True)

        with (
            patch("apps.pdf_splitting.tasks.PdfSplitService.cross_check_stage") as xc,
            patch.object(two_stage, "submit_segment_stage") as seg,
        ):
            from apps.pdf_splitting.tasks import run_cross_check_stage

            run_cross_check_stage(str(job.id))

        xc.assert_not_called()
        seg.assert_not_called()
        job.refresh_from_db()
        assert job.status == PdfSplitJobStatus.CANCELLED


class TestExtractSummaryPersisted:
    """取字摘要必须落盘：``ocr_provider`` 是分段阶段换算 bbox 单位的唯一依据。

    不落盘时分段阶段只能拿 ``job.cloud_backend``（默认 "auto"）当依据，而
    ``resolve_bbox_unit("auto")`` 是 unknown —— positioned 恒空。
    """

    def test_取字跑完把摘要落盘(self) -> None:
        job = _job()
        summary: dict[str, Any] = {"ocr_provider": "mineru", "cloud_failover_from": ["textin"]}

        with (
            patch("apps.pdf_splitting.tasks.PdfSplitService.extract_stage", return_value=([], summary)),
            patch.object(two_stage, "save_pages"),
            patch.object(two_stage, "save_page_quality"),
            patch.object(two_stage, "save_extract_summary") as save,
            patch.object(two_stage, "submit_segment_stage", return_value="tid-seg"),
        ):
            from apps.pdf_splitting.tasks import run_extract_stage

            run_extract_stage(str(job.id))

        save.assert_called_once()
        assert save.call_args.args[1]["ocr_provider"] == "mineru"

    def test_摘要落盘失败不阻断取字阶段(self) -> None:
        """坐标是附加信息，正文已经拿到了——不能因为写不动一个 json 就判整份卷宗失败。"""
        job = _job()

        with (
            patch("apps.pdf_splitting.tasks.PdfSplitService.extract_stage", return_value=([], {})),
            patch.object(two_stage, "save_pages"),
            patch.object(two_stage, "save_page_quality"),
            patch.object(two_stage, "save_extract_summary", side_effect=OSError("disk full")),
            patch.object(two_stage, "submit_segment_stage", return_value="tid-seg"),
        ):
            from apps.pdf_splitting.tasks import run_extract_stage

            run_extract_stage(str(job.id))

        job.refresh_from_db()
        assert job.status != PdfSplitJobStatus.FAILED
        assert job.stage == PdfSplitStage.SEGMENT
