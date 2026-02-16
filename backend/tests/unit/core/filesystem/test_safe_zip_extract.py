from __future__ import annotations

import io
import tempfile
import zipfile

import pytest

from apps.core.exceptions import ValidationException
from apps.core.filesystem import FolderFilesystemService


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_extract_zip_bytes_blocks_traversal():
    service = FolderFilesystemService()
    with tempfile.TemporaryDirectory() as tmp:
        content = _zip_bytes({"../evil.txt": b"x"})
        with pytest.raises(ValidationException):
            service.extract_zip_bytes(tmp, content)


def test_extract_zip_bytes_writes_files_under_base():
    service = FolderFilesystemService()
    with tempfile.TemporaryDirectory() as tmp:
        content = _zip_bytes({"a/b.txt": b"hello"})
        out_dir = service.extract_zip_bytes(tmp, content)
        with open(f"{out_dir}/a/b.txt", "rb") as f:
            assert f.read() == b"hello"
