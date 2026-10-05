"""ClientAdminService 单元测试。

覆盖延迟属性、JSON 导入编排（成功/失败）、表单集文件处理
（DELETE 跳过、缺证件类型跳过、更新 vs 新增证件）。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.client.services.client_admin_service import ClientAdminService, ImportResult
from apps.core.exceptions import ValidationException
from apps.testing.factories import ClientFactory


def _make_service() -> tuple[ClientAdminService, MagicMock, MagicMock]:
    identity = MagicMock()
    internal = MagicMock()
    service = ClientAdminService(identity_doc_service=identity, internal_query_service=internal)
    return service, identity, internal


class TestLazyProperties:
    def test_identity_doc_service_lazy_created_once(self) -> None:
        service = ClientAdminService()
        first = service.identity_doc_service
        assert first is not None
        assert service.identity_doc_service is first

    def test_internal_query_service_lazy_created_once(self) -> None:
        service = ClientAdminService()
        first = service.internal_query_service
        assert first is not None
        assert service.internal_query_service is first


@pytest.mark.django_db
class TestImportFromJson:
    def test_success_returns_client(self) -> None:
        from apps.client.services.importer.importer import ClientJsonImportResult

        client = ClientFactory(name="导入客户")
        service, _, internal = _make_service()
        internal.get_client.return_value = client
        importer = MagicMock()
        importer.import_from_json.return_value = ClientJsonImportResult(success=True, client_id=client.pk)

        with patch("apps.client.services.importer.ClientJsonImporter", return_value=importer):
            result = service.import_from_json({"name": "导入客户"}, admin_user="admin")

        assert result.success is True
        assert result.client is client
        internal.get_client.assert_called_once_with(client_id=client.pk)

    def test_failure_returns_error_message(self) -> None:
        from apps.client.services.importer.importer import ClientJsonImportResult

        service, _, internal = _make_service()
        importer = MagicMock()
        importer.import_from_json.return_value = ClientJsonImportResult(success=False, error_message="JSON 无效")

        with patch("apps.client.services.importer.ClientJsonImporter", return_value=importer):
            result = service.import_from_json({}, admin_user="admin")

        assert result.success is False
        assert result.error_message == "JSON 无效"
        assert result.client is None
        internal.get_client.assert_not_called()

    def test_success_without_client_id_treated_as_failure(self) -> None:
        from apps.client.services.importer.importer import ClientJsonImportResult

        service, _, internal = _make_service()
        importer = MagicMock()
        importer.import_from_json.return_value = ClientJsonImportResult(success=True, client_id=None)

        with patch("apps.client.services.importer.ClientJsonImporter", return_value=importer):
            result = service.import_from_json({"name": "x"}, admin_user="admin")

        assert result.success is False
        assert result.error_message is None
        internal.get_client.assert_not_called()


@pytest.mark.django_db
class TestProcessFormsetFiles:
    def test_missing_client_raises(self) -> None:
        service, _, internal = _make_service()
        internal.get_client.return_value = None
        with pytest.raises(ValidationException) as exc_info:
            service.process_formset_files(99999, [], admin_user="admin")
        assert exc_info.value.code == "CLIENT_NOT_FOUND"

    def _make_service_with_storage(
        self, storage_results: dict[str, str | None]
    ) -> tuple[ClientAdminService, MagicMock, MagicMock, MagicMock]:
        service, identity, internal = _make_service()
        client = ClientFactory(name="表单客户")
        internal.get_client.return_value = client
        storage = MagicMock(side_effect=lambda form_data, name, display: storage_results.get(form_data.get("doc_type")))
        service._handle_file_storage = storage  # type: ignore[method-assign]
        return service, identity, internal, storage

    def test_mixed_forms(self) -> None:
        service, identity, _, storage = self._make_service_with_storage(
            {"id_card": "client_docs/a.jpg", "passport": None, "residence_permit": "z"}
        )
        existing_doc = MagicMock()
        existing_doc.pk = 31

        def _get_doc(doc_id: int):
            return existing_doc

        identity.get_identity_doc.side_effect = _get_doc

        service.process_formset_files(
            client_id=1,
            formset_data=[
                {"DELETE": True, "file_path": "x", "doc_type": "id_card"},  # DELETE 跳过
                {"doc_type": "id_card", "file_path": "old", "id": 31},  # 更新既有证件
                {"doc_type": "passport", "uploaded_file": object()},  # 存储失败 → None
                {"doc_type": "", "file_path": "y"},  # 缺证件类型 → None
                {"doc_type": "residence_permit", "file_path": "z"},  # 新增证件
            ],
            admin_user="admin",
        )

        # 仅 2 次落库：1 次更新（doc_id=31），1 次新增
        assert existing_doc.pk == 31
        identity.get_identity_doc.assert_called_once_with(31)
        assert existing_doc.file_path == "client_docs/a.jpg"
        client_id_used = identity.add_identity_doc.call_args.kwargs["client_id"]
        identity.add_identity_doc.assert_called_once_with(
            client_id=client_id_used, doc_type="residence_permit", file_path="z"
        )
        assert storage.call_count == 3  # DELETE 表单不进入存储

    def test_delete_form_skipped_entirely(self) -> None:
        service, identity, internal, storage = self._make_service_with_storage({})
        service.process_formset_files(client_id=1, formset_data=[{"DELETE": True}], admin_user="admin")
        storage.assert_not_called()
        identity.add_identity_doc.assert_not_called()

    def test_form_without_file_skipped(self) -> None:
        service, identity, _, storage = self._make_service_with_storage({})
        service.process_formset_files(client_id=1, formset_data=[{"doc_type": "id_card"}], admin_user="admin")
        storage.assert_not_called()


class TestShouldProcessForm:
    def setup_method(self) -> None:
        self.service, _, _ = _make_service()

    def test_delete_false(self) -> None:
        assert self.service._should_process_form({"DELETE": True, "file_path": "x"}) is False

    def test_file_path_true(self) -> None:
        assert self.service._should_process_form({"file_path": "x"}) is True

    def test_uploaded_file_true(self) -> None:
        assert self.service._should_process_form({"uploaded_file": object()}) is True

    def test_neither_false(self) -> None:
        assert self.service._should_process_form({"doc_type": "id_card"}) is False


@pytest.mark.django_db
class TestProcessSingleForm:
    def test_missing_doc_type_returns_none(self) -> None:
        service, identity, _ = _make_service()
        client = ClientFactory(name="单表单客户")
        result = service._process_single_form(client, {"file_path": "x"}, "admin")
        assert result is None
        identity.add_identity_doc.assert_not_called()

    def test_storage_failure_returns_none(self) -> None:
        service, identity, _ = _make_service()
        client = ClientFactory(name="单表单客户")
        service._handle_file_storage = MagicMock(return_value=None)  # type: ignore[method-assign]
        result = service._process_single_form(client, {"doc_type": "id_card", "file_path": "x"}, "admin")
        assert result is None
        identity.add_identity_doc.assert_not_called()

    def test_new_doc_returns_file_info(self) -> None:
        service, identity, _ = _make_service()
        client = ClientFactory(name="单表单客户")
        service._handle_file_storage = MagicMock(return_value="client_docs/new.jpg")  # type: ignore[method-assign]

        result = service._process_single_form(client, {"doc_type": "id_card"}, "admin")

        assert result == {"doc_type": "id_card", "file_path": "client_docs/new.jpg", "doc_id": None}
        identity.add_identity_doc.assert_called_once_with(
            client_id=client.pk, doc_type="id_card", file_path="client_docs/new.jpg"
        )

    def test_existing_doc_updated(self) -> None:
        service, identity, _ = _make_service()
        client = ClientFactory(name="单表单客户")
        service._handle_file_storage = MagicMock(return_value="client_docs/upd.jpg")  # type: ignore[method-assign]
        doc = MagicMock()

        def _get_doc(doc_id: int):
            assert doc_id == 5
            return doc

        identity.get_identity_doc.side_effect = _get_doc

        result = service._process_single_form(client, {"doc_type": "id_card", "id": 5}, "admin")

        assert result == {"doc_type": "id_card", "file_path": "client_docs/upd.jpg", "doc_id": 5}
        assert doc.file_path == "client_docs/upd.jpg"
        doc.save.assert_called_once_with(update_fields=["file_path"])
        identity.add_identity_doc.assert_not_called()


class TestImportResultDataclass:
    def test_defaults(self) -> None:
        result = ImportResult(success=False)
        assert result.client is None
        assert result.error_message is None
