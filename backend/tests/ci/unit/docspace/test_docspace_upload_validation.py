"""DocSpace 上传校验测试（类型白名单 + 大小上限，校验先于 read() 进内存）。"""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.exceptions import ValidationException
from apps.docspace.api.docspace_api import _DOCSPACE_MAX_UPLOAD_SIZE_BYTES, _validate_upload


class TestValidateUpload:
    def test_html_rejected(self) -> None:
        f = SimpleUploadedFile("x.html", b"<html/>", content_type="text/html")
        with pytest.raises(ValidationException, match="不支持的文件格式"):
            _validate_upload(f)

    def test_executable_rejected(self) -> None:
        f = SimpleUploadedFile("x.exe", b"MZ", content_type="application/octet-stream")
        with pytest.raises(ValidationException, match="不支持的文件格式"):
            _validate_upload(f)

    def test_no_extension_rejected(self) -> None:
        f = SimpleUploadedFile("noext", b"data", content_type="application/octet-stream")
        with pytest.raises(ValidationException, match="不支持的文件格式"):
            _validate_upload(f)

    def test_oversized_rejected(self) -> None:
        f = SimpleUploadedFile("big.docx", b"tiny", content_type="application/vnd...")
        f.size = _DOCSPACE_MAX_UPLOAD_SIZE_BYTES + 1
        with pytest.raises(ValidationException, match="文件过大"):
            _validate_upload(f)

    @pytest.mark.parametrize("name", ["a.docx", "b.doc", "c.pdf", "d.xlsx", "e.pptx", "f.txt", "g.md", "h.csv"])
    def test_document_types_accepted(self, name: str) -> None:
        f = SimpleUploadedFile(name, b"ok", content_type="application/octet-stream")
        assert _validate_upload(f) is None
