import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.exceptions import ValidationException
from apps.core.validators import Validators


def test_validate_uploaded_file_rejects_oversize():
    uploaded = SimpleUploadedFile("a.txt", b"1234", content_type="text/plain")
    with pytest.raises(ValidationException):
        Validators.validate_uploaded_file(uploaded, max_size_bytes=3)


def test_validate_uploaded_file_rejects_disallowed_extension():
    uploaded = SimpleUploadedFile("a.exe", b"hi", content_type="application/octet-stream")
    with pytest.raises(ValidationException):
        Validators.validate_uploaded_file(uploaded, allowed_extensions=[".pdf"])


def test_validate_uploaded_file_rejects_executable_magic():
    uploaded = SimpleUploadedFile("a.txt", b"MZ" + b"\x00" * 10, content_type="text/plain")
    with pytest.raises(ValidationException):
        Validators.validate_uploaded_file(uploaded)


def test_validate_uploaded_file_accepts_pdf_like_content():
    uploaded = SimpleUploadedFile("a.pdf", b"%PDF-1.7\n", content_type="application/pdf")
    assert Validators.validate_uploaded_file(uploaded, allowed_extensions=[".pdf"]) is uploaded
