"""
客户服务单元测试
"""

from unittest.mock import Mock

import pytest
from django.contrib.auth import get_user_model

from apps.client.models import Client
from apps.client.services.client_service import ClientService
from apps.client.services.client_mutation_service import ClientMutationService
from apps.core.exceptions import NotFoundError, PermissionDenied, ValidationException
from tests.factories.client_factories import ClientFactory

User = get_user_model()


@pytest.mark.django_db
class TestClientServiceRead:
    """客户只读服务测试"""

    def setup_method(self) -> None:
        self.service = ClientService()

    def test_list_clients_success(self) -> None:
        """测试获取客户列表成功"""
        ClientFactory.create_batch(5)
        clients = self.service.list_clients(page=1, page_size=10)
        assert len(list(clients)) == 5

    def test_list_clients_with_filters(self) -> None:
        """测试带过滤条件的客户列表"""
        ClientFactory(client_type=Client.NATURAL, is_our_client=True)
        ClientFactory(client_type=Client.LEGAL, is_our_client=False)
        ClientFactory(client_type=Client.NATURAL, is_our_client=True)

        clients = self.service.list_clients(client_type=Client.NATURAL)
        assert len(list(clients)) == 2

        clients = self.service.list_clients(is_our_client=True)
        assert len(list(clients)) == 2

    def test_list_clients_with_search(self) -> None:
        """测试搜索客户"""
        ClientFactory(name="张三")
        ClientFactory(name="李四")
        ClientFactory(name="王五")

        clients = self.service.list_clients(search="张")
        clients_list = list(clients)
        assert len(clients_list) == 1
        assert clients_list[0].name == "张三"

    def test_list_clients_pagination(self) -> None:
        """测试分页"""
        ClientFactory.create_batch(25)

        clients_page1 = self.service.list_clients(page=1, page_size=10)
        assert len(list(clients_page1)) == 10

        clients_page2 = self.service.list_clients(page=2, page_size=10)
        assert len(list(clients_page2)) == 10

        clients_page3 = self.service.list_clients(page=3, page_size=10)
        assert len(list(clients_page3)) == 5

    def test_get_client_success(self) -> None:
        """测试获取客户成功"""
        client = ClientFactory()
        result = self.service.get_client(client.id)  # type: ignore[attr-defined]
        assert result.id == client.id  # type: ignore[attr-defined]
        assert result.name == client.name

    def test_get_client_not_found(self) -> None:
        """测试获取不存在的客户"""
        with pytest.raises(NotFoundError) as exc_info:
            self.service.get_client(99999)
        assert "客户不存在" in exc_info.value.message  # type: ignore[operator]
        assert exc_info.value.code == "CLIENT_NOT_FOUND"

    def test_get_clients_by_ids(self) -> None:
        """测试批量获取客户"""
        client1 = ClientFactory()
        client2 = ClientFactory()
        client3 = ClientFactory()

        clients = self.service.get_clients_by_ids([client1.id, client2.id])  # type: ignore[attr-defined]
        assert len(clients) == 2
        client_ids = [c.id for c in clients]
        assert client1.id in client_ids  # type: ignore[attr-defined]
        assert client2.id in client_ids  # type: ignore[attr-defined]
        assert client3.id not in client_ids  # type: ignore[attr-defined]


def _make_user(*, has_perm: bool = True) -> Mock:
    """创建模拟用户"""
    user = Mock()
    user.id = 1
    user.is_authenticated = True
    user.is_admin = has_perm
    user.is_superuser = False
    user.has_perm = Mock(return_value=has_perm)
    return user


@pytest.mark.django_db
class TestClientMutationService:
    """客户写操作服务测试"""

    def setup_method(self) -> None:
        self.service = ClientMutationService()

    def test_create_client_success(self) -> None:
        """测试创建客户成功"""
        user = _make_user()
        data = {
            "name": "测试客户",
            "client_type": Client.NATURAL,
            "phone": "13800138000",
            "id_number": "110101199001010001",
            "address": "测试地址",
            "legal_representative": "",
            "is_our_client": True,
        }
        client = self.service.create_client(data=data, user=user)
        assert client.id is not None
        assert client.name == "测试客户"
        assert client.client_type == Client.NATURAL
        assert client.phone == "13800138000"

    def test_create_client_permission_denied(self) -> None:
        """测试创建客户权限不足"""
        user = _make_user(has_perm=False)
        data = {"name": "测试客户", "client_type": Client.NATURAL}
        with pytest.raises(PermissionDenied):
            self.service.create_client(data=data, user=user)

    def test_create_client_invalid_name(self) -> None:
        """测试创建客户名称为空"""
        user = _make_user()
        data = {"name": "", "client_type": Client.NATURAL}
        with pytest.raises(ValidationException) as exc_info:
            self.service.create_client(data=data, user=user)
        assert exc_info.value.code == "INVALID_NAME"

    def test_create_client_invalid_type(self) -> None:
        """测试创建客户类型无效"""
        user = _make_user()
        data = {"name": "测试客户", "client_type": "invalid_type"}
        with pytest.raises(ValidationException) as exc_info:
            self.service.create_client(data=data, user=user)
        assert exc_info.value.code == "INVALID_CLIENT_TYPE"

    def test_create_client_legal_without_representative(self) -> None:
        """测试创建法人客户但未填写法定代表人"""
        user = _make_user()
        data = {"name": "测试公司", "client_type": Client.LEGAL}
        with pytest.raises(ValidationException) as exc_info:
            self.service.create_client(data=data, user=user)
        assert exc_info.value.code == "MISSING_LEGAL_REPRESENTATIVE"

    def test_update_client_success(self) -> None:
        """测试更新客户成功"""
        client = ClientFactory(name="旧名称")
        user = _make_user()
        result = self.service.update_client(client_id=client.id, data={"name": "新名称"}, user=user)  # type: ignore[attr-defined]
        assert result.name == "新名称"
        client.refresh_from_db()  # type: ignore[attr-defined]
        assert client.name == "新名称"

    def test_update_client_not_found(self) -> None:
        """测试更新不存在的客户"""
        user = _make_user()
        with pytest.raises(NotFoundError):
            self.service.update_client(client_id=99999, data={"name": "新名称"}, user=user)

    def test_update_client_permission_denied(self) -> None:
        """测试更新客户权限不足"""
        client = ClientFactory()
        user = _make_user(has_perm=False)
        with pytest.raises(PermissionDenied):
            self.service.update_client(client_id=client.id, data={"name": "新名称"}, user=user)  # type: ignore[attr-defined]

    def test_update_client_invalid_name(self) -> None:
        """测试更新客户名称为空"""
        client = ClientFactory()
        user = _make_user()
        with pytest.raises(ValidationException) as exc_info:
            self.service.update_client(client_id=client.id, data={"name": ""}, user=user)  # type: ignore[attr-defined]
        assert exc_info.value.code == "INVALID_NAME"

    def test_delete_client_success(self) -> None:
        """测试删除客户成功"""
        client = ClientFactory()
        client_id = client.id  # type: ignore[attr-defined]
        user = _make_user()
        self.service.delete_client(client_id=client_id, user=user)
        assert not Client.objects.filter(id=client_id).exists()

    def test_delete_client_not_found(self) -> None:
        """测试删除不存在的客户"""
        user = _make_user()
        with pytest.raises(NotFoundError):
            self.service.delete_client(client_id=99999, user=user)

    def test_delete_client_permission_denied(self) -> None:
        """测试删除客户权限不足"""
        client = ClientFactory()
        user = _make_user(has_perm=False)
        with pytest.raises(PermissionDenied):
            self.service.delete_client(client_id=client.id, user=user)  # type: ignore[attr-defined]
