from unittest.mock import Mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from tests.factories import LawyerFactory


@pytest.mark.django_db
def test_file_upload_endpoint(client, monkeypatch):
    user = LawyerFactory()
    client.force_login(user)

    mock_result = Mock()
    mock_result.success = True
    mock_result.file_info = {"path": "uploads/a.pdf"}
    mock_result.extraction = {"text": "ok"}
    mock_result.processing_params = {"limit": 10, "preview_page": 1}
    mock_result.error = None

    mock_service = Mock()
    mock_service.process_uploaded_file.return_value = mock_result
    monkeypatch.setattr("apps.automation.api.main_api._get_document_processor_service", lambda: mock_service)

    uploaded = SimpleUploadedFile("a.pdf", b"%PDF-1.4\n", content_type="application/pdf")
    resp = client.post(
        "/api/v1/automation/file/upload?limit=10&preview_page=1",
        data={"file": uploaded},
        HTTP_HOST="localhost",
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
