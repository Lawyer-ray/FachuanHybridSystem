from unittest.mock import Mock, patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client


@pytest.fixture
def api_client():
    return Client()


@pytest.mark.django_db
def test_contract_download_denied_without_access(api_client):
    user = get_user_model().objects.create_user(username="u_gen_1", password="p1")
    api_client.force_login(user)

    from apps.core.exceptions import PermissionDenied

    with patch(  # noqa: SIM117
        "apps.contracts.services.contract.contract_service_adapter.ContractServiceAdapter.ensure_contract_access_ctx_internal",
        side_effect=PermissionDenied(message="无权限访问该合同", code="PERMISSION_DENIED"),
    ):
        with patch("apps.documents.api.generation_api._get_contract_generation_service") as get_service:
            get_service.return_value = Mock()
            resp = api_client.get("/api/v1/documents/contracts/1/download", HTTP_HOST="localhost")
            assert resp.status_code == 403
            get_service.assert_not_called()


@pytest.mark.django_db
def test_contract_folder_download_denied_without_access(api_client):
    user = get_user_model().objects.create_user(username="u_gen_2", password="p2")
    api_client.force_login(user)

    from apps.core.exceptions import PermissionDenied

    with patch(  # noqa: SIM117
        "apps.contracts.services.contract.contract_service_adapter.ContractServiceAdapter.ensure_contract_access_ctx_internal",
        side_effect=PermissionDenied(message="无权限访问该合同", code="PERMISSION_DENIED"),
    ):
        with patch("apps.documents.api.generation_api._get_folder_generation_service") as get_service:
            get_service.return_value = Mock()
            resp = api_client.get("/api/v1/documents/contracts/1/folder/download", HTTP_HOST="localhost")
            assert resp.status_code == 403
            get_service.assert_not_called()


@pytest.mark.django_db
def test_supplementary_download_denied_without_access(api_client):
    user = get_user_model().objects.create_user(username="u_gen_3", password="p3")
    api_client.force_login(user)

    from apps.core.exceptions import PermissionDenied

    with patch(  # noqa: SIM117
        "apps.contracts.services.contract.contract_service_adapter.ContractServiceAdapter.ensure_contract_access_ctx_internal",
        side_effect=PermissionDenied(message="无权限访问该合同", code="PERMISSION_DENIED"),
    ):
        with patch("apps.documents.api.generation_api._get_supplementary_agreement_service") as get_service:
            get_service.return_value = Mock()
            resp = api_client.get(
                "/api/v1/documents/contracts/1/supplementary-agreements/2/download", HTTP_HOST="localhost"
            )
            assert resp.status_code == 403
            get_service.assert_not_called()
