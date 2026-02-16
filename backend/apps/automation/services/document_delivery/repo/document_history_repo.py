"""Data repository layer."""

from datetime import datetime

from django.utils import timezone

from .court_sms_repo import CourtSmsRepo


def record_query_history_task(credential_id: int, case_number: str, send_time: datetime) -> None:
    DocumentHistoryRepo().record_query_history(
        credential_id=credential_id, case_number=case_number, send_time=send_time
    )


class DocumentHistoryRepo:
    def __init__(self, court_sms_repo: CourtSmsRepo | None = None) -> None:
        self._court_sms_repo = court_sms_repo

    @property
    def court_sms_repo(self) -> CourtSmsRepo:
        if self._court_sms_repo is None:
            self._court_sms_repo = CourtSmsRepo()
        return self._court_sms_repo

    def should_process(self, credential_id: int, case_number: str, send_time: datetime) -> bool:
        completed_sms_id = self.court_sms_repo.find_completed_sms_id_by_case_number(case_number)
        if completed_sms_id:
            return False

        from apps.automation.models import DocumentQueryHistory

        send_time_value = timezone.make_aware(send_time) if timezone.is_naive(send_time) else send_time

        existing = DocumentQueryHistory.objects.filter(
            credential_id=credential_id, case_number=case_number, send_time=send_time_value
        ).first()
        return existing is None

    def delete_query_history(self, credential_id: int, case_number: str, send_time: datetime) -> int:
        from apps.automation.models import DocumentQueryHistory

        send_time_value = timezone.make_aware(send_time) if timezone.is_naive(send_time) else send_time
        deleted, _ = DocumentQueryHistory.objects.filter(
            credential_id=credential_id, case_number=case_number, send_time=send_time_value
        ).delete()
        return deleted

    def record_query_history(self, credential_id: int, case_number: str, send_time: datetime) -> None:
        from apps.automation.models import DocumentQueryHistory

        send_time_value = timezone.make_aware(send_time) if timezone.is_naive(send_time) else send_time
        DocumentQueryHistory.objects.get_or_create(
            credential_id=credential_id, case_number=case_number, send_time=send_time_value, defaults={}
        )

    def enqueue_record_query_history(self, credential_id: int, case_number: str, send_time: datetime) -> str:
        from apps.core.services.django_q_tasks import submit_q_task

        return submit_q_task(
            "apps.automation.services.document_delivery.repo.document_history_repo.record_query_history_task",
            credential_id,
            case_number,
            send_time,
            task_name=f"document_delivery.record_query_history:{credential_id}:{case_number}",
        )
