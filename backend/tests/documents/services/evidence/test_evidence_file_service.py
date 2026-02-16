from __future__ import annotations

from dataclasses import dataclass

import pytest

from apps.core.exceptions import ValidationException
from apps.documents.services.evidence.evidence_file_service import EvidenceFileService

pytestmark = pytest.mark.django_db(transaction=True)


@dataclass
class _DummyFile:
    name: str
    size: int


class _DummyStoredFile:
    def __init__(self):
        self.deleted = False

    def delete(self, save: bool = False):
        self.deleted = True


class _DummyItem:
    def __init__(self):
        self.file = None
        self.file_name = ""
        self.file_size = 0
        self.page_count = 0
        self.page_start = None
        self.page_end = None
        self.saved = False

    def save(self, *args, **kwargs):
        self.saved = True


def test_upload_file_rejects_unsupported_format():
    svc = EvidenceFileService()
    item = _DummyItem()
    file = _DummyFile(name="a.exe", size=123)
    with pytest.raises(ValidationException) as e:
        svc.upload_file(item=item, file=file)
    assert e.value.code == "UNSUPPORTED_FILE_FORMAT"


def test_upload_file_rejects_large_file():
    svc = EvidenceFileService()
    item = _DummyItem()
    file = _DummyFile(name="a.jpg", size=EvidenceFileService.MAX_FILE_SIZE + 1)
    with pytest.raises(ValidationException) as e:
        svc.upload_file(item=item, file=file)
    assert e.value.code == "FILE_TOO_LARGE"


def test_upload_file_replaces_existing_file():
    svc = EvidenceFileService()
    item = _DummyItem()
    old = _DummyStoredFile()
    item.file = old

    file = _DummyFile(name="a.jpg", size=123)
    svc.upload_file(item=item, file=file)
    assert old.deleted is True
    assert item.file is file
    assert item.page_count == 1
    assert item.saved is True


def test_delete_file_clears_fields():
    svc = EvidenceFileService()
    item = _DummyItem()
    stored = _DummyStoredFile()
    item.file = stored
    item.file_name = "x"
    item.file_size = 1
    item.page_count = 2
    item.page_start = 1
    item.page_end = 2

    assert svc.delete_file(item=item) is True
    assert stored.deleted is True
    assert item.file is None
    assert item.file_name == ""
    assert item.file_size == 0
    assert item.page_count == 0
    assert item.page_start is None
    assert item.page_end is None
    assert item.saved is True
