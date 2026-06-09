"""legal_research app Model 单元测试

覆盖 LegalResearchTask, LegalResearchResult, LegalResearchTaskEvent,
CaseDownloadTask, CaseDownloadResult 的 __str__、choices。
"""

import pytest

from apps.testing.factories import LawyerFactory
from apps.automation.models.token import CourtToken
from apps.organization.models.credential import AccountCredential
from apps.organization.models.law_firm import LawFirm
from apps.organization.models.lawyer import Lawyer

from apps.legal_research.models.case_download import (
    CaseDownloadFormat,
    CaseDownloadResult,
    CaseDownloadStatus,
    CaseDownloadTask,
)
from apps.legal_research.models.result import LegalResearchResult
from apps.legal_research.models.task import LegalResearchSearchMode, LegalResearchTask, LegalResearchTaskStatus
from apps.legal_research.models.task_event import LegalResearchTaskEvent


def _make_credential():
    """创建测试用凭证"""
    lawyer = LawyerFactory()
    return AccountCredential.objects.create(
        lawyer=lawyer,
        site_name="weike",
        account="test_account",
        password="test_password",
    )


# ============================================================
# LegalResearchTask
# ============================================================


@pytest.mark.django_db
class TestLegalResearchTask:
    def test_str(self):
        cred = _make_credential()
        task = LegalResearchTask.objects.create(
            credential=cred,
            keyword="逾期利息",
            case_summary="借款合同纠纷",
            status=LegalResearchTaskStatus.PENDING,
        )
        result = str(task)
        assert "逾期利息" in result
        assert "pending" in result

    def test_status_choices(self):
        assert LegalResearchTaskStatus.PENDING.value == "pending"
        assert LegalResearchTaskStatus.QUEUED.value == "queued"
        assert LegalResearchTaskStatus.RUNNING.value == "running"
        assert LegalResearchTaskStatus.COMPLETED.value == "completed"
        assert LegalResearchTaskStatus.FAILED.value == "failed"
        assert LegalResearchTaskStatus.CANCELLED.value == "cancelled"

    def test_search_mode_choices(self):
        assert LegalResearchSearchMode.EXPANDED.value == "expanded"
        assert LegalResearchSearchMode.SINGLE.value == "single"

    def test_default_values(self):
        cred = _make_credential()
        task = LegalResearchTask.objects.create(
            credential=cred,
            keyword="测试关键词",
            case_summary="测试案情",
        )
        assert task.source == "weike"
        assert task.target_count == 3
        assert task.max_candidates == 100
        assert task.min_similarity_score == 0.9
        assert task.progress == 0
        assert task.scanned_count == 0
        assert task.matched_count == 0
        assert task.status == LegalResearchTaskStatus.PENDING


# ============================================================
# LegalResearchResult
# ============================================================


@pytest.mark.django_db
class TestLegalResearchResult:
    def test_str(self):
        cred = _make_credential()
        task = LegalResearchTask.objects.create(
            credential=cred,
            keyword="关键词",
            case_summary="案情",
        )
        result = LegalResearchResult.objects.create(
            task=task,
            rank=1,
            source_doc_id="doc_001",
            title="某某诉某某借款合同纠纷案",
            similarity_score=0.95,
        )
        result_str = str(result)
        assert str(task.id) in result_str
        assert "1" in result_str
        assert "某某诉某某借款合同纠纷案" in result_str

    def test_unique_constraint(self):
        cred = _make_credential()
        task = LegalResearchTask.objects.create(
            credential=cred,
            keyword="测试",
            case_summary="案情",
        )
        LegalResearchResult.objects.create(
            task=task, rank=1, source_doc_id="dup_doc"
        )
        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            LegalResearchResult.objects.create(
                task=task, rank=2, source_doc_id="dup_doc"
            )


# ============================================================
# LegalResearchTaskEvent
# ============================================================


@pytest.mark.django_db
class TestLegalResearchTaskEvent:
    def test_str_success(self):
        cred = _make_credential()
        task = LegalResearchTask.objects.create(
            credential=cred,
            keyword="测试",
            case_summary="案情",
        )
        event = LegalResearchTaskEvent.objects.create(
            task=task,
            stage=LegalResearchTaskEvent.Stage.SEARCH,
            source=LegalResearchTaskEvent.Source.API,
            interface_name="search_api",
            success=True,
        )
        result = str(event)
        assert "search" in result
        assert "api" in result
        assert "search_api" in result
        assert "ok" in result

    def test_str_failure(self):
        cred = _make_credential()
        task = LegalResearchTask.objects.create(
            credential=cred,
            keyword="测试",
            case_summary="案情",
        )
        event = LegalResearchTaskEvent.objects.create(
            task=task,
            stage=LegalResearchTaskEvent.Stage.DETAIL,
            source=LegalResearchTaskEvent.Source.DOM,
            interface_name="detail_page",
            success=False,
        )
        assert "fail" in str(event)

    def test_stage_choices(self):
        assert LegalResearchTaskEvent.Stage.SEARCH.value == "search"
        assert LegalResearchTaskEvent.Stage.DETAIL.value == "detail"

    def test_source_choices(self):
        assert LegalResearchTaskEvent.Source.API.value == "api"
        assert LegalResearchTaskEvent.Source.DOM.value == "dom"
        assert LegalResearchTaskEvent.Source.SYSTEM.value == "system"


# ============================================================
# CaseDownloadTask
# ============================================================


@pytest.mark.django_db
class TestCaseDownloadTask:
    def test_str(self):
        cred = _make_credential()
        task = CaseDownloadTask.objects.create(
            credential=cred,
            case_numbers="(2025)京01民初123号",
            file_format=CaseDownloadFormat.PDF,
            status=CaseDownloadStatus.PENDING,
        )
        result = str(task)
        assert "pdf" in result
        assert "pending" in result

    def test_status_choices(self):
        assert CaseDownloadStatus.PENDING.value == "pending"
        assert CaseDownloadStatus.RUNNING.value == "running"
        assert CaseDownloadStatus.COMPLETED.value == "completed"
        assert CaseDownloadStatus.FAILED.value == "failed"

    def test_format_choices(self):
        assert CaseDownloadFormat.PDF.value == "pdf"
        assert CaseDownloadFormat.DOC.value == "doc"

    def test_default_format(self):
        cred = _make_credential()
        task = CaseDownloadTask.objects.create(
            credential=cred,
            case_numbers="测试案号",
        )
        assert task.file_format == CaseDownloadFormat.PDF


# ============================================================
# CaseDownloadResult
# ============================================================


@pytest.mark.django_db
class TestCaseDownloadResult:
    def test_str(self):
        cred = _make_credential()
        task = CaseDownloadTask.objects.create(
            credential=cred,
            case_numbers="测试",
        )
        result = CaseDownloadResult.objects.create(
            task=task,
            case_number="(2025)京01民初123号",
            title="某某案",
            file_path="/tmp/doc.pdf",
        )
        assert str(result) == ""
