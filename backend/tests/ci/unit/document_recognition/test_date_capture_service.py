"""日期捕获旁线（date_capture_service）单元测试。

覆盖：
- 无文书 / 无案件日志时的明确跳过（不建任务）
- 幂等：同 (来源短信, 来源文书) 第二次调用复用而不再建任务
- failed 任务原地重跑而不是新建（避免堆垃圾行）
- force=True 无条件新建
- 文书文件已丢失时跳过
- 单份失败不影响同批其他文书
- list_source_tasks 的计数与归属过滤
- 旁线纪律：送识别不改变 CourtSMS 状态
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.document_recognition.models import DocumentRecognitionStatus, DocumentRecognitionTask
from apps.document_recognition.services import date_capture_service
from apps.testing.factories import LawyerFactory

SMS_ID = 9001


@pytest.fixture
def doc_file(tmp_path: Path) -> str:
    p = tmp_path / "传票.pdf"
    p.write_bytes(b"%PDF-1.4 test")
    return str(p)


def _source(paths: list[str], *, case_log_id: int | None = 77) -> Any:
    return date_capture_service.DateCaptureSource(
        sms_id=SMS_ID,
        case_id=5 if case_log_id else None,
        case_log_id=case_log_id,
        document_paths=paths,
    )


@pytest.mark.django_db
class TestCapturePreconditions:
    def test_no_documents_returns_skip(self) -> None:
        items = date_capture_service.capture_dates_for_source(_source([]))
        assert len(items) == 1
        assert items[0].action == "skipped"
        assert "没有可识别的文书" in items[0].reason
        assert DocumentRecognitionTask.objects.count() == 0

    def test_no_case_log_returns_skip(self) -> None:
        items = date_capture_service.capture_dates_for_source(_source(["/tmp/x.pdf"], case_log_id=None))
        assert items[0].action == "skipped"
        assert "尚未绑定案件" in items[0].reason
        assert DocumentRecognitionTask.objects.count() == 0

    def test_missing_file_skipped(self, tmp_path: Path) -> None:
        items = date_capture_service.capture_dates_for_source(_source([str(tmp_path / "gone.pdf")]))
        assert items[0].action == "skipped"
        assert "不在磁盘上" in items[0].reason
        assert DocumentRecognitionTask.objects.count() == 0


@pytest.mark.django_db
class TestCaptureIdempotency:
    def test_creates_once_then_reuses(self, doc_file: str) -> None:
        with patch("apps.core.tasking.submit_task") as submit:
            first = date_capture_service.capture_dates_for_source(_source([doc_file]))
            second = date_capture_service.capture_dates_for_source(_source([doc_file]))

        assert first[0].action == "created"
        assert first[0].task_id is not None
        assert second[0].action == "reused"
        assert second[0].task_id == first[0].task_id
        assert DocumentRecognitionTask.objects.count() == 1
        # 只投递一次异步任务：复用不再烧一次 LLM
        assert submit.call_count == 1

    def test_pipeline_prebinding_is_persisted(self, doc_file: str) -> None:
        owner = LawyerFactory()
        with patch("apps.core.tasking.submit_task"):
            items = date_capture_service.capture_dates_for_source(_source([doc_file]), user=owner)

        task = DocumentRecognitionTask.objects.get(id=items[0].task_id)
        assert task.source_court_sms_id == SMS_ID
        assert task.source_document_path == doc_file
        assert task.case_id == 5
        assert task.case_log_id == 77
        assert task.binding_success is True
        assert task.created_by_id == owner.id

    def test_failed_task_restarts_in_place(self, doc_file: str) -> None:
        with patch("apps.core.tasking.submit_task"):
            created = date_capture_service.capture_dates_for_source(_source([doc_file]))
        task_id = created[0].task_id
        DocumentRecognitionTask.objects.filter(id=task_id).update(
            status=DocumentRecognitionStatus.FAILED, error_message="boom"
        )

        with patch("apps.core.tasking.submit_task") as submit:
            again = date_capture_service.capture_dates_for_source(_source([doc_file]))

        assert again[0].action == "retried"
        assert again[0].task_id == task_id
        assert DocumentRecognitionTask.objects.count() == 1  # 不新建行
        assert submit.call_count == 1
        row = DocumentRecognitionTask.objects.get(id=task_id)
        assert row.status == DocumentRecognitionStatus.PENDING
        assert row.error_message == ""

    def test_force_creates_new_task(self, doc_file: str) -> None:
        with patch("apps.core.tasking.submit_task"):
            first = date_capture_service.capture_dates_for_source(_source([doc_file]))
            forced = date_capture_service.capture_dates_for_source(_source([doc_file]), force=True)

        assert forced[0].action == "created"
        assert forced[0].task_id != first[0].task_id
        assert DocumentRecognitionTask.objects.count() == 2

    def test_one_bad_document_does_not_block_others(self, doc_file: str, tmp_path: Path) -> None:
        paths = [doc_file, str(tmp_path / "missing.pdf")]
        with patch("apps.core.tasking.submit_task"):
            items = date_capture_service.capture_dates_for_source(_source(paths))

        actions = {Path(i.document_name).name: i.action for i in items}
        assert actions["传票.pdf"] == "created"
        assert actions["missing.pdf"] == "skipped"


@pytest.mark.django_db
class TestListSourceTasks:
    def test_counts_and_ownership_filter(self, doc_file: str) -> None:
        owner = LawyerFactory()
        other = LawyerFactory()
        with patch("apps.core.tasking.submit_task"):
            items = date_capture_service.capture_dates_for_source(_source([doc_file]), user=owner)
        task_id = items[0].task_id

        from django.utils import timezone

        from apps.document_recognition.models import DateCandidateStatus, DocumentRecognitionDateCandidate

        DocumentRecognitionDateCandidate.objects.create(
            task_id=task_id, due_at=timezone.now(), reminder_type="hearing", status=DateCandidateStatus.PENDING
        )
        DocumentRecognitionDateCandidate.objects.create(
            task_id=task_id, due_at=timezone.now(), reminder_type="other", status=DateCandidateStatus.CONFIRMED
        )

        rows = date_capture_service.list_source_tasks(SMS_ID, user=owner)
        assert len(rows) == 1
        assert rows[0]["candidate_count"] == 2
        assert rows[0]["pending_count"] == 1
        assert rows[0]["confirmed_count"] == 1

        # 非归属人（非管理员）看不到别人建的任务
        assert date_capture_service.list_source_tasks(SMS_ID, user=other) == []

        admin = LawyerFactory(is_admin=True)
        assert len(date_capture_service.list_source_tasks(SMS_ID, user=admin)) == 1


@pytest.mark.django_db
class TestSideLineDiscipline:
    def test_capture_never_touches_sms_record(self, doc_file: str) -> None:
        """旁线纪律：送识别全程不写 CourtSMS（识别失败也不能把短信拖下水）。"""
        from apps.automation.models import CourtSMS, CourtSMSStatus
        from apps.testing.factories import CaseFactory, CaseLogFactory

        case = CaseFactory()
        case_log = CaseLogFactory(case=case)
        sms = CourtSMS.objects.create(
            content="【测试】送达通知",
            received_at="2026-11-01T10:00:00Z",
            status=CourtSMSStatus.COMPLETED,
            case=case,
            case_log=case_log,
            document_file_paths=[doc_file],
        )
        before = (str(sms.status), sms.error_message, sms.retry_count)

        # 让建任务直接抛错：模拟旁线彻底失败
        with patch(
            "apps.document_recognition.services.task_service.DocumentRecognitionTaskService.create_task",
            side_effect=RuntimeError("boom"),
        ):
            items = date_capture_service.capture_dates_for_source(
                date_capture_service.DateCaptureSource(
                    sms_id=sms.id, case_id=case.id, case_log_id=case_log.id, document_paths=[doc_file]
                )
            )

        assert items[0].action == "skipped"
        assert "创建识别任务失败" in items[0].reason
        sms.refresh_from_db()
        assert (str(sms.status), sms.error_message, sms.retry_count) == before


def _make_service(doc_type: Any, confidence: float) -> tuple[Any, Any, Any]:
    """构造识别服务并注入提取器/分类器替身（text_extraction/classifier 是只读 property）。"""
    from apps.document_recognition.services.recognition_service import CourtDocumentRecognitionService

    extraction = MagicMock()
    extraction.extract_text.return_value = MagicMock(success=True, text="正文", extraction_method="pdf_direct")
    classifier = MagicMock()
    classifier.classify.return_value = (doc_type, confidence)
    svc = CourtDocumentRecognitionService(text_extraction=extraction, classifier=classifier)
    svc._reset_run_state()
    svc._run_llm_model = None
    return svc, extraction, classifier


@pytest.mark.django_db
class TestSmsHints:
    """来源管线解析结果回灌识别（短信识别的准度带给记一笔）。"""

    def test_hints_loaded_from_sms(self) -> None:
        from apps.automation.models import CourtSMS
        from apps.document_recognition.tasks import _load_pipeline_hints

        sms = CourtSMS.objects.create(
            content="x",
            received_at="2026-11-01T10:00:00Z",
            case_numbers=["（20XX）粤01民初某某号"],
            party_names=["甲某公司", " 乙某 ", ""],
            sms_type="document_delivery",
        )
        task = MagicMock(source_court_sms_id=sms.id)
        hints = _load_pipeline_hints(task)
        assert hints["case_number"] == "（20XX）粤01民初某某号"
        assert hints["party_names"] == ["甲某公司", "乙某"]

    def test_hints_empty_when_sms_missing(self) -> None:
        from apps.document_recognition.tasks import _load_pipeline_hints

        task = MagicMock(source_court_sms_id=999_999)
        hints = _load_pipeline_hints(task)
        assert hints == {"case_number": None, "party_names": [], "document_type": None, "received_at": None}

    def test_hints_empty_without_source(self) -> None:
        from apps.document_recognition.tasks import _load_pipeline_hints

        assert _load_pipeline_hints(MagicMock(source_court_sms_id=None))["case_number"] is None

    def test_sms_case_number_overrides_extracted(self) -> None:
        """案号：短信侧解析优先于本文书提取结果。"""
        from apps.document_recognition.services.data_classes import DocumentType
        from apps.document_recognition.services.recognition_service import CourtDocumentRecognitionService

        svc, extraction, classifier = _make_service(DocumentType.SUMMONS, 0.9)
        with (
            patch.object(svc, "_extract_doc_info", return_value=("（20XX）文书里的某某号", None)),
            patch.object(svc, "_build_date_candidates", return_value=[]),
            patch.object(svc, "_cached_analysis", return_value=None),
            patch.object(svc, "_build_binding", return_value=(MagicMock(success=True), "/tmp/a.pdf")),
        ):
            res = svc.recognize_document(
                "/tmp/a.pdf",
                known_case_number="（20XX）粤01民初某某号",
                known_document_type=None,
            )
        assert res.recognition.case_number == "（20XX）粤01民初某某号"

    def test_classifier_wins_over_sms_type_hint(self) -> None:
        """类型：只有分类器认不出（other）时才用短信类型兜底。"""
        from apps.document_recognition.services.data_classes import DocumentType
        from apps.document_recognition.services.recognition_service import CourtDocumentRecognitionService

        svc, _extraction, _classifier = _make_service(DocumentType.SUMMONS, 0.9)
        with (
            patch.object(svc, "_extract_doc_info", return_value=(None, None)),
            patch.object(svc, "_build_date_candidates", return_value=[]),
            patch.object(svc, "_cached_analysis", return_value=None),
            patch.object(svc, "_build_binding", return_value=(MagicMock(success=True), "/tmp/a.pdf")),
        ):
            res = svc.recognize_document("/tmp/a.pdf", known_document_type="other")
        assert res.recognition.document_type == DocumentType.SUMMONS
        assert res.classification_hint == ""

    def test_unknown_hint_ignored_safely(self) -> None:
        """短信类型兜底值非法时不炸、不改类型。"""
        from apps.document_recognition.services.data_classes import DocumentType
        from apps.document_recognition.services.recognition_service import CourtDocumentRecognitionService

        svc, _extraction, _classifier = _make_service(DocumentType.OTHER, 0.1)
        with (
            patch.object(svc, "_extract_doc_info", return_value=(None, None)),
            patch.object(svc, "_build_date_candidates", return_value=[]),
            patch.object(svc, "_cached_analysis", return_value=None),
            patch.object(svc, "_build_binding", return_value=(MagicMock(success=True), "/tmp/a.pdf")),
        ):
            res = svc.recognize_document("/tmp/a.pdf", known_document_type="not_a_type")
        assert res.recognition.document_type == DocumentType.OTHER
        assert res.classification_hint == ""
