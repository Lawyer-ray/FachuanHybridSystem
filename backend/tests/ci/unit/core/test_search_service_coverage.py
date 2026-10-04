"""Coverage tests for core.services.search_service."""

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from apps.core.services.search_service import SearchResultItem


class TestSearchResultItem:
    def test_basic(self):
        item = SearchResultItem(id=1, title="test", subtitle="sub")
        assert item.id == 1
        assert item.title == "test"
        assert item.subtitle == "sub"

    def test_default_subtitle(self):
        item = SearchResultItem(id=1, title="test")
        assert item.subtitle == ""


class TestSearchFunctions:
    @patch("apps.client.models.Client")
    def test_search_clients(self, MockClient):
        from apps.core.services.search_service import search_clients

        mock_obj = MagicMock()
        mock_obj.id = 1
        mock_obj.name = "Alice"
        mock_obj.phone = "123"
        mock_qs = MagicMock()
        mock_qs.distinct.return_value.__getitem__ = MagicMock(return_value=[mock_obj])
        mock_qs.distinct.return_value.__iter__ = MagicMock(return_value=iter([mock_obj]))
        MockClient.objects.filter.return_value = mock_qs
        MockClient.objects.filter.return_value.distinct.return_value = [mock_obj]
        # 管理员（has_perm 恒真）走完整查询路径
        admin = MagicMock(is_authenticated=True, is_admin=True)
        result = search_clients("Alice", 10, user=admin)
        assert isinstance(result, list)

    @patch("apps.contracts.models.Contract")
    def test_search_contracts(self, MockContract):
        from apps.core.services.search_service import search_contracts

        mock_obj = MagicMock()
        mock_obj.id = 1
        mock_obj.name = "Contract1"
        mock_qs = MagicMock()
        mock_qs.distinct.return_value.__getitem__ = MagicMock(return_value=[mock_obj])
        mock_qs.distinct.return_value.__iter__ = MagicMock(return_value=iter([mock_obj]))
        MockContract.objects.filter.return_value = mock_qs
        MockContract.objects.filter.return_value.distinct.return_value = [mock_obj]
        # 管理员跳过行级过滤（filter_queryset 原样放行）
        admin = MagicMock(is_authenticated=True, is_admin=True)
        result = search_contracts("Contract", 10, user=admin)
        assert isinstance(result, list)

    def test_search_denied_without_user(self):
        """未提供 user（未认证）时各分支返回空，不触碰查询。"""
        from apps.core.services.search_service import search_contacts, search_contracts

        assert search_contracts("x", 10, user=None) == []
        assert search_contacts("x", 10, user=None) == []
