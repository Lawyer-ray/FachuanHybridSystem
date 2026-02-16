"""
客户服务单元测试
"""

from unittest.mock import Mock

import pytest
from django.contrib.auth import get_user_model

from apps.client.models import Client
from apps.client.services.client_service import ClientService
from apps.core.exceptions import NotFoundError, PermissionDenied, ValidationException
from tests.factories.client_factories import ClientFactory

User = get_user_model()


@pytest.mark.django_db
class TestClientService:
    """客户服务测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.service = ClientService()

    def test_list_clients_success(self):
        """测试获取客户列表成功"""
        # 准备测试数据
        ClientFactory.create_batch(5)

        # 执行测试
        clients = self.service.list_clients(page=1, page_size=10)

        # 断言结果
        assert len(list(clients)) == 5

    def test_list_clients_with_filters(self):
        """测试带过滤条件的客户列表"""
        # 准备测试数据
        ClientFactory(client_type=Client.NATURAL, is_our_client=True)
        ClientFactory(client_type=Client.LEGAL, is_our_client=False)
        ClientFactory(client_type=Client.NATURAL, is_our_client=True)

        # 测试按类型过滤
        clients = self.service.list_clients(client_type=Client.NATURAL)
        assert len(list(clients)) == 2

        # 测试按我方当事人过滤
        clients = self.service.list_clients(is_our_client=True)
        assert len(list(clients)) == 2

    def test_list_clients_with_search(self):
        """测试搜索客户"""
        # 准备测试数据
        ClientFactory(name="张三")
        ClientFactory(name="李四")
        ClientFactory(name="王五")

        # 执行搜索
        clients = self.service.list_clients(search="张")

        # 断言结果
        assert len(list(clients)) == 1
        assert list(clients)[0].name == "张三"

    def test_list_clients_pagination(self):
        """测试分页"""
        # 准备测试数据
        ClientFactory.create_batch(25)

        # 测试第一页
        clients_page1 = self.service.list_clients(page=1, page_size=10)
        assert len(list(clients_page1)) == 10

        # 测试第二页
        clients_page2 = self.service.list_clients(page=2, page_size=10)
        assert len(list(clients_page2)) == 10

        # 测试第三页
        clients_page3 = self.service.list_clients(page=3, page_size=10)
        assert len(list(clients_page3)) == 5

    def test_get_client_success(self):
        """测试获取客户成功"""
        # 准备测试数据
        client = ClientFactory()

        # 执行测试
        result = self.service.get_client(client.id)

        # 断言结果
        assert result.id == client.id
        assert result.name == client.name

    def test_get_client_not_found(self):
        """测试获取不存在的客户"""
        # 断言抛出异常
        with pytest.raises(NotFoundError) as exc_info:
            self.service.get_client(99999)

        assert "客户不存在" in exc_info.value.message
        assert exc_info.value.code == "CLIENT_NOT_FOUND"

    def test_get_clients_by_ids(self):
        """测试批量获取客户"""
        # 准备测试数据
        client1 = ClientFactory()
        client2 = ClientFactory()
        client3 = ClientFactory()

        # 执行测试
        clients = self.service.get_clients_by_ids([client1.id, client2.id])

        # 断言结果
        assert len(clients) == 2
        client_ids = [c.id for c in clients]
        assert client1.id in client_ids
        assert client2.id in client_ids
        assert client3.id not in client_ids

    def test_create_client_success(self):
        """测试创建客户成功"""
        # 准备测试数据
        user = Mock()
        user.id = 1
        user.is_authenticated = True
        user.is_admin = True
        user.is_superuser = False
        user.has_perm = Mock(return_value=True)

        data = {
            "name": "测试客户",
            "client_type": Client.NATURAL,
            "phone": "13800138000",
            "id_number": "110101199001010001",
            "address": "测试地址",
            "legal_representative": "",
            "is_our_client": True,
        }

        # 执行测试
        client = self.service.create_client(data, user)

        # 断言结果
        assert client.id is not None
        assert client.name == "测试客户"
        assert client.client_type == Client.NATURAL
        assert client.phone == "13800138000"

    def test_create_client_permission_denied(self):
        """测试创建客户权限不足"""
        # 准备测试数据
        user = Mock()
        user.id = 1
        user.is_authenticated = True
        user.is_admin = False
        user.is_superuser = False
        user.has_perm = Mock(return_value=False)

        data = {
            "name": "测试客户",
            "client_type": Client.NATURAL,
        }

        # 断言抛出异常
        with pytest.raises(PermissionDenied) as exc_info:
            self.service.create_client(data, user)

        assert "无权限创建客户" in exc_info.value.message

    def test_create_client_invalid_name(self):
        """测试创建客户名称为空"""
        # 准备测试数据
        user = Mock()
        user.id = 1
        user.is_authenticated = True
        user.is_admin = True

        data = {
            "name": "",
            "client_type": Client.NATURAL,
        }

        # 断言抛出异常
        with pytest.raises(ValidationException) as exc_info:
            self.service.create_client(data, user)

        assert "客户名称不能为空" in exc_info.value.message
        assert exc_info.value.code == "INVALID_NAME"

    def test_create_client_invalid_type(self):
        """测试创建客户类型无效"""
        # 准备测试数据
        user = Mock()
        user.id = 1
        user.is_authenticated = True
        user.is_admin = True

        data = {
            "name": "测试客户",
            "client_type": "invalid_type",
        }

        # 断言抛出异常
        with pytest.raises(ValidationException) as exc_info:
            self.service.create_client(data, user)

        assert "无效的客户类型" in exc_info.value.message
        assert exc_info.value.code == "INVALID_CLIENT_TYPE"

    def test_create_client_legal_without_representative(self):
        """测试创建法人客户但未填写法定代表人"""
        # 准备测试数据
        user = Mock()
        user.id = 1
        user.is_authenticated = True
        user.is_admin = True

        data = {
            "name": "测试公司",
            "client_type": Client.LEGAL,
        }

        # 断言抛出异常
        with pytest.raises(ValidationException) as exc_info:
            self.service.create_client(data, user)

        assert "法人客户必须填写法定代表人" in exc_info.value.message
        assert exc_info.value.code == "MISSING_LEGAL_REPRESENTATIVE"

    def test_update_client_success(self):
        """测试更新客户成功"""
        # 准备测试数据
        client = ClientFactory(name="旧名称")

        user = Mock()
        user.id = 1
        user.is_authenticated = True
        user.is_admin = True
        user.is_superuser = False
        user.has_perm = Mock(return_value=True)

        data = {"name": "新名称"}

        # 执行测试
        result = self.service.update_client(client.id, data, user)

        # 断言结果
        assert result.name == "新名称"

        # 验证数据库
        client.refresh_from_db()
        assert client.name == "新名称"

    def test_update_client_not_found(self):
        """测试更新不存在的客户"""
        # 准备测试数据
        user = Mock()
        user.id = 1
        user.is_authenticated = True
        user.is_admin = True

        # 断言抛出异常
        with pytest.raises(NotFoundError):
            self.service.update_client(99999, {"name": "新名称"}, user)

    def test_update_client_permission_denied(self):
        """测试更新客户权限不足"""
        # 准备测试数据
        client = ClientFactory()

        user = Mock()
        user.id = 1
        user.is_authenticated = True
        user.is_admin = False
        user.is_superuser = False
        user.has_perm = Mock(return_value=False)

        # 断言抛出异常
        with pytest.raises(PermissionDenied) as exc_info:
            self.service.update_client(client.id, {"name": "新名称"}, user)

        assert "无权限更新该客户" in exc_info.value.message

    def test_update_client_invalid_name(self):
        """测试更新客户名称为空"""
        # 准备测试数据
        client = ClientFactory()

        user = Mock()
        user.id = 1
        user.is_authenticated = True
        user.is_admin = True

        # 断言抛出异常
        with pytest.raises(ValidationException) as exc_info:
            self.service.update_client(client.id, {"name": ""}, user)

        assert "客户名称不能为空" in exc_info.value.message

    def test_delete_client_success(self):
        """测试删除客户成功"""
        # 准备测试数据
        client = ClientFactory()
        client_id = client.id

        user = Mock()
        user.id = 1
        user.is_authenticated = True
        user.is_admin = True
        user.is_superuser = False
        user.has_perm = Mock(return_value=True)

        # 执行测试
        self.service.delete_client(client_id, user)

        # 验证客户已删除
        assert not Client.objects.filter(id=client_id).exists()

    def test_delete_client_not_found(self):
        """测试删除不存在的客户"""
        # 准备测试数据
        user = Mock()
        user.id = 1
        user.is_authenticated = True
        user.is_admin = True

        # 断言抛出异常
        with pytest.raises(NotFoundError):
            self.service.delete_client(99999, user)

    def test_delete_client_permission_denied(self):
        """测试删除客户权限不足"""
        # 准备测试数据
        client = ClientFactory()

        user = Mock()
        user.id = 1
        user.is_authenticated = True
        user.is_admin = False
        user.is_superuser = False
        user.has_perm = Mock(return_value=False)

        # 断言抛出异常
        with pytest.raises(PermissionDenied) as exc_info:
            self.service.delete_client(client.id, user)

        assert "无权限删除该客户" in exc_info.value.message
