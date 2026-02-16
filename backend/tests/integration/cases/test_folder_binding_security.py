import io
import zipfile
from types import SimpleNamespace

import pytest

from apps.cases.services import CaseFolderBindingService
from apps.core.exceptions import ValidationException


class TestCaseFolderBindingSecurity:
    def test_save_file_rejects_traversal_filename(self, tmp_path, monkeypatch):
        service = CaseFolderBindingService()
        monkeypatch.setattr(
            service,
            "get_binding",
            lambda *args, **kwargs: SimpleNamespace(folder_path=str(tmp_path)),
        )
        monkeypatch.setattr(service, "_get_case_internal", lambda case_id: SimpleNamespace(case_type="civil"))
        monkeypatch.setattr(service, "_get_subdir_path_from_template_binding", lambda *args, **kwargs: "案件文书")

        with pytest.raises(ValidationException):
            service.save_file_to_bound_folder(
                case_id=1,
                file_content=b"evil",
                file_name="../evil.txt",
                user=None,
                perm_open_access=True,
            )

    def test_save_file_rejects_traversal_subdir(self, tmp_path, monkeypatch):
        service = CaseFolderBindingService()
        monkeypatch.setattr(
            service,
            "get_binding",
            lambda *args, **kwargs: SimpleNamespace(folder_path=str(tmp_path)),
        )
        monkeypatch.setattr(service, "_get_case_internal", lambda case_id: SimpleNamespace(case_type="civil"))
        monkeypatch.setattr(service, "_get_subdir_path_from_template_binding", lambda *args, **kwargs: "../escape")

        with pytest.raises(ValidationException):
            service.save_file_to_bound_folder(
                case_id=1,
                file_content=b"evil",
                file_name="ok.txt",
                user=None,
                perm_open_access=True,
            )

    def test_extract_zip_blocks_zip_slip(self, tmp_path, monkeypatch):
        service = CaseFolderBindingService()
        monkeypatch.setattr(
            service,
            "get_binding",
            lambda *args, **kwargs: SimpleNamespace(folder_path=str(tmp_path)),
        )

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("../evil.txt", b"pwned")

        with pytest.raises(ValidationException):
            service.extract_zip_to_bound_folder(case_id=1, zip_content=buf.getvalue(), user=None, perm_open_access=True)

    def test_extract_zip_allows_safe_files(self, tmp_path, monkeypatch):
        service = CaseFolderBindingService()
        monkeypatch.setattr(
            service,
            "get_binding",
            lambda *args, **kwargs: SimpleNamespace(folder_path=str(tmp_path)),
        )

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("nested/ok.txt", b"ok")

        out = service.extract_zip_to_bound_folder(
            case_id=1, zip_content=buf.getvalue(), user=None, perm_open_access=True
        )
        assert out == str(tmp_path)
        assert (tmp_path / "nested" / "ok.txt").read_bytes() == b"ok"
