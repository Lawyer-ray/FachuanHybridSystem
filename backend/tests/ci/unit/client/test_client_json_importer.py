"""ClientJsonImporter 单元测试。

覆盖延迟属性注入与 import_from_json 的真实编排（合法法人客户 + 证件、
非法数据抛 ValidationException）。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.client.models import Client, ClientIdentityDoc
from apps.client.services.importer.importer import ClientJsonImporter
from apps.core.exceptions import ValidationException


class TestLazyProperties:
    def test_all_lazy_created_once(self) -> None:
        importer = ClientJsonImporter()
        assert importer.validator is not None
        assert importer.validator is importer.validator
        assert importer.mapper is not None
        assert importer.mapper is importer.mapper
        assert importer.persister is not None
        assert importer.persister is importer.persister


@pytest.mark.django_db
class TestImportFromJson:
    def test_valid_legal_client_with_docs(self) -> None:
        json_data = {
            "name": "导入甲公司",
            "client_type": "legal",
            "legal_representative": "李代表",
            "phone": "13800000000",
            "is_our_client": True,
            "identity_docs": [
                {"doc_type": "business_license", "file_path": "client_docs/bl.pdf"},
                {"doc_type": "legal_rep_id_card", "file_path": "client_docs/lr.pdf"},
            ],
        }

        result = ClientJsonImporter().import_from_json(json_data, admin_user="admin")

        assert result.success is True
        client = Client.objects.get(pk=result.client_id)
        assert client.name == "导入甲公司"
        assert client.legal_representative == "李代表"
        assert client.is_our_client is True
        docs = set(ClientIdentityDoc.objects.filter(client=client).values_list("doc_type", flat=True))
        assert docs == {"business_license", "legal_rep_id_card"}

    def test_natural_client_without_legal_rep(self) -> None:
        json_data = {"name": "张三", "client_type": "natural"}
        result = ClientJsonImporter().import_from_json(json_data, admin_user="admin")
        assert result.success is True
        client = Client.objects.get(pk=result.client_id)
        assert client.client_type == "natural"

    def test_invalid_data_raises(self) -> None:
        with pytest.raises(ValidationException) as exc_info:
            ClientJsonImporter().import_from_json({"name": "", "client_type": "legal"}, admin_user="admin")
        assert exc_info.value.code == "INVALID_JSON"

    def test_invalid_identity_docs_raises(self) -> None:
        json_data = {
            "name": "乙公司",
            "client_type": "legal",
            "legal_representative": "王代表",
            "identity_docs": [{"doc_type": "", "file_path": ""}],
        }
        with pytest.raises(ValidationException):
            ClientJsonImporter().import_from_json(json_data, admin_user="admin")

    def test_is_our_client_defaults_false(self) -> None:
        json_data = {"name": "丙公司", "client_type": "legal", "legal_representative": "赵代表"}
        result = ClientJsonImporter().import_from_json(json_data, admin_user="admin")
        assert result.success is True
        assert Client.objects.get(pk=result.client_id).is_our_client is False


@pytest.mark.django_db
class TestInjectedCollaborators:
    def test_validator_short_circuits_before_persist(self) -> None:
        """注入的 validator 抛错时 persister 不被调用。"""
        from apps.client.services.importer.mapper import ClientJsonImportMapper
        from apps.client.services.importer.persister import ClientJsonImportPersister
        from apps.client.services.importer.validator import ClientJsonImportValidator

        real_validator = ClientJsonImportValidator()

        class StrictValidator:
            def validate(self, json_data: dict) -> None:
                real_validator.validate(json_data)
                if json_data.get("name") == "拒绝名单":
                    raise ValidationException(message="拒绝导入", code="REJECTED")

        persister_mock = ClientJsonImportPersister()
        importer = ClientJsonImporter(
            validator=StrictValidator(),  # type: ignore[arg-type]
            mapper=ClientJsonImportMapper(),
            persister=persister_mock,
        )
        with patch.object(persister_mock, "persist") as mock_persist:
            with pytest.raises(ValidationException, match="拒绝导入"):
                importer.import_from_json({"name": "拒绝名单", "client_type": "natural"}, admin_user="admin")
            mock_persist.assert_not_called()
