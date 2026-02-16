import pytest

from apps.client.models import Client, ClientIdentityDoc
from apps.client.services.client_admin_service import ClientAdminService
from apps.core.exceptions import ValidationException


@pytest.mark.unit
@pytest.mark.django_db
class TestClientAdminService:
    def test_import_from_json_creates_client_and_identity_docs(self):
        service = ClientAdminService()
        payload = {
            "name": "张三",
            "client_type": Client.NATURAL,
            "phone": "13800000000",
            "address": "广州市天河区",
            "is_our_client": True,
            "identity_docs": [
                {
                    "doc_type": ClientIdentityDoc.ID_CARD,
                    "file_path": "client_identity_docs/zhangsan_id_card.jpg",
                }
            ],
        }

        result = service.import_from_json(payload, admin_user="admin")

        assert result.success is True
        assert result.client is not None
        assert result.client.name == "张三"
        assert result.client.client_type == Client.NATURAL
        assert result.client.is_our_client is True
        assert ClientIdentityDoc.objects.filter(client_id=result.client.id).count() == 1

    def test_import_from_json_requires_name(self):
        service = ClientAdminService()
        payload = {"client_type": Client.NATURAL}

        with pytest.raises(ValidationException) as exc_info:
            service.import_from_json(payload, admin_user="admin")

        assert exc_info.value.errors.get("name") == "客户名称不能为空"

    def test_import_from_json_legal_requires_legal_representative(self):
        service = ClientAdminService()
        payload = {"name": "某公司", "client_type": Client.LEGAL}

        with pytest.raises(ValidationException) as exc_info:
            service.import_from_json(payload, admin_user="admin")

        assert "法定代表人" in (exc_info.value.errors.get("legal_representative") or "")
