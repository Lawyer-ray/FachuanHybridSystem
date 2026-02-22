"""
客户 API 集成测试
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client as HttpClient

from apps.client.models import Client
from apps.organization.models import LawFirm
from tests.factories.client_factories import ClientFactory

User = get_user_model()


@pytest.mark.django_db
class TestClientAPI:
    """客户 API 测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.http_client = HttpClient()

        # 创建测试用户
        self.firm = LawFirm.objects.create(name="测试律所")
        self.admin = User.objects.create_user(
            username="testadmin",
            password="testpass123",
            is_admin=True,
            law_firm=self.firm,
        )

        # 登录
        self.http_client.force_login(self.admin)

    def test_list_clients_success(self):
        """测试获取客户列表成功"""
        # 准备测试数据
        ClientFactory.create_batch(5)

        # 执行请求
        response = self.http_client.get("/api/v1/client/clients")

        # 断言结果
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5

    def test_list_clients_with_filters(self):
        """测试带过滤条件的客户列表"""
        # 准备测试数据
        ClientFactory(client_type=Client.NATURAL, is_our_client=True)
        ClientFactory(client_type=Client.LEGAL, is_our_client=False)

        # 测试按类型过滤
        response = self.http_client.get(f"/api/v1/client/clients?client_type={Client.NATURAL}")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["client_type"] == Client.NATURAL

    def test_list_clients_pagination(self):
        """测试分页"""
        # 准备测试数据
        ClientFactory.create_batch(25)

        # 测试第一页
        response = self.http_client.get("/api/v1/client/clients?page=1&page_size=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 10

    def test_get_client_success(self):
        """测试获取单个客户成功"""
        # 准备测试数据
        client = ClientFactory()

        # 执行请求
        response = self.http_client.get(f"/api/v1/client/clients/{client.id}")  # type: ignore[attr-defined]

        # 断言结果
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == client.id  # type: ignore[attr-defined]
        assert data["name"] == client.name

    def test_get_client_not_found(self):
        """测试获取不存在的客户"""
        # 执行请求
        response = self.http_client.get("/api/v1/client/clients/99999")

        # 断言结果
        assert response.status_code == 404

    def test_create_client_success(self):
        """测试创建客户成功"""
        # 准备测试数据
        data = {
            "name": "新建客户",
            "client_type": Client.NATURAL,
            "phone": "13800138000",
            "address": "测试地址",
            "id_number": "110101199001011234",
            "is_our_client": True,
        }

        # 执行请求
        response = self.http_client.post("/api/v1/client/clients", data=data, content_type="application/json")

        # 断言结果
        assert response.status_code == 200
        result = response.json()
        assert result["name"] == "新建客户"
        assert result["phone"] == "13800138000"

        # 验证数据库
        assert Client.objects.filter(name="新建客户").exists()

    def test_create_client_invalid_data(self):
        """测试创建客户数据无效"""
        # 准备测试数据（名称为空）
        data = {
            "name": "",
            "client_type": Client.NATURAL,
        }

        # 执行请求
        response = self.http_client.post("/api/v1/client/clients", data=data, content_type="application/json")

        # 断言结果
        assert response.status_code == 400

    def test_update_client_success(self):
        """测试更新客户成功"""
        # 准备测试数据
        client = ClientFactory(name="旧名称")

        data = {"name": "新名称"}

        # 执行请求
        response = self.http_client.put(
            f"api/v1/client/clients/{client.id}",  # type: ignore[attr-defined]
            data=data,
            content_type="application/json",
        )

        # 断言结果
        assert response.status_code == 200
        result = response.json()
        assert result["name"] == "新名称"

        # 验证数据库
        client.refresh_from_db()  # type: ignore[attr-defined]
        assert client.name == "新名称"

    def test_update_client_not_found(self):
        """测试更新不存在的客户"""
        # 准备测试数据
        data = {"name": "新名称"}

        # 执行请求
        response = self.http_client.put("/api/v1/client/clients/99999", data=data, content_type="application/json")

        # 断言结果
        assert response.status_code == 404

    def test_delete_client_success(self):
        """测试删除客户成功"""
        # 准备测试数据
        client = ClientFactory()
        client_id = client.id  # type: ignore[attr-defined]

        # 执行请求
        response = self.http_client.delete(f"/api/v1/client/clients/{client_id}")

        # 断言结果
        assert response.status_code == 204

        # 验证数据库
        assert not Client.objects.filter(id=client_id).exists()

    def test_delete_client_not_found(self):
        """测试删除不存在的客户"""
        # 执行请求
        response = self.http_client.delete("/api/v1/client/clients/99999")

        # 断言结果
        assert response.status_code == 404

    def test_unauthorized_access(self):
        """测试未认证访问"""
        # 登出
        self.http_client.logout()

        # 执行请求
        response = self.http_client.get("/api/v1/client/clients")

        # 断言结果
        assert response.status_code == 401
