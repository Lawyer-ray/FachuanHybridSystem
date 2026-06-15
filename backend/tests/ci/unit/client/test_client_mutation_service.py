"""Unit tests for ClientMutationService."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.client.models import Client
from apps.client.services.client_mutation_service import ClientMutationService
from apps.core.exceptions import ForbiddenError, ValidationException


@pytest.fixture
def svc():
    return ClientMutationService()


@pytest.fixture
def mock_access_policy():
    return MagicMock()


@pytest.fixture
def mock_query_service():
    return MagicMock()


# ──────────── _validate_create_data ────────────


class TestValidateCreateData:
    def test_empty_name_raises(self, svc):
        with pytest.raises(ValidationException, match="名称不能为空"):
            svc._validate_create_data({"name": "", "client_type": Client.NATURAL})

    def test_no_name_raises(self, svc):
        with pytest.raises(ValidationException, match="名称不能为空"):
            svc._validate_create_data({"client_type": Client.NATURAL})

    def test_invalid_client_type_raises(self, svc):
        with pytest.raises(ValidationException, match="无效的客户类型"):
            svc._validate_create_data({"name": "张三", "client_type": "INVALID"})

    def test_no_client_type_raises(self, svc):
        with pytest.raises(ValidationException, match="无效的客户类型"):
            svc._validate_create_data({"name": "张三"})

    def test_legal_without_rep_raises(self, svc):
        with pytest.raises(ValidationException, match="法定代表人"):
            svc._validate_create_data({"name": "公司A", "client_type": Client.LEGAL})

    def test_legal_with_rep_passes(self, svc):
        svc._validate_create_data({
            "name": "公司A",
            "client_type": Client.LEGAL,
            "legal_representative": "王五",
        })  # should not raise

    def test_natural_type_passes(self, svc):
        svc._validate_create_data({"name": "李四", "client_type": Client.NATURAL})

    def test_non_legal_org_passes(self, svc):
        svc._validate_create_data({"name": "组织X", "client_type": Client.NON_LEGAL_ORG})


# ──────────── _validate_update_data ────────────


class TestValidateUpdateData:
    def test_empty_name_raises(self, svc):
        client = MagicMock(spec=Client)
        client.name = "原名"
        client.client_type = Client.NATURAL
        client.legal_representative = None
        with pytest.raises(ValidationException, match="名称不能为空"):
            svc._validate_update_data(client, {"name": ""})

    def test_invalid_type_raises(self, svc):
        client = MagicMock(spec=Client)
        client.name = "原名"
        client.client_type = Client.NATURAL
        with pytest.raises(ValidationException, match="无效的客户类型"):
            svc._validate_update_data(client, {"client_type": "BAD"})

    def test_legal_without_rep_raises(self, svc):
        client = MagicMock(spec=Client)
        client.client_type = Client.LEGAL
        client.legal_representative = None
        with pytest.raises(ValidationException, match="法定代表人"):
            svc._validate_update_data(client, {"client_type": Client.LEGAL})

    def test_update_preserves_existing_rep(self, svc):
        client = MagicMock(spec=Client)
        client.client_type = Client.LEGAL
        client.legal_representative = "已有法人"
        # Updating name only, not touching legal_representative
        svc._validate_update_data(client, {"name": "新名称"})  # should not raise


# ──────────── update_client ────────────


class TestUpdateClient:
    @pytest.mark.django_db
    def test_update_with_valid_data(self, db):
        from apps.testing.factories import ClientFactory
        client = ClientFactory(name="原名", client_type=Client.NATURAL)
        mock_policy = MagicMock()
        svc = ClientMutationService(access_policy=mock_policy)
        result = svc.update_client(client_id=client.pk, data={"name": "新名"})
        result.refresh_from_db()
        assert result.name == "新名"

    @pytest.mark.django_db
    def test_non_updatable_field_ignored(self, db):
        from apps.testing.factories import ClientFactory
        client = ClientFactory(name="原始", client_type=Client.NATURAL)
        mock_policy = MagicMock()
        svc = ClientMutationService(access_policy=mock_policy)
        result = svc.update_client(client_id=client.pk, data={"name": "变更", "id_number": "123"})
        result.refresh_from_db()
        assert result.name == "变更"

    @pytest.mark.django_db
    def test_update_legal_type_with_rep(self, db):
        from apps.testing.factories import ClientFactory
        client = ClientFactory(
            client_type=Client.LEGAL, name="公司", legal_representative="旧法人"
        )
        mock_policy = MagicMock()
        svc = ClientMutationService(access_policy=mock_policy)
        result = svc.update_client(
            client_id=client.pk,
            data={"legal_representative": "新法人"},
        )
        result.refresh_from_db()
        assert result.legal_representative == "新法人"


# ──────────── delete_client ────────────


class TestDeleteClient:
    @pytest.mark.django_db
    def test_delete_removes_client(self, db):
        from apps.testing.factories import ClientFactory
        client = ClientFactory(name="待删", client_type=Client.NATURAL)
        mock_workflow = MagicMock()
        mock_workflow.collect_client_file_paths.return_value = []
        mock_policy = MagicMock()
        mock_query = MagicMock()
        # Make query_service.get_client return the actual client
        mock_query.get_client.return_value = client
        svc = ClientMutationService(
            deletion_workflow=mock_workflow,
            access_policy=mock_policy,
            query_service=mock_query,
        )
        svc.delete_client(client_id=client.pk)
        assert not Client.objects.filter(pk=client.pk).exists()


# ──────────── properties ────────────


class TestServiceProperties:
    def test_access_policy_is_created(self):
        svc = ClientMutationService()
        # After first access, _access_policy should be set
        result = svc.access_policy
        assert result is not None
        assert svc._access_policy is result

    def test_query_service_is_created(self):
        svc = ClientMutationService()
        result = svc.query_service
        assert result is not None
        assert svc._query_service is result

    def test_identity_doc_service_is_created(self):
        svc = ClientMutationService()
        result = svc.identity_doc_service
        assert result is not None
        assert svc._identity_doc_service is result

    def test_delegation_workflow_is_created(self):
        svc = ClientMutationService()
        result = svc.deletion_workflow
        assert result is not None
        assert svc._deletion_workflow is result

    def test_injected_services_used_directly(self):
        mock_policy = MagicMock()
        mock_query = MagicMock()
        mock_id_doc = MagicMock()
        mock_workflow = MagicMock()
        svc = ClientMutationService(
            access_policy=mock_policy,
            query_service=mock_query,
            identity_doc_service=mock_id_doc,
            deletion_workflow=mock_workflow,
        )
        assert svc.access_policy is mock_policy
        assert svc.query_service is mock_query
        assert svc.identity_doc_service is mock_id_doc
        assert svc.deletion_workflow is mock_workflow


# ──────────── Constants ────────────


class TestConstants:
    def test_valid_client_types(self):
        assert Client.NATURAL in ClientMutationService._VALID_CLIENT_TYPES
        assert Client.LEGAL in ClientMutationService._VALID_CLIENT_TYPES
        assert Client.NON_LEGAL_ORG in ClientMutationService._VALID_CLIENT_TYPES

    def test_updatable_fields(self):
        assert "name" in ClientMutationService._UPDATABLE_FIELDS
        assert "phone" in ClientMutationService._UPDATABLE_FIELDS
        assert "client_type" in ClientMutationService._UPDATABLE_FIELDS
        assert "is_our_client" in ClientMutationService._UPDATABLE_FIELDS
