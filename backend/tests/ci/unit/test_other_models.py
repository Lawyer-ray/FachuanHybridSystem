"""其他 Model 测试 - 未分类 app 的模型测试"""

from __future__ import annotations

from typing import Any

import pytest

from apps.batch_printing.models import BatchPrintJob, BatchPrintItem, BatchPrintJobStatus
from apps.pdf_splitting.models import PdfSplitJob, PdfSplitJobStatus
from apps.finance.models.lpr_rate import LPRRate
from apps.story_viz.models import StoryAnimation, StoryAnimationStatus


@pytest.mark.django_db
class TestBatchPrintJobModel:
    """BatchPrintJob 模型测试"""

    def test_create_job(self) -> None:
        """创建批量打印任务"""
        job = BatchPrintJob.objects.create(
            status=BatchPrintJobStatus.PENDING,
        )
        assert job.status == BatchPrintJobStatus.PENDING

    def test_job_status_choices(self) -> None:
        """任务状态选项"""
        assert BatchPrintJobStatus.PENDING == "pending"
        assert BatchPrintJobStatus.PROCESSING == "processing"
        assert BatchPrintJobStatus.COMPLETED == "completed"
        assert BatchPrintJobStatus.FAILED == "failed"


@pytest.mark.django_db
class TestPdfSplitJobModel:
    """PdfSplitJob 模型测试"""

    def test_create_job(self) -> None:
        """创建 PDF 拆分任务"""
        job = PdfSplitJob.objects.create(
            source_type="upload",
            source_original_name="test.pdf",
            status=PdfSplitJobStatus.PENDING,
        )
        assert job.source_original_name == "test.pdf"
        assert job.status == PdfSplitJobStatus.PENDING

    def test_job_status_choices(self) -> None:
        """任务状态选项"""
        assert PdfSplitJobStatus.PENDING == "pending"
        assert PdfSplitJobStatus.PROCESSING == "processing"
        assert PdfSplitJobStatus.COMPLETED == "completed"
        assert PdfSplitJobStatus.FAILED == "failed"

@pytest.mark.django_db
class TestLPRRateModel:
    """LPRRate 模型测试"""

    def test_create_rate(self) -> None:
        """创建 LPR 利率"""
        from datetime import date
        from decimal import Decimal

        rate = LPRRate.objects.create(
            effective_date=date(2024, 1, 1),
            rate_1y=Decimal("3.45"),
            rate_5y=Decimal("4.20"),
            is_auto_synced=True,
        )
        assert rate.rate_1y == Decimal("3.45")
        assert rate.rate_5y == Decimal("4.20")
        assert rate.is_auto_synced is True


@pytest.mark.django_db
class TestStoryAnimationModel:
    """StoryAnimation 模型测试"""

    def test_create_animation(self) -> None:
        """创建动画"""
        animation = StoryAnimation.objects.create(
            source_title="测试动画",
            source_text="测试内容",
            viz_type="timeline",
            status=StoryAnimationStatus.PENDING,
        )
        assert animation.source_title == "测试动画"
        assert animation.status == StoryAnimationStatus.PENDING

    def test_animation_status_choices(self) -> None:
        """动画状态选项"""
        assert StoryAnimationStatus.PENDING == "pending"
        assert StoryAnimationStatus.PROCESSING == "processing"
        assert StoryAnimationStatus.COMPLETED == "completed"
        assert StoryAnimationStatus.FAILED == "failed"

    def test_animation_with_payloads(self) -> None:
        """创建动画包含载荷数据"""
        facts = {"events": [{"name": "事件1"}], "parties": [{"name": "人物1"}]}
        script = {"timeline_nodes": [{"id": 1}]}
        render = {"nodes": [{"id": 1}], "edges": []}
        animation = StoryAnimation.objects.create(
            source_title="载荷动画",
            source_text="载荷内容",
            viz_type="timeline",
            status=StoryAnimationStatus.PENDING,
            facts_payload=facts,
            script_payload=script,
            render_payload=render,
        )
        assert animation.facts_payload == facts
        assert animation.script_payload == script
        assert animation.render_payload == render
