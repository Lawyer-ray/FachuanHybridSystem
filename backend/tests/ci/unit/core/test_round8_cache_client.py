"""Tests for client services and other pure-logic modules."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.client.services.client_service_adapter import ClientServiceAdapter

# ---------------------------------------------------------------------------
# ClientServiceAdapter
# ---------------------------------------------------------------------------


class TestClientServiceAdapter:
    def test_lazy_properties(self):
        adapter = ClientServiceAdapter()
        # Access properties to trigger lazy init
        assert adapter.dto_assembler is not None
        assert adapter.internal_query_service is not None
        assert adapter.related_dto_assembler is not None

    def test_get_client_none(self):
        mock_query = MagicMock()
        mock_query.get_client.return_value = None
        adapter = ClientServiceAdapter(internal_query_service=mock_query)
        result = adapter.get_client(1)
        assert result is None

    def test_get_client_internal(self):
        mock_query = MagicMock()
        mock_query.get_client.return_value = None
        adapter = ClientServiceAdapter(internal_query_service=mock_query)
        result = adapter.get_client_internal(1)
        assert result is None

    def test_validate_client_exists_false(self):
        mock_query = MagicMock()
        mock_query.get_client.return_value = None
        adapter = ClientServiceAdapter(internal_query_service=mock_query)
        assert adapter.validate_client_exists(1) is False

    def test_validate_client_exists_true(self):
        mock_query = MagicMock()
        mock_query.get_client.return_value = MagicMock()
        mock_dto_assembler = MagicMock()
        mock_dto_assembler.to_dto.return_value = MagicMock()
        adapter = ClientServiceAdapter(
            internal_query_service=mock_query,
            dto_assembler=mock_dto_assembler,
        )
        assert adapter.validate_client_exists(1) is True

    def test_get_clients_by_ids_empty(self):
        mock_query = MagicMock()
        mock_query.get_clients_by_ids.return_value = []
        adapter = ClientServiceAdapter(internal_query_service=mock_query)
        result = adapter.get_clients_by_ids([])
        assert result == []

    def test_get_client_by_name_none(self):
        mock_query = MagicMock()
        mock_query.get_client_by_name.return_value = None
        adapter = ClientServiceAdapter(internal_query_service=mock_query)
        result = adapter.get_client_by_name("not found")
        assert result is None

    def test_get_all_clients_internal_empty(self):
        mock_query = MagicMock()
        mock_query.list_all_clients.return_value = []
        adapter = ClientServiceAdapter(internal_query_service=mock_query)
        result = adapter.get_all_clients_internal()
        assert result == []

    def test_search_clients_empty(self):
        mock_query = MagicMock()
        mock_query.search_clients_by_name.return_value = []
        adapter = ClientServiceAdapter(internal_query_service=mock_query)
        result = adapter.search_clients_by_name_internal("name")
        assert result == []

    def test_is_natural_person(self):
        mock_query = MagicMock()
        mock_query.is_natural_person.return_value = True
        adapter = ClientServiceAdapter(internal_query_service=mock_query)
        assert adapter.is_natural_person_internal(1) is True

    def test_get_property_clues_empty(self):
        mock_query = MagicMock()
        mock_query.list_property_clues_by_client.return_value = []
        mock_related = MagicMock()
        mock_related.property_clues_to_dtos.return_value = []
        adapter = ClientServiceAdapter(
            internal_query_service=mock_query,
            related_dto_assembler=mock_related,
        )
        result = adapter.get_property_clues_by_client_internal(1)
        assert result == []

    def test_get_identity_docs_empty(self):
        mock_query = MagicMock()
        mock_query.list_identity_docs_by_client.return_value = []
        mock_related = MagicMock()
        mock_related.identity_docs_to_dtos.return_value = []
        adapter = ClientServiceAdapter(
            internal_query_service=mock_query,
            related_dto_assembler=mock_related,
        )
        result = adapter.get_identity_docs_by_client_internal(1)
        assert result == []
