import pytest

from apps.automation.services.document_delivery.data_classes import DocumentRecord, DocumentProcessResult
from apps.automation.services.document_delivery.download_service import DocumentDownloadService


@pytest.mark.unit
class TestDocumentDownloadServiceFacade:
    def test_process_document_via_api_delegates_to_api_service(self):
        calls = []

        class _ApiServiceStub:
            def process_document(self, record, token: str, credential_id: int):
                calls.append((record.sdbh, token, credential_id))
                return DocumentProcessResult(
                    success=True,
                    case_id=1,
                    case_log_id=2,
                    renamed_path="/tmp/a.pdf",
                    notification_sent=True,
                    error_message=None,
                )

        svc = DocumentDownloadService(api_service=_ApiServiceStub())
        record = DocumentRecord(
            ah="(2026)粤01民初00001号",
            sdbh="SDBH001",
            ajzybh="AJ001",
            fssj="2026-01-01 10:00:00",
            fymc="测试法院",
            wsmc="判决书",
        )
        res = svc.process_document_via_api(record=record, token="t", credential_id=9)

        assert calls == [("SDBH001", "t", 9)]
        assert res.success is True
