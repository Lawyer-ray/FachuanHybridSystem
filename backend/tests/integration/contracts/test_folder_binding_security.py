import io
import zipfile
from types import SimpleNamespace

import pytest

from apps.contracts.services.folder_binding_service import FolderBindingService
from apps.core.exceptions import ValidationException


class TestFolderBindingSecurity:
    def test_sanitize_file_name_rejects_traversal(self):
        service = FolderBindingService()
        with pytest.raises(ValidationException):
            service._sanitize_file_name("../evil.txt")

        with pytest.raises(ValidationException):
            service._sanitize_file_name("a/b.txt")

        with pytest.raises(ValidationException):
            service._sanitize_file_name("C:\\evil.txt")

    def test_normalize_relative_path_rejects_traversal(self):
        service = FolderBindingService()
        with pytest.raises(ValidationException):
            service._normalize_relative_path("../evil.txt")

        with pytest.raises(ValidationException):
            service._normalize_relative_path("/abs/evil.txt")

        with pytest.raises(ValidationException):
            service._normalize_relative_path("C:/evil.txt")

    def test_extract_zip_blocks_zip_slip(self, tmp_path, monkeypatch):
        service = FolderBindingService()
        monkeypatch.setattr(
            service,
            "get_binding",
            lambda contract_id: SimpleNamespace(folder_path=str(tmp_path)),
        )

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("../evil.txt", b"pwned")

        with pytest.raises(ValidationException):
            service.extract_zip_to_bound_folder(contract_id=1, zip_content=buf.getvalue())

    def test_extract_zip_allows_safe_files(self, tmp_path, monkeypatch):
        service = FolderBindingService()
        monkeypatch.setattr(
            service,
            "get_binding",
            lambda contract_id: SimpleNamespace(folder_path=str(tmp_path)),
        )

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("nested/ok.txt", b"ok")

        out = service.extract_zip_to_bound_folder(contract_id=1, zip_content=buf.getvalue())
        assert out == str(tmp_path)
        assert (tmp_path / "nested" / "ok.txt").read_bytes() == b"ok"
