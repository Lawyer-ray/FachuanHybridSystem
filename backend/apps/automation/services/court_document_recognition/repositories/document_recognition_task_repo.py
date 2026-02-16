"""Data repository layer."""

from apps.automation.models import DocumentRecognitionTask


class DocumentRecognitionTaskRepo:
    def get(self, task_id: int) -> DocumentRecognitionTask | None:
        return DocumentRecognitionTask.objects.filter(id=task_id).first()
