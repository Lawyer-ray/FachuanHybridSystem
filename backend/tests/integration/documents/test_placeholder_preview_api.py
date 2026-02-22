from datetime import datetime
from unittest.mock import patch

import pytest
from django.test import Client


@pytest.fixture
def api_client():
    return Client()


@patch("apps.documents.api.placeholder_api.EnhancedContextBuilder.build_contract_context")
def test_preview_placeholders_all(mock_build_context, api_client):
    mock_build_context.return_value = {"a": 1, "b": datetime(2025, 1, 1, 0, 0, 0)}
    response = api_client.get("/api/v1/documents/placeholders/preview/1")
    assert response.status_code == 200
    data = response.json()
    assert data["contract_id"] == 1
    assert data["values"]["a"] == 1
    assert data["values"]["b"] == "2025-01-01T00:00:00"
    assert data["missing_keys"] == []


@patch("apps.documents.api.placeholder_api.EnhancedContextBuilder.build_contract_context")
def test_preview_placeholders_with_keys_filter(mock_build_context, api_client):
    mock_build_context.return_value = {"a": 1}
    response = api_client.get("/api/v1/documents/placeholders/preview/1", data={"keys": "a, c"})
    assert response.status_code == 200
    data = response.json()
    assert data["values"] == {"a": 1}
    assert data["missing_keys"] == ["c"]
