"""ClientIdentityDocService 单元测试（第二轮覆盖）。

覆盖权限门槛、按类型 upsert、到期日更新、删除（含 on_commit 文件清理）、
上传端口委托与真实文件重命名（tmp_path MEDIA_ROOT）。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.client.models import ClientIdentityDoc
from apps.client.services.client_identity_doc_service import ClientIdentityDocService
from apps.core.exceptions import ForbiddenError, NotFoundError, ValidationException
from apps.testing.factories import ClientFactory, ClientIdentityDocFactory, LawyerFactory


def _lawyer(**kwargs):
    """用户名加随机后缀：避免 xdist 双 worker 共享测试库时 username 序列冲突。"""
    kwargs.setdefault("username", f"lawyer-{uuid4().hex[:12]}")
    return LawyerFactory(**kwargs)


class TestFileUploadPortLazy:
    def test_lazy_created_once(self) -> None:
        service = ClientIdentityDocService()
        first = service.file_upload_port
        assert first is not None
        assert service.file_upload_port is first


@pytest.mark.django_db
class TestGetIdentityDoc:
    def test_found(self) -> None:
        doc = ClientIdentityDocFactory()
        result = ClientIdentityDocService().get_identity_doc(doc.pk)
        assert result.pk == doc.pk

    def test_missing_raises(self) -> None:
        with pytest.raises(NotFoundError) as exc_info:
            ClientIdentityDocService().get_identity_doc(99999)
        assert exc_info.value.code == "IDENTITY_DOC_NOT_FOUND"

    def test_user_without_perm_denied(self) -> None:
        """B-14：无 client.view_client 权限的用户查看证件被拒。"""
        user = _lawyer()  # 普通用户无权限
        with pytest.raises(ForbiddenError, match="无权限查看客户证件"):
            ClientIdentityDocService().get_identity_doc(1, user=user)

    def test_superuser_allowed(self) -> None:
        doc = ClientIdentityDocFactory()
        admin = _lawyer(is_superuser=True)
        result = ClientIdentityDocService().get_identity_doc(doc.pk, user=admin)
        assert result.pk == doc.pk


@pytest.mark.django_db
class TestUpdateExpiryDate:
    def test_updates_field(self) -> None:
        doc = ClientIdentityDocFactory(expiry_date=None)
        ClientIdentityDocService().update_expiry_date(doc.pk, date(2027, 1, 31))
        doc.refresh_from_db()
        assert doc.expiry_date == date(2027, 1, 31)


@pytest.mark.django_db
class TestUpsertIdentityDocFile:
    def test_missing_client_raises(self) -> None:
        with pytest.raises(NotFoundError) as exc_info:
            ClientIdentityDocService().upsert_identity_doc_file(client_id=99999, doc_type="id_card", file_path="x")
        assert exc_info.value.code == "CLIENT_NOT_FOUND"

    def test_creates_when_absent(self) -> None:
        client = ClientFactory(client_type="natural")
        doc = ClientIdentityDocService().upsert_identity_doc_file(
            client_id=client.pk, doc_type="id_card", file_path="client_docs/a.jpg"
        )
        assert doc.client_id == client.pk
        assert doc.file_path == "client_docs/a.jpg"
        assert ClientIdentityDoc.objects.filter(client=client, doc_type="id_card").count() == 1

    def test_updates_existing_when_path_differs(self) -> None:
        client = ClientFactory(client_type="natural")
        service = ClientIdentityDocService()
        first = service.upsert_identity_doc_file(client_id=client.pk, doc_type="id_card", file_path="client_docs/a.jpg")
        second = service.upsert_identity_doc_file(
            client_id=client.pk, doc_type="id_card", file_path="client_docs/b.jpg"
        )
        assert second.pk == first.pk
        assert second.file_path == "client_docs/b.jpg"
        assert ClientIdentityDoc.objects.filter(client=client).count() == 1

    def test_same_path_no_extra_save(self) -> None:
        client = ClientFactory(client_type="natural")
        service = ClientIdentityDocService()
        first = service.upsert_identity_doc_file(client_id=client.pk, doc_type="id_card", file_path="client_docs/a.jpg")
        with patch.object(ClientIdentityDoc, "save") as mock_save:
            second = service.upsert_identity_doc_file(
                client_id=client.pk, doc_type="id_card", file_path="client_docs/a.jpg"
            )
            mock_save.assert_not_called()
        assert second.pk == first.pk


@pytest.mark.django_db
class TestDeleteIdentityDoc:
    def test_user_without_perm_denied(self) -> None:
        user = _lawyer()
        with pytest.raises(ForbiddenError, match="无权限删除客户证件"):
            ClientIdentityDocService().delete_identity_doc(1, user=user)

    def test_missing_doc_raises(self) -> None:
        admin = _lawyer(is_superuser=True)
        with pytest.raises(NotFoundError):
            ClientIdentityDocService().delete_identity_doc(99999, user=admin)

    def test_deletes_record_and_schedules_file_cleanup(self, django_capture_on_commit_callbacks: object) -> None:
        admin = _lawyer(is_superuser=True)
        doc = ClientIdentityDocFactory(file_path="client_docs/to-delete.jpg")

        with (
            patch(
                "apps.client.services.client_identity_doc_service.delete_media_file", return_value=True
            ) as mock_delete,
            django_capture_on_commit_callbacks(execute=True),
        ):  # type: ignore[attr-defined]
            ClientIdentityDocService().delete_identity_doc(doc.pk, user=admin)

        assert not ClientIdentityDoc.objects.filter(pk=doc.pk).exists()
        mock_delete.assert_called_once_with("client_docs/to-delete.jpg")

    def test_deletes_without_file_path(self, django_capture_on_commit_callbacks: object) -> None:
        admin = _lawyer(is_superuser=True)
        doc = ClientIdentityDocFactory(file_path="")

        with (
            patch(
                "apps.client.services.client_identity_doc_service.delete_media_file", return_value=True
            ) as mock_delete,
            django_capture_on_commit_callbacks(execute=True),
        ):  # type: ignore[attr-defined]
            ClientIdentityDocService().delete_identity_doc(doc.pk, user=admin)

        assert not ClientIdentityDoc.objects.filter(pk=doc.pk).exists()
        mock_delete.assert_not_called()


@pytest.mark.django_db
class TestSaveUploadedFileToDir:
    def test_delegates_to_storage(self) -> None:
        upload = SimpleUploadedFile("a.jpg", b"data")
        with patch(
            "apps.client.services.client_identity_doc_service.save_uploaded_file",
            return_value=("client_docs/uuid.jpg", "a.jpg"),
        ) as mock_save:
            result = ClientIdentityDocService().save_uploaded_file_to_dir(upload, rel_dir="client_docs")
        assert result == "client_docs/uuid.jpg"
        mock_save.assert_called_once_with(upload, rel_dir="client_docs")


@pytest.mark.django_db
class TestAddIdentityDocFromUpload:
    def test_saves_via_port_and_creates_doc(self) -> None:
        client = ClientFactory(client_type="natural")
        port = MagicMock()
        port.save_file.return_value = Path("client_docs/1/uploaded.jpg")
        upload = SimpleUploadedFile("uploaded.jpg", b"data")
        user = _lawyer(is_superuser=True)

        service = ClientIdentityDocService(file_upload_port=port)
        with patch(
            "apps.core.services.storage_service.normalize_to_media_rel",
            side_effect=lambda p: p,
        ):
            doc = service.add_identity_doc_from_upload(
                client_id=client.pk, doc_type="id_card", uploaded_file=upload, user=user
            )

        port.save_file.assert_called_once_with(upload, base_dir=f"client_docs/{client.pk}", preserve_name=True)
        assert doc.client_id == client.pk
        assert doc.doc_type == "id_card"
        assert doc.file_path == "client_docs/1/uploaded.jpg"

    def test_port_lazy_used_when_not_injected(self) -> None:
        service = ClientIdentityDocService()
        assert service.file_upload_port is not None


@pytest.mark.django_db
class TestAddIdentityDocValidation:
    """add_identity_doc 的路径收敛与权限门槛（B-14）。"""

    def test_dotdot_path_rejected(self) -> None:
        client = ClientFactory(client_type="natural")
        with pytest.raises(ValidationException) as exc_info:
            ClientIdentityDocService().add_identity_doc(
                client_id=client.pk, doc_type="id_card", file_path="../etc/passwd"
            )
        assert exc_info.value.code == "INVALID_FILE_PATH"

    def test_missing_client_raises(self) -> None:
        with pytest.raises(NotFoundError) as exc_info:
            ClientIdentityDocService().add_identity_doc(client_id=99999, doc_type="id_card", file_path="a.jpg")
        assert exc_info.value.code == "CLIENT_NOT_FOUND"

    def test_user_without_perm_denied(self) -> None:
        client = ClientFactory(client_type="natural")
        user = _lawyer()
        with pytest.raises(ForbiddenError, match="无权限添加客户证件"):
            ClientIdentityDocService().add_identity_doc(
                client_id=client.pk, doc_type="id_card", file_path="a.jpg", user=user
            )


@pytest.mark.django_db
class TestRenameUploadedFile:
    """真实文件重命名：tmp MEDIA_ROOT + 首选名冲突递增。"""

    def test_renames_to_display_and_client_name(self, tmp_path: Path) -> None:
        client = ClientFactory(name="张三公司", client_type="legal")
        doc = ClientIdentityDocFactory(client=client, doc_type="business_license", file_path="")
        source = tmp_path / "raw.pdf"
        source.write_bytes(b"pdf")
        doc.file_path = str(source)
        doc.save(update_fields=["file_path"])

        with override_settings(MEDIA_ROOT=str(tmp_path)):
            ClientIdentityDocService().rename_uploaded_file(doc)

        doc.refresh_from_db()
        assert doc.file_path == "营业执照_张三公司.pdf"
        assert (tmp_path / "营业执照_张三公司.pdf").exists()
        assert not source.exists()

    def test_name_conflict_appends_counter(self, tmp_path: Path) -> None:
        client = ClientFactory(name="李四公司", client_type="legal")
        (tmp_path / "营业执照_李四公司.pdf").write_bytes(b"existing")
        doc = ClientIdentityDocFactory(client=client, doc_type="business_license", file_path="")
        source = tmp_path / "raw2.pdf"
        source.write_bytes(b"pdf2")
        doc.file_path = str(source)
        doc.save(update_fields=["file_path"])

        with override_settings(MEDIA_ROOT=str(tmp_path)):
            ClientIdentityDocService().rename_uploaded_file(doc)

        doc.refresh_from_db()
        assert doc.file_path == "营业执照_李四公司_1.pdf"
        assert (tmp_path / "营业执照_李四公司_1.pdf").exists()

    def test_missing_file_noop(self, tmp_path: Path) -> None:
        client = ClientFactory(name="王五公司", client_type="legal")
        doc = ClientIdentityDocFactory(client=client, doc_type="business_license", file_path="not_exists.pdf")
        original_path = doc.file_path

        with override_settings(MEDIA_ROOT=str(tmp_path)):
            ClientIdentityDocService().rename_uploaded_file(doc)

        doc.refresh_from_db()
        assert doc.file_path == original_path

    def test_empty_file_path_noop(self) -> None:
        doc = ClientIdentityDocFactory(file_path="")
        ClientIdentityDocService().rename_uploaded_file(doc)
        doc.refresh_from_db()
        # 空值经 save 钩子归一为 NULL（占位行语义），rename 对空路径仍是 no-op
        assert doc.file_path is None


@pytest.mark.django_db
class TestRenameUploadedFileById:
    def test_missing_doc_logged_not_raised(self) -> None:
        """_rename_uploaded_file_by_id 吞掉异常（get_identity_doc 抛 NotFoundError）。"""
        # 无返回值契约 + 异常吞并：返回 None 且不抛
        assert ClientIdentityDocService()._rename_uploaded_file_by_id(99999) is None

    def test_renames_existing_doc(self, tmp_path: Path) -> None:
        client = ClientFactory(name="赵六公司", client_type="legal")
        doc = ClientIdentityDocFactory(client=client, doc_type="business_license", file_path="")
        source = tmp_path / "raw3.pdf"
        source.write_bytes(b"pdf3")
        doc.file_path = str(source)
        doc.save(update_fields=["file_path"])

        with override_settings(MEDIA_ROOT=str(tmp_path)):
            ClientIdentityDocService()._rename_uploaded_file_by_id(doc.pk)

        doc.refresh_from_db()
        assert doc.file_path == "营业执照_赵六公司.pdf"
