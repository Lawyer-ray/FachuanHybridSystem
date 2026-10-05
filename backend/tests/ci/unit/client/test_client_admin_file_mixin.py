"""ClientAdminFileMixin 单元测试。

覆盖 _handle_file_storage 三分支、_save_uploaded_file 的首选名拼接与
缺文件名回退、_update_identity_doc、save_and_rename_file（含真实重命名）。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.client.services.client_admin_file_mixin import ClientAdminFileMixin
from apps.client.services.client_identity_doc_service import ClientIdentityDocService
from apps.testing.factories import ClientFactory, ClientIdentityDocFactory


def _make_mixin(identity_service: MagicMock | ClientIdentityDocService | None = None) -> ClientAdminFileMixin:
    mixin = ClientAdminFileMixin()
    mixin.identity_doc_service = identity_service or ClientIdentityDocService()  # type: ignore[assignment]
    return mixin


class TestHandleFileStorage:
    def test_file_path_passthrough(self) -> None:
        mixin = _make_mixin()
        assert mixin._handle_file_storage({"file_path": "client_docs/a.jpg"}) == "client_docs/a.jpg"

    def test_no_file_returns_none(self) -> None:
        mixin = _make_mixin()
        assert mixin._handle_file_storage({}) is None

    def test_uploaded_file_saved(self) -> None:
        mixin = _make_mixin()
        upload = SimpleUploadedFile("x.jpg", b"data")
        with patch.object(mixin, "_save_uploaded_file", return_value="client_docs/saved.jpg") as mock_save:
            result = mixin._handle_file_storage(
                {"uploaded_file": upload}, client_name="客户", doc_type_display="身份证"
            )
        assert result == "client_docs/saved.jpg"
        mock_save.assert_called_once_with(upload, "客户", "身份证")


class TestSaveUploadedFile:
    def test_missing_name_returns_empty(self) -> None:
        mixin = _make_mixin()
        assert mixin._save_uploaded_file(object(), "客户", "身份证") == ""

    def test_saves_with_preferred_filename(self) -> None:
        mixin = _make_mixin()
        upload = SimpleUploadedFile("raw.jpg", b"data")
        with patch(
            "apps.client.services.client_admin_file_mixin.save_uploaded_file",
            return_value=("client_docs/target.jpg", "raw.jpg"),
        ) as mock_save:
            result = mixin._save_uploaded_file(upload, "客户甲", "营业执照")

        assert result == "client_docs/target.jpg"
        mock_save.assert_called_once_with(
            upload,
            rel_dir="client_docs",
            preferred_filename="客户甲_营业执照",
        )

    def test_saves_without_preferred_when_missing_parts(self) -> None:
        mixin = _make_mixin()
        upload = SimpleUploadedFile("raw.jpg", b"data")
        with patch(
            "apps.client.services.client_admin_file_mixin.save_uploaded_file",
            return_value=("client_docs/uuid.jpg", "raw.jpg"),
        ) as mock_save:
            result = mixin._save_uploaded_file(upload)

        assert result == "client_docs/uuid.jpg"
        mock_save.assert_called_once_with(upload, rel_dir="client_docs", preferred_filename=None)


@pytest.mark.django_db
class TestUpdateIdentityDoc:
    def test_updates_path(self) -> None:
        doc = ClientIdentityDocFactory(file_path="client_docs/old.jpg")
        mixin = _make_mixin()
        mixin._update_identity_doc(doc.pk, "client_docs/new.jpg", "admin")
        doc.refresh_from_db()
        assert doc.file_path == "client_docs/new.jpg"


@pytest.mark.django_db
class TestSaveAndRenameFile:
    def test_empty_saved_path_returns_empty_without_touching_doc(self) -> None:
        doc = ClientIdentityDocFactory(file_path="client_docs/keep.jpg")
        mixin = _make_mixin()
        with patch.object(mixin, "_save_uploaded_file", return_value=""):
            result = mixin.save_and_rename_file(doc.client_id, doc.client.name, doc.pk, doc.doc_type, object())
        assert result == ""
        doc.refresh_from_db()
        assert doc.file_path == "client_docs/keep.jpg"

    def test_success_flow_updates_and_renames(self, tmp_path: Path) -> None:
        client = ClientFactory(name="_rename客户", client_type="legal")
        doc = ClientIdentityDocFactory(client=client, doc_type="business_license", file_path="")
        # 预置重命名源文件（save_uploaded_file 返回的相对路径）
        source = tmp_path / "raw-license.pdf"
        source.write_bytes(b"pdf")
        doc.file_path = str(source)
        doc.save(update_fields=["file_path"])
        upload = SimpleUploadedFile("raw-license.pdf", b"pdf")

        mixin = _make_mixin()
        with patch(
            "apps.client.services.client_admin_file_mixin.save_uploaded_file",
            return_value=(str(source), "raw-license.pdf"),
        ):
            with override_settings(MEDIA_ROOT=str(tmp_path)):
                result = mixin.save_and_rename_file(client.pk, client.name, doc.pk, "business_license", upload)

        assert result == str(source)
        doc.refresh_from_db()
        # 重命名后 file_path 更新为「类型_客户名」的相对路径
        assert doc.file_path == "营业执照_rename客户.pdf"
        assert (tmp_path / "营业执照_rename客户.pdf").exists()
