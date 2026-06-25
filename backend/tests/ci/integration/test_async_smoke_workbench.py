"""Smoke tests for async workbench API.

Validates full CRUD lifecycle for workbench sessions via async views.
"""

from __future__ import annotations

import json

import pytest


@pytest.mark.django_db
class TestWorkbenchAsyncSmoke:
    def test_create_and_list_sessions(self, authenticated_client):
        """Create -> List workbench sessions should work end-to-end."""
        # Create
        create_resp = authenticated_client.post(
            "/api/v1/workbench/sessions",
            data=json.dumps({"title": "烟雾测试会话"}),
            content_type="application/json",
        )
        assert create_resp.status_code in (200, 201), f"Create failed: {create_resp.content}"

        # List
        list_resp = authenticated_client.get("/api/v1/workbench/sessions")
        assert list_resp.status_code == 200, f"List failed: {list_resp.content}"

    def test_create_get_delete_session(self, authenticated_client):
        """Create -> Get -> Delete workbench session lifecycle."""
        # Create
        create_resp = authenticated_client.post(
            "/api/v1/workbench/sessions",
            data=json.dumps({"title": "生命周期测试"}),
            content_type="application/json",
        )
        assert create_resp.status_code in (200, 201)
        data = create_resp.json()
        session_id = data.get("id") or data.get("session_id")
        assert session_id is not None

        # Get
        get_resp = authenticated_client.get(f"/api/v1/workbench/sessions/{session_id}")
        assert get_resp.status_code == 200

        # Delete
        del_resp = authenticated_client.delete(f"/api/v1/workbench/sessions/{session_id}")
        assert del_resp.status_code in (200, 204)
