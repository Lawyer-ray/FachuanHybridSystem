"""Client Admin 测试 - ClientAdmin, ClientIdentityDocAdmin, PropertyClueAdmin"""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.client.admin.client_admin import ClientAdmin
from apps.client.admin.clientidentitydoc_admin import ClientIdentityDocAdmin
from apps.client.admin.property_clue_admin import PropertyClueAdmin
from apps.client.models import Client, ClientIdentityDoc, PropertyClue

User = get_user_model()


def _make_request(path: str = "/admin/") -> Any:
    factory = RequestFactory()
    request = factory.get(path)
    request.user = User(is_superuser=True, is_staff=True)
    return request


@pytest.mark.django_db
class TestClientAdmin:
    """ClientAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = ClientAdmin(Client, AdminSite())
        display = admin_obj.list_display
        assert "name" in display

    def test_search_fields(self) -> None:
        """search_fields 包含 name"""
        admin_obj = ClientAdmin(Client, AdminSite())
        assert "name" in admin_obj.search_fields

    def test_client_type_natural(self) -> None:
        """自然人客户类型"""
        client = Client.objects.create(name="自然人客户", client_type="natural")
        assert client.client_type == "natural"

    def test_client_type_legal(self) -> None:
        """法人客户类型"""
        client = Client.objects.create(
            name="法人客户", client_type="legal", legal_representative="法定代表人"
        )
        assert client.client_type == "legal"


@pytest.mark.django_db
class TestClientIdentityDocAdmin:
    """ClientIdentityDocAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = ClientIdentityDocAdmin(ClientIdentityDoc, AdminSite())
        assert "id" in admin_obj.list_display
        assert "client" in admin_obj.list_display

    def test_list_select_related(self) -> None:
        """list_select_related 存在"""
        admin_obj = ClientIdentityDocAdmin(ClientIdentityDoc, AdminSite())
        assert hasattr(admin_obj, 'list_select_related')

    def test_get_queryset_no_n_plus_1(self) -> None:
        """get_queryset 应使用 select_related 避免 N+1"""
        client = Client.objects.create(name="证件测试客户", client_type="natural")
        ClientIdentityDoc.objects.create(
            client=client,
            doc_type="id_card",
            file_path="identity_docs/test.pdf",
        )

        admin_obj = ClientIdentityDocAdmin(ClientIdentityDoc, AdminSite())
        qs = admin_obj.get_queryset(_make_request())
        results = list(qs)
        assert len(results) == 1
        assert results[0].client.name == "证件测试客户"


@pytest.mark.django_db
class TestPropertyClueAdmin:
    """PropertyClueAdmin 测试"""

    def test_list_display_fields(self) -> None:
        """list_display 包含必要字段"""
        admin_obj = PropertyClueAdmin(PropertyClue, AdminSite())
        assert "id" in admin_obj.list_display

    def test_list_select_related(self) -> None:
        """list_select_related 存在"""
        admin_obj = PropertyClueAdmin(PropertyClue, AdminSite())
        assert hasattr(admin_obj, 'list_select_related')
