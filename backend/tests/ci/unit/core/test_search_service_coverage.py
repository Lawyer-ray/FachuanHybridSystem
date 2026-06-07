"""Coverage tests for core.services.search_service."""

from unittest.mock import MagicMock, patch, PropertyMock

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
        result = search_clients("Alice", 10)
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
        result = search_contracts("Contract", 10)
        assert isinstance(result, list)
