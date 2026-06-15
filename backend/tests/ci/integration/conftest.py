"""Shared fixtures and helpers for integration tests."""

from __future__ import annotations

import json
from typing import Any

import pytest


@pytest.fixture
def json_post(authenticated_client):
    """Helper to POST JSON data without boilerplate."""

    def _post(url: str, data: dict[str, Any], **kwargs: Any):
        return authenticated_client.post(
            url,
            data=json.dumps(data),
            content_type="application/json",
            **kwargs,
        )

    return _post


@pytest.fixture
def json_put(authenticated_client):
    """Helper to PUT JSON data without boilerplate."""

    def _put(url: str, data: dict[str, Any], **kwargs: Any):
        return authenticated_client.put(
            url,
            data=json.dumps(data),
            content_type="application/json",
            **kwargs,
        )

    return _put


@pytest.fixture
def api_client_unauth(api_client):
    """Alias for unauthenticated client for clarity."""
    return api_client
