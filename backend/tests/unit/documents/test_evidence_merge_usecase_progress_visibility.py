import datetime

import pytest
from django.db import connection, transaction

from apps.documents.models import EvidenceItem, EvidenceList, ListType, MergeStatus
from apps.documents.services.evidence.evidence_merge_usecase import EvidenceMergeUseCase, MergeProgressReporter


@pytest.mark.django_db(transaction=True)
def test_merge_progress_is_visible_while_running(monkeypatch):
    today = datetime.date.today()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO cases_case
                (  # noqa: E501
                    is_archived, name, status, start_date, effective_date,
                    cause_of_action, target_amount, case_type, current_stage,
                )
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [0, "测试案件", "active", today, None, "合同纠纷", None, "civil", None],
        )
        case_id = cursor.lastrowid

    evidence_list = EvidenceList.objects.create(case_id=case_id, list_type=ListType.LIST_1)
    EvidenceItem.objects.create(
        evidence_list=evidence_list,
        order=1,
        name="证据1",
        purpose="测试",
        file="dummy.pdf",
        file_name="dummy.pdf",
    )

    class RecordingReporter:
        def __init__(self, *, list_id: int):
            self._inner = MergeProgressReporter(list_id=list_id)
            self.in_atomic_block: bool | None = None

        def report(self, *, current: int, total: int, message: str):
            self.in_atomic_block = transaction.get_connection().in_atomic_block
            self._inner.report(current=current, total=total, message=message)

    class FakePDFMergeService:
        def merge_evidence_files(self, evidence_list, progress_callback=None) -> str:
            if progress_callback:
                progress_callback(1, 1, "已处理：dummy.pdf")
            return "/tmp/fake.pdf"

    class FakeEvidenceService:
        def __init__(self, case_service=None):
            self.case_service = case_service

        def calculate_page_ranges(self, list_id):
            return None

        def update_subsequent_lists_pages(self, case_id, start_order):
            return None

    monkeypatch.setattr("apps.documents.services.pdf_merge_service.PDFMergeService", FakePDFMergeService)
    monkeypatch.setattr("apps.documents.services.evidence_service.EvidenceService", FakeEvidenceService)

    reporter = RecordingReporter(list_id=evidence_list.id)
    EvidenceMergeUseCase().merge(list_id=evidence_list.id, reporter=reporter)  # type: ignore[arg-type]

    assert reporter.in_atomic_block is False
    evidence_list.refresh_from_db()
    assert evidence_list.merge_status == MergeStatus.COMPLETED
    assert evidence_list.merge_progress == 100
