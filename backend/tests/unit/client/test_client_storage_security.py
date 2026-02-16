import pytest
from django.core.files.uploadedfile import SimpleUploadedFile


@pytest.mark.django_db
def test_sanitize_upload_filename_strips_path():
    from apps.client.services.storage import sanitize_upload_filename

    assert sanitize_upload_filename("../a.txt").endswith(".txt")
    assert ".." not in sanitize_upload_filename("../a.txt")


@pytest.mark.django_db
def test_save_uploaded_file_writes_under_media_root(settings, tmp_path):
    from apps.client.services.storage import save_uploaded_file

    settings.MEDIA_ROOT = tmp_path
    uploaded = SimpleUploadedFile("../evil.txt", b"hello", content_type="text/plain")

    rel_path, safe_name = save_uploaded_file(uploaded, rel_dir="client_docs/1")

    assert rel_path.startswith("client_docs/1/")
    assert ".." not in rel_path
    assert safe_name.endswith(".txt")
    assert (tmp_path / rel_path).exists()


@pytest.mark.django_db
def test_save_uploaded_file_falls_back_to_original_extension_when_preferred_missing_ext(settings, tmp_path):
    from apps.client.services.storage import save_uploaded_file

    settings.MEDIA_ROOT = tmp_path
    uploaded = SimpleUploadedFile("license.pdf", b"hello", content_type="application/pdf")

    rel_path, _ = save_uploaded_file(
        uploaded,
        rel_dir="client_docs/1",
        preferred_filename="营业执照（广东润知信息科技有限公司）",
    )

    assert rel_path.endswith(".pdf")
    assert (tmp_path / rel_path).exists()


@pytest.mark.django_db
def test_delete_media_file_does_not_delete_outside_media_root(settings, tmp_path):
    from apps.client.services.storage import delete_media_file

    settings.MEDIA_ROOT = tmp_path
    outside = tmp_path.parent / "outside.txt"
    outside.write_bytes(b"x")

    delete_media_file(str(outside))

    assert outside.exists()


@pytest.mark.django_db
def test_recognize_expiry_date_task_reads_relative_path(settings, tmp_path, monkeypatch, client_entity):
    from datetime import date

    from apps.client.models import ClientIdentityDoc
    from apps.client.tasks import recognize_expiry_date_task

    settings.MEDIA_ROOT = tmp_path
    rel_path = "client_docs/1/id.jpg"
    abs_path = tmp_path / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(b"fake")

    doc = ClientIdentityDoc.objects.create(
        client=client_entity,
        doc_type=ClientIdentityDoc.ID_CARD,
        file_path=rel_path,
        expiry_date=None,
    )

    class _FakeResult:
        def __init__(self):
            self.extracted_data = {"expiry_date": "2030-01-01"}
            self.confidence = 0.9
            self.doc_type = ClientIdentityDoc.ID_CARD

    class _FakeService:
        def extract(self, image_bytes: bytes, doc_type: str):
            return _FakeResult()

    monkeypatch.setattr(
        "apps.client.services.identity_extraction.extraction_service.IdentityExtractionService",
        lambda: _FakeService(),
    )

    result = recognize_expiry_date_task(doc.id)
    doc.refresh_from_db()

    assert result["status"] == "success"
    assert doc.expiry_date == date(2030, 1, 1)
