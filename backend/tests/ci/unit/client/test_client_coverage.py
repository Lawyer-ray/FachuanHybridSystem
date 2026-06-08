"""Coverage tests for apps/client 0% files.

Covers:
- apps/client/services/client_dto_assembler.py
- apps/client/services/client_query_builder.py
- apps/client/services/query/client_get_query_service.py
- apps/client/services/query/client_batch_query_service.py
- apps/client/services/query/client_list_query_service.py
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError


# ── client_dto_assembler.py ─────────────────────────────────────────────────


class TestClientDtoAssembler:
    """ClientDtoAssembler.to_dto() 测试。"""

    def test_to_dto_basic(self) -> None:
        from apps.client.services.client_dto_assembler import ClientDtoAssembler

        assembler = ClientDtoAssembler()
        client = SimpleNamespace(
            id=1,
            name="张三",
            client_type="natural",
            phone="12000000000",
            id_number="000000000000000000",
            address="北京市朝阳区",
            is_our_client=True,
        )
        dto = assembler.to_dto(client)
        assert dto.id == 1
        assert dto.name == "张三"
        assert dto.client_type == "natural"
        assert dto.phone == "12000000000"
        assert dto.id_number == "000000000000000000"
        assert dto.address == "北京市朝阳区"
        assert dto.is_our_client is True

    def test_to_dto_minimal_fields(self) -> None:
        from apps.client.services.client_dto_assembler import ClientDtoAssembler

        assembler = ClientDtoAssembler()
        client = SimpleNamespace(
            id=2,
            name="乙公司",
            client_type="legal",
            phone=None,
            id_number=None,
            address=None,
            is_our_client=False,
        )
        dto = assembler.to_dto(client)
        assert dto.id == 2
        assert dto.name == "乙公司"
        assert dto.client_type == "legal"
        assert dto.phone is None
        assert dto.is_our_client is False


class TestClientRelatedDtoAssembler:
    """ClientRelatedDtoAssembler 测试。"""

    def test_property_clue_to_dto(self) -> None:
        from apps.client.services.client_dto_assembler import ClientRelatedDtoAssembler

        assembler = ClientRelatedDtoAssembler()
        clue = SimpleNamespace(pk=10, client_id=1, clue_type="vehicle", content="车牌号京A12345")
        dto = assembler.property_clue_to_dto(clue)
        assert dto.id == 10
        assert dto.client_id == 1
        assert dto.clue_type == "vehicle"
        assert dto.content == "车牌号京A12345"
        assert dto.description is None

    def test_property_clues_to_dtos_list(self) -> None:
        from apps.client.services.client_dto_assembler import ClientRelatedDtoAssembler

        assembler = ClientRelatedDtoAssembler()
        clues = [
            SimpleNamespace(pk=1, client_id=1, clue_type="vehicle", content="c1"),
            SimpleNamespace(pk=2, client_id=1, clue_type="property", content="c2"),
        ]
        dtos = assembler.property_clues_to_dtos(clues)
        assert len(dtos) == 2
        assert dtos[0].clue_type == "vehicle"
        assert dtos[1].clue_type == "property"

    def test_property_clues_to_dtos_empty(self) -> None:
        from apps.client.services.client_dto_assembler import ClientRelatedDtoAssembler

        assembler = ClientRelatedDtoAssembler()
        assert assembler.property_clues_to_dtos([]) == []

    def test_identity_doc_to_dto(self) -> None:
        from apps.client.services.client_dto_assembler import ClientRelatedDtoAssembler

        assembler = ClientRelatedDtoAssembler()
        doc = SimpleNamespace(
            pk=5,
            client_id=1,
            doc_type="id_card",
            get_doc_type_display=lambda: "身份证",
            media_url="/media/docs/id.pdf",
            expiry_date=None,
        )
        dto = assembler.identity_doc_to_dto(doc)
        assert dto.id == 5
        assert dto.doc_type == "id_card"
        assert dto.doc_type_display == "身份证"
        assert dto.file_path == "/media/docs/id.pdf"
        assert dto.expiry_date is None
        assert dto.is_valid is True

    def test_identity_doc_to_dto_with_expiry(self) -> None:
        from apps.client.services.client_dto_assembler import ClientRelatedDtoAssembler

        assembler = ClientRelatedDtoAssembler()
        doc = SimpleNamespace(
            pk=6,
            client_id=1,
            doc_type="passport",
            get_doc_type_display=lambda: "护照",
            media_url="/media/docs/pass.pdf",
            expiry_date="2030-01-01",
        )
        dto = assembler.identity_doc_to_dto(doc)
        assert dto.expiry_date == "2030-01-01"

    def test_identity_docs_to_dtos_list(self) -> None:
        from apps.client.services.client_dto_assembler import ClientRelatedDtoAssembler

        assembler = ClientRelatedDtoAssembler()
        docs = [
            SimpleNamespace(pk=1, client_id=1, doc_type="id_card", get_doc_type_display=lambda: "身份证", media_url="/a", expiry_date=None),
            SimpleNamespace(pk=2, client_id=1, doc_type="passport", get_doc_type_display=lambda: "护照", media_url="/b", expiry_date="2030-01-01"),
        ]
        dtos = assembler.identity_docs_to_dtos(docs)
        assert len(dtos) == 2
        assert dtos[0].doc_type == "id_card"
        assert dtos[1].doc_type == "passport"


# ── client_query_builder.py ────────────────────────────────────────────────


class TestClientQueryBuilder:
    """ClientQueryBuilder.build_queryset() 测试。"""

    @patch("apps.client.services.client_query_builder.Client")
    def test_build_queryset_no_filters(self, mock_client) -> None:
        from apps.client.services.client_query_builder import ClientQueryBuilder

        builder = ClientQueryBuilder()
        mock_qs = MagicMock()
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.order_by.return_value = mock_qs
        mock_client.objects = mock_qs

        result = builder.build_queryset()
        mock_qs.prefetch_related.assert_called_once_with("identity_docs")
        mock_qs.order_by.assert_called_once_with("-id")

    @patch("apps.client.services.client_query_builder.Client")
    def test_build_queryset_with_client_type(self, mock_client) -> None:
        from apps.client.services.client_query_builder import ClientQueryBuilder

        builder = ClientQueryBuilder()
        mock_qs = MagicMock()
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.order_by.return_value = mock_qs
        mock_client.objects = mock_qs

        builder.build_queryset(client_type="natural")
        mock_qs.filter.assert_called_with(client_type="natural")

    @patch("apps.client.services.client_query_builder.Client")
    def test_build_queryset_with_is_our_client(self, mock_client) -> None:
        from apps.client.services.client_query_builder import ClientQueryBuilder

        builder = ClientQueryBuilder()
        mock_qs = MagicMock()
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.order_by.return_value = mock_qs
        mock_client.objects = mock_qs

        builder.build_queryset(is_our_client=True)
        mock_qs.filter.assert_called_with(is_our_client=True)

    @patch("apps.client.services.client_query_builder.Client")
    def test_build_queryset_with_search(self, mock_client) -> None:
        from apps.client.services.client_query_builder import ClientQueryBuilder

        builder = ClientQueryBuilder()
        mock_qs = MagicMock()
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.order_by.return_value = mock_qs
        mock_client.objects = mock_qs

        builder.build_queryset(search="张三")
        mock_qs.filter.assert_called()
        # 验证 Q 对象被使用
        call_args = mock_qs.filter.call_args
        assert call_args is not None

    @patch("apps.client.services.client_query_builder.Client")
    def test_build_queryset_all_filters(self, mock_client) -> None:
        from apps.client.services.client_query_builder import ClientQueryBuilder

        builder = ClientQueryBuilder()
        mock_qs = MagicMock()
        mock_qs.prefetch_related.return_value = mock_qs
        mock_qs.order_by.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_client.objects = mock_qs

        builder.build_queryset(client_type="legal", is_our_client=False, search="test")
        assert mock_qs.filter.call_count == 3


# ── client_get_query_service.py ────────────────────────────────────────────


class TestClientGetQueryService:
    """ClientGetQueryService 测试。"""

    def test_get_client_found(self) -> None:
        from apps.client.services.query.client_get_query_service import ClientGetQueryService

        mock_internal = MagicMock()
        mock_internal.get_client.return_value = SimpleNamespace(id=1, name="张三")
        svc = ClientGetQueryService(internal_query_service=mock_internal)
        result = svc.get_client(client_id=1)
        assert result.name == "张三"

    def test_get_client_not_found_raises(self) -> None:
        from apps.client.services.query.client_get_query_service import ClientGetQueryService

        mock_internal = MagicMock()
        mock_internal.get_client.return_value = None
        svc = ClientGetQueryService(internal_query_service=mock_internal)
        with pytest.raises(NotFoundError) as exc_info:
            svc.get_client(client_id=999)
        assert exc_info.value.code == "CLIENT_NOT_FOUND"

    def test_lazy_internal_service(self) -> None:
        from apps.client.services.query.client_get_query_service import ClientGetQueryService

        svc = ClientGetQueryService()
        assert svc._internal_query_service is None


# ── client_batch_query_service.py ──────────────────────────────────────────


class TestClientBatchQueryService:
    """ClientBatchQueryService 测试。"""

    def test_get_clients_by_ids_delegates(self) -> None:
        from apps.client.services.query.client_batch_query_service import ClientBatchQueryService

        mock_internal = MagicMock()
        mock_internal.get_clients_by_ids.return_value = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
        svc = ClientBatchQueryService(internal_query_service=mock_internal)
        result = svc.get_clients_by_ids(client_ids=[1, 2])
        assert len(result) == 2
        mock_internal.get_clients_by_ids.assert_called_once_with(client_ids=[1, 2])

    def test_get_clients_by_ids_empty(self) -> None:
        from apps.client.services.query.client_batch_query_service import ClientBatchQueryService

        mock_internal = MagicMock()
        mock_internal.get_clients_by_ids.return_value = []
        svc = ClientBatchQueryService(internal_query_service=mock_internal)
        result = svc.get_clients_by_ids(client_ids=[])
        assert result == []

    def test_lazy_internal_service(self) -> None:
        from apps.client.services.query.client_batch_query_service import ClientBatchQueryService

        svc = ClientBatchQueryService()
        assert svc._internal_query_service is None


# ── client_list_query_service.py ────────────────────────────────────────────


class TestClientListQueryService:
    """ClientListQueryService 测试。"""

    def test_list_clients_delegates_to_builder(self) -> None:
        from apps.client.services.query.client_list_query_service import ClientListQueryService

        mock_builder = MagicMock()
        mock_builder.build_queryset.return_value = "qs"
        svc = ClientListQueryService(query_builder=mock_builder)
        result = svc.list_clients(client_type="natural", is_our_client=True, search="test")
        assert result == "qs"
        mock_builder.build_queryset.assert_called_once_with(
            client_type="natural", is_our_client=True, search="test"
        )

    def test_list_clients_no_filters(self) -> None:
        from apps.client.services.query.client_list_query_service import ClientListQueryService

        mock_builder = MagicMock()
        mock_builder.build_queryset.return_value = "qs"
        svc = ClientListQueryService(query_builder=mock_builder)
        result = svc.list_clients()
        assert result == "qs"
        mock_builder.build_queryset.assert_called_once_with(
            client_type=None, is_our_client=None, search=None
        )
