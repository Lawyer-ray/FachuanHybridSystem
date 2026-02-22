"""
ClientServiceAdapter Property-Based Tests
测试客户服务适配器的接口实现

Feature: service-layer-decoupling
Property 3: ClientServiceAdapter 客户存在性验证
Property 4: ClientServiceAdapter 名称查询一致性
Validates: Requirements 2.4, 2.5
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.client.models import Client
from apps.client.services import ClientServiceAdapter
from apps.core.interfaces import ClientDTO
from tests.factories import ClientFactory


@pytest.mark.django_db(transaction=True)
class TestClientServiceAdapterExistenceProperties:
    """
    ClientServiceAdapter 客户存在性验证属性测试

    **Feature: service-layer-decoupling, Property 3: ClientServiceAdapter 客户存在性验证**
    **Validates: Requirements 2.4**
    """

    @given(
        client_name=st.text(alphabet=st.characters(whitelist_categories=("L", "N")), min_size=1, max_size=30).filter(
            lambda x: x.strip()
        ),
    )
    @settings(max_examples=100)
    def test_validate_client_exists_consistency_with_get_client(self, client_name):
        """
        Property 3: 客户存在性验证一致性

        **Feature: service-layer-decoupling, Property 3: ClientServiceAdapter 客户存在性验证**
        **Validates: Requirements 2.4**

        属性：对于任意客户 ID，validate_client_exists(id) 返回 True
        当且仅当 get_client(id) 返回非 None 值。
        """
        adapter = ClientServiceAdapter()

        # 使用 Factory 创建客户
        client = ClientFactory(name=client_name)

        # 验证存在的客户
        exists = adapter.validate_client_exists(client.id)  # type: ignore[attr-defined]
        dto = adapter.get_client(client.id)  # type: ignore[attr-defined]

        # Property: exists == True 当且仅当 dto is not None
        assert exists is True
        assert dto is not None
        assert (exists is True) == (dto is not None)

    @given(
        fake_id=st.integers(min_value=900000, max_value=999999),
    )
    @settings(max_examples=100)
    def test_validate_client_exists_false_for_nonexistent(self, fake_id):
        """
        Property 3: 不存在的客户验证返回 False

        **Feature: service-layer-decoupling, Property 3: ClientServiceAdapter 客户存在性验证**
        **Validates: Requirements 2.4**

        属性：对于不存在的客户 ID，validate_client_exists 返回 False，
        且 get_client 返回 None。
        """
        adapter = ClientServiceAdapter()

        # 确保 ID 不存在
        Client.objects.filter(id=fake_id).delete()

        # 验证不存在的客户
        exists = adapter.validate_client_exists(fake_id)
        dto = adapter.get_client(fake_id)

        # Property: exists == False 当且仅当 dto is None
        assert exists is False
        assert dto is None
        assert (exists is False) == (dto is None)


@pytest.mark.django_db(transaction=True)
class TestClientServiceAdapterNameQueryProperties:
    """
    ClientServiceAdapter 名称查询一致性属性测试

    **Feature: service-layer-decoupling, Property 4: ClientServiceAdapter 名称查询一致性**
    **Validates: Requirements 2.5**
    """

    @given(
        client_name=st.text(alphabet=st.characters(whitelist_categories=("L", "N")), min_size=1, max_size=30).filter(
            lambda x: x.strip()
        ),
    )
    @settings(max_examples=100)
    def test_get_client_by_name_returns_matching_name(self, client_name):
        """
        Property 4: 名称查询返回匹配的客户

        **Feature: service-layer-decoupling, Property 4: ClientServiceAdapter 名称查询一致性**
        **Validates: Requirements 2.5**

        属性：如果 get_client_by_name(name) 返回 DTO，
        则该 DTO 的 name 字段应与查询参数匹配。
        """
        adapter = ClientServiceAdapter()

        # 使用 Factory 创建客户
        client = ClientFactory(name=client_name)

        # 按名称查询
        dto = adapter.get_client_by_name(client_name)

        # Property: 如果返回 DTO，则 name 字段匹配
        assert dto is not None
        assert dto.name == client_name

    @given(
        nonexistent_name=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")), min_size=10, max_size=50
        ).filter(lambda x: x.strip()),
    )
    @settings(max_examples=100)
    def test_get_client_by_name_returns_none_for_nonexistent(self, nonexistent_name):
        """
        Property 4: 不存在的名称查询返回 None

        **Feature: service-layer-decoupling, Property 4: ClientServiceAdapter 名称查询一致性**
        **Validates: Requirements 2.5**

        属性：对于不存在的客户名称，get_client_by_name 返回 None。
        """
        adapter = ClientServiceAdapter()

        # 确保名称不存在
        Client.objects.filter(name=nonexistent_name).delete()

        # 按名称查询
        dto = adapter.get_client_by_name(nonexistent_name)

        # Property: 不存在的名称返回 None
        assert dto is None

    @given(
        client_name=st.text(alphabet=st.characters(whitelist_categories=("L", "N")), min_size=1, max_size=30).filter(
            lambda x: x.strip()
        ),
    )
    @settings(max_examples=50)
    def test_get_client_by_name_dto_fields_complete(self, client_name):
        """
        Property: 名称查询返回的 DTO 字段完整

        属性：get_client_by_name 返回的 DTO 应包含所有必要字段。
        """
        adapter = ClientServiceAdapter()

        # 使用 Factory 创建客户
        client = ClientFactory(name=client_name, phone="13800138000")

        # 按名称查询
        dto = adapter.get_client_by_name(client_name)

        # Property: DTO 字段完整
        assert dto is not None
        assert isinstance(dto, ClientDTO)
        assert dto.id == client.id  # type: ignore[attr-defined]
        assert dto.name == client.name
        assert dto.client_type == client.client_type
        assert dto.is_our_client == client.is_our_client


@pytest.mark.django_db(transaction=True)
class TestClientServiceAdapterInstanceMethodProperties:
    """
    ClientServiceAdapter 实例方法属性测试

    验证适配器正确使用实例方法而非类方法
    Requirements: 2.1, 2.2, 2.3
    """

    @given(
        client_name=st.text(alphabet=st.characters(whitelist_categories=("L", "N")), min_size=1, max_size=30).filter(
            lambda x: x.strip()
        ),
    )
    @settings(max_examples=50)
    def test_get_client_uses_instance_method(self, client_name):
        """
        Property: get_client 使用实例方法

        属性：ClientServiceAdapter.get_client 应该正确调用
        ClientService 实例的 get_client 方法。
        """
        adapter = ClientServiceAdapter()

        # 使用 Factory 创建客户
        client = ClientFactory(name=client_name)

        # 调用 get_client
        dto = adapter.get_client(client.id)  # type: ignore[attr-defined]

        # 验证返回正确的 DTO
        assert dto is not None
        assert dto.id == client.id  # type: ignore[attr-defined]
        assert dto.name == client_name

    @given(
        count=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=50)
    def test_get_clients_by_ids_uses_instance_method(self, count):
        """
        Property: get_clients_by_ids 使用实例方法

        属性：ClientServiceAdapter.get_clients_by_ids 应该正确调用
        ClientService 实例的 get_clients_by_ids 方法。
        """
        adapter = ClientServiceAdapter()

        # 使用 Factory 创建多个客户
        clients = [ClientFactory(name=f"测试客户_{i}") for i in range(count)]

        client_ids = [c.id for c in clients]  # type: ignore[attr-defined]

        # 调用 get_clients_by_ids
        dtos = adapter.get_clients_by_ids(client_ids)

        # 验证返回正确数量的 DTO
        assert len(dtos) == count

        # 验证所有 ID 都在返回结果中
        returned_ids = {dto.id for dto in dtos}
        assert returned_ids == set(client_ids)
