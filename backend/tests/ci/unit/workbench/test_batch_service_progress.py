"""batch_service.py 补充单元测试：Excel 拆分 + 进度推导 + 子项查询.

覆盖 _is_excel / _split_excel_rows（表头探测、空行清理、行转文本）、
get_job_progress 的 ETA 与速度计算、get_active_items 的状态过滤、
分页与 _job_to_dict 序列化。
"""

from __future__ import annotations

import io
from typing import Any

import pytest

from apps.workbench.models import BatchJob, BatchJobItem, BatchJobStatus
from apps.workbench.services.batch_service import BatchAnalysisService, _is_excel, _split_excel_rows


class TestIsExcel:
    def test_xlsx(self) -> None:
        assert _is_excel("报表.xlsx") is True

    def test_xls(self) -> None:
        assert _is_excel("旧格式.XLS") is True  # 大小写不敏感

    def test_docx(self) -> None:
        assert _is_excel("合同.docx") is False

    def test_no_extension(self) -> None:
        assert _is_excel("README") is False

    def test_empty(self) -> None:
        assert _is_excel("") is False


class TestSplitExcelRows:
    def _xlsx(self, rows: list[list[Any]], name: str = "线索.xlsx") -> Any:
        import pandas as pd

        buf = io.BytesIO()
        pd.DataFrame(rows).to_excel(buf, index=False, header=False)
        buf.seek(0)
        from django.core.files.uploadedfile import SimpleUploadedFile

        return SimpleUploadedFile(
            name, buf.read(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    def test_splits_each_row_to_text(self) -> None:
        uploaded = self._xlsx(
            [
                ["姓名", "金额", "事项"],
                ["张三", "10万", "借款"],
                ["李四", "5万", "货款"],
            ]
        )
        results = _split_excel_rows(uploaded)

        assert len(results) == 2
        first_name, first_text = results[0]
        assert first_name == "线索_第1行.txt"
        assert "姓名: 张三" in first_text
        assert "金额: 10万" in first_text
        assert "事项: 借款" in first_text

    def test_header_detection_skips_preamble(self) -> None:
        """前两行是说明文字，第三行才是真表头（>=3 个非空单元格）。"""
        uploaded = self._xlsx(
            [
                ["批量材料"],
                ["仅供测试"],
                ["列A", "列B", "列C"],
                ["v1", "v2", "v3"],
            ]
        )
        results = _split_excel_rows(uploaded)
        assert len(results) == 1
        assert "列A: v1" in results[0][1]

    def test_blank_rows_dropped(self) -> None:
        uploaded = self._xlsx(
            [
                ["姓名", "金额"],
                ["张三", "10万"],
                [None, None],
                ["李四", ""],
            ]
        )
        results = _split_excel_rows(uploaded)
        # 全空行被丢弃；「李四」行仍有一个有效字段 → 保留
        assert len(results) == 2
        assert results[1][1] == "姓名: 李四"

    def test_missing_column_header_kept_by_pandas(self) -> None:
        """空表头单元格在 pandas 侧命名（"Unnamed: N"），行内容仍逐列透出。"""
        uploaded = self._xlsx(
            [
                ["姓名", None, "备注", "补充"],
                ["王五", "x", "y", "z"],
            ]
        )
        results = _split_excel_rows(uploaded)
        assert len(results) == 1
        assert "姓名: 王五" in results[0][1]
        assert "备注: y" in results[0][1]
        assert "补充: z" in results[0][1]
        assert ": x" in results[0][1]  # 空表头列的值仍在（列名为 pandas 生成名）


@pytest.mark.django_db
class TestGetJobProgress:
    def _job(self, session: Any, **kwargs: Any) -> BatchJob:
        from django.utils import timezone

        defaults: dict[str, Any] = {
            "session": session,
            "job_type": "doc_analysis",
            "prompt": "测试",
            "llm_model": "m",
            "total_items": 10,
        }
        defaults.update(kwargs)
        return BatchJob.objects.create(**defaults)

    def _session(self) -> Any:
        from apps.workbench.models import WorkbenchSession

        return WorkbenchSession.objects.create(title="进度测试")

    def test_returns_job_and_items(self) -> None:
        session = self._session()
        job = self._job(session)
        BatchJobItem.objects.create(job=job, file_name="a.docx")
        BatchJobItem.objects.create(job=job, file_name="b.docx")

        result_job, items = BatchAnalysisService().get_job_progress(job.id)
        assert result_job.id == job.id
        assert len(items) == 2

    def test_eta_and_speed_computed_when_running(self) -> None:
        from datetime import timedelta

        from django.utils import timezone

        session = self._session()
        started = timezone.now() - timedelta(minutes=2)
        job = self._job(
            session,
            status=BatchJobStatus.RUNNING,
            completed_items=4,
            failed_items=1,
            started_processing_at=started,
        )
        result_job, _ = BatchAnalysisService().get_job_progress(job.id)
        # 5 项 / 2 分钟 = 2.5 项每分钟
        assert result_job.speed_per_minute == pytest.approx(2.5, rel=0.2)
        # 剩余 5 项 → 约 2 分钟
        assert result_job.eta_seconds == pytest.approx(120, rel=0.2)

    def test_no_eta_when_not_running(self) -> None:
        from datetime import timedelta

        from django.utils import timezone

        session = self._session()
        job = self._job(
            session,
            status=BatchJobStatus.PENDING,
            completed_items=4,
            failed_items=1,
            started_processing_at=timezone.now() - timedelta(minutes=5),
        )
        result_job, _ = BatchAnalysisService().get_job_progress(job.id)
        assert not hasattr(result_job, "speed_per_minute") or result_job.speed_per_minute == 0

    def test_no_eta_when_nothing_processed(self) -> None:
        from datetime import timedelta

        from django.utils import timezone

        session = self._session()
        job = self._job(
            session,
            status=BatchJobStatus.RUNNING,
            completed_items=0,
            failed_items=0,
            started_processing_at=timezone.now() - timedelta(minutes=1),
        )
        result_job, _ = BatchAnalysisService().get_job_progress(job.id)
        assert not hasattr(result_job, "speed_per_minute") or result_job.speed_per_minute == 0


@pytest.mark.django_db
class TestGetActiveItems:
    def test_filters_running_and_finished(self) -> None:
        from apps.workbench.models import WorkbenchSession

        session = WorkbenchSession.objects.create(title="active items")
        job = BatchJob.objects.create(
            session=session, job_type="doc_analysis", prompt="p", llm_model="m", total_items=4
        )
        BatchJobItem.objects.create(job=job, file_name="running.docx", status=BatchJobStatus.RUNNING)
        BatchJobItem.objects.create(job=job, file_name="done.docx", status=BatchJobStatus.COMPLETED)
        BatchJobItem.objects.create(job=job, file_name="fail.docx", status=BatchJobStatus.FAILED)
        BatchJobItem.objects.create(job=job, file_name="pending.docx", status=BatchJobStatus.PENDING)

        active = BatchAnalysisService().get_active_items(job.id)
        names = {item.file_name for item in active}
        assert names == {"running.docx", "done.docx", "fail.docx"}  # PENDING 不在 active 集


@pytest.mark.django_db
class TestListBatchJobsPagination:
    def test_page_slicing(self) -> None:
        from apps.workbench.models import WorkbenchSession

        session = WorkbenchSession.objects.create(title="分页")
        for i in range(5):
            BatchJob.objects.create(
                session=session, job_type="doc_analysis", prompt=f"p{i}", llm_model="m", total_items=1
            )

        svc = BatchAnalysisService()
        page1 = svc.list_batch_jobs(session.id, page=1, page_size=2)
        page2 = svc.list_batch_jobs(session.id, page=2, page_size=2)

        assert page1["count"] == 5
        assert len(page1["items"]) == 2
        assert len(page2["items"]) == 2
        # created_at 倒序：第一页比第二页新
        assert page1["items"][0]["created_at"] >= page2["items"][0]["created_at"]
        # 序列化字段齐全
        assert {"id", "status", "total_items", "progress"} <= set(page1["items"][0])


@pytest.mark.django_db
class TestCreateJobExcelSplit:
    def test_excel_rows_become_txt_items(self) -> None:
        """create_job：xlsx 每行 → 一个 .txt item（Q 提交 mock）。"""
        import pandas as pd
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.workbench.models import WorkbenchSession

        session = WorkbenchSession.objects.create(title="excel 建任务")

        buf = io.BytesIO()
        pd.DataFrame([["姓名", "金额"], ["张三", "10万"]]).to_excel(buf, index=False, header=False)
        buf.seek(0)
        xlsx = SimpleUploadedFile(
            "线索.xlsx", buf.read(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        docx = SimpleUploadedFile(
            "合同.docx", b"PK", content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

        svc = BatchAnalysisService()
        with patch_submit() as mock_factory:
            mock_factory.return_value.submit.return_value = "task-1"
            job = svc.create_job(session_id=session.id, prompt="分析", llm_model="m", files=[docx, xlsx])

        try:
            assert job.total_items == 2
            names = {item.file_name for item in BatchJobItem.objects.filter(job=job)}
            assert names == {"合同.docx", "线索_第1行.txt"}
            assert job.task_id == "task-1"
        finally:
            for item in BatchJobItem.objects.filter(job=job):
                item.file.delete(save=False)


def patch_submit():
    from unittest.mock import patch

    return patch("apps.core.dependencies.core.build_task_submission_service")
