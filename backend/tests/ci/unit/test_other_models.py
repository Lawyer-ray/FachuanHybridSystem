"""其他 Model 测试 - 未分类 app 的模型测试"""

from __future__ import annotations

from typing import Any

import pytest

from apps.batch_printing.models import BatchPrintJob, BatchPrintItem, BatchPrintJobStatus
from apps.pdf_splitting.models import PdfSplitJob, PdfSplitJobStatus
from apps.sales_dispute.models import CaseAssessment, CollectionRecord, PaymentRecord
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
class TestCaseAssessmentModel:
    """CaseAssessment 模型测试"""

    def test_create_assessment(self) -> None:
        """创建案件评估"""
        from apps.cases.models import Case
        from apps.contracts.models import Contract
        from decimal import Decimal

        contract = Contract.objects.create(name="评估测试合同", case_type="civil")
        case = Case.objects.create(name="评估测试案件", contract=contract)
        assessment = CaseAssessment.objects.create(
            case=case,
            principal_amount=Decimal("100000.00"),
            assessment_grade="A",
        )
        assert assessment.principal_amount == Decimal("100000.00")
        assert assessment.assessment_grade == "A"


@pytest.mark.django_db
class TestCollectionRecordModel:
    """CollectionRecord 模型测试"""

    def test_create_record(self) -> None:
        """创建催收记录"""
        from apps.cases.models import Case
        from apps.contracts.models import Contract
        from datetime import date

        contract = Contract.objects.create(name="催收测试合同", case_type="civil")
        case = Case.objects.create(name="催收测试案件", contract=contract)
        record = CollectionRecord.objects.create(
            case=case,
            current_stage="phone",
            start_date=date(2024, 1, 1),
        )
        assert record.current_stage == "phone"


@pytest.mark.django_db
class TestPaymentRecordModel:
    """PaymentRecord 模型测试"""

    def test_create_record(self) -> None:
        """创建付款记录"""
        from apps.cases.models import Case
        from apps.contracts.models import Contract
        from decimal import Decimal
        from datetime import date

        contract = Contract.objects.create(name="付款测试合同", case_type="civil")
        case = Case.objects.create(name="付款测试案件", contract=contract)
        record = PaymentRecord.objects.create(
            case=case,
            payment_date=date(2024, 1, 1),
            payment_amount=Decimal("50000.00"),
            remaining_principal=Decimal("50000.00"),
        )
        assert record.payment_amount == Decimal("50000.00")


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
