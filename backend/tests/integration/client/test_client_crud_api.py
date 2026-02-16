"""
客户 CRUD API 集成测试

通过直接调用 API 函数测试完整的 CRUD 流程。
使用 factories 创建测试数据。

Requirements: 5.4
"""
from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest

from apps.client.api.client_api import (
    create_client,
    delete_client,
    get_client,
    list_clients,
    update_client,
)
from apps.client.models import Client
from apps.client.schemas import ClientIn, ClientUpdateIn
from apps.core.exceptions import NotFoundError, ValidationException
from tests.factories.client_factories import ClientFactory, LegalClientFactory
from tests.factories.organization_factories import LawyerFactory


def _make_request(
    user: Any = None,
    *,
    perm_open_access: bool = True,
    org_access: Any = None,
) -> Mock:
    """构造模拟 request 对象。"""
    request = Mock()
    request.user = user
    request.auth = user
    request.perm_open_access = perm_open_access
    request.org_access = org_access
    return request


@pytest.mark.django_db
@pytest.mark.integration
class TestClientCreateAPI:
    """客户创建 API 测试"""

    def test_create_natural_client(self) -> None:
        """创建自然人客户"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        payload = ClientIn(
            name="张三",
            client_type=Client.NATURAL,
            phone="13800138000",
            is_our_client=True,
        )
        result = create_client(request, payload)

        assert result.id is not None
        assert result.name == "张三"
        assert result.client_type == Client.NATURAL
        assert result.phone == "13800138000"

    def test_create_legal_client(self) -> None:
        """创建法人客户"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        payload = ClientIn(
            name="测试公司",
            client_type=Client.LEGAL,
            legal_representative="李四",
            id_number="91110000123456789A",
            is_our_client=False,
        )
        result = create_client(request, payload)

        assert result.name == "测试公司"
        assert result.client_type == Client.LEGAL

    def test_create_client_empty_name_rejected(self) -> None:
        """空名称创建客户被拒绝"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        payload = ClientIn(
            name="",
            client_type=Client.NATURAL,
        )
        with pytest.raises(ValidationException):
            create_client(request, payload)


@pytest.mark.django_db
@pytest.mark.integration
class TestClientListAPI:
    """客户列表查询 API 测试"""

    def test_list_clients_empty(self) -> None:
        """空列表查询"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = list_clients(request)
        assert len(result) == 0

    def test_list_clients_returns_all(self) -> None:
        """查询所有客户"""
        ClientFactory.create_batch(3)
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = list_clients(request)
        assert len(result) == 3

    def test_list_clients_filter_by_type(self) -> None:
        """按客户类型过滤"""
        ClientFactory.create_batch(2, client_type=Client.NATURAL)
        LegalClientFactory()
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = list_clients(request, client_type=Client.NATURAL)
        assert len(result) == 2

    def test_list_clients_filter_is_our_client(self) -> None:
        """按是否我方当事人过滤"""
        ClientFactory.create_batch(2, is_our_client=True)
        ClientFactory(is_our_client=False)
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = list_clients(request, is_our_client=True)
        assert len(result) == 2

    def test_list_clients_search(self) -> None:
        """按关键词搜索"""
        ClientFactory(name="张三测试")
        ClientFactory(name="李四测试")
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = list_clients(request, search="张三")
        assert len(result) == 1


@pytest.mark.django_db
@pytest.mark.integration
class TestClientGetAPI:
    """客户详情查询 API 测试"""

    def test_get_client_success(self) -> None:
        """获取客户详情"""
        client = ClientFactory(name="详情测试客户")
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = get_client(request, client.id)

        assert result.id == client.id
        assert result.name == "详情测试客户"

    def test_get_client_not_found(self) -> None:
        """获取不存在的客户"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        with pytest.raises(NotFoundError):
            get_client(request, 999999)


@pytest.mark.django_db
@pytest.mark.integration
class TestClientUpdateAPI:
    """客户更新 API 测试"""

    def test_update_client_name(self) -> None:
        """更新客户名称"""
        client = ClientFactory(name="旧名称")
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        payload = ClientUpdateIn(name="新名称")
        result = update_client(request, client.id, payload)

        assert result.name == "新名称"
        client.refresh_from_db()
        assert client.name == "新名称"

    def test_update_client_partial(self) -> None:
        """部分更新（只更新指定字段）"""
        client = ClientFactory(name="原名称", phone="13800000000")
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        payload = ClientUpdateIn(phone="13900000000")
        result = update_client(request, client.id, payload)

        assert result.name == "原名称"
        assert result.phone == "13900000000"

    def test_update_client_not_found(self) -> None:
        """更新不存在的客户"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        payload = ClientUpdateIn(name="新名称")
        with pytest.raises(NotFoundError):
            update_client(request, 999999, payload)


@pytest.mark.django_db
@pytest.mark.integration
class TestClientDeleteAPI:
    """客户删除 API 测试"""

    def test_delete_client_success(self) -> None:
        """删除客户"""
        client = ClientFactory()
        client_id = client.id
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        status_code, _ = delete_client(request, client_id)

        assert status_code == 204
        assert not Client.objects.filter(id=client_id).exists()

    def test_delete_client_not_found(self) -> None:
        """删除不存在的客户"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        with pytest.raises(NotFoundError):
            delete_client(request, 999999)
