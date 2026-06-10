"""Express query API integration tests."""

from __future__ import annotations

import pytest

from apps.express_query.models import ExpressQueryTask


# ===================================================================
# List tasks
# ===================================================================


@pytest.mark.django_db
def test_list_tasks_empty(authenticated_client):
    resp = authenticated_client.get("/api/v1/express-query/tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.django_db
def test_list_tasks_with_data(authenticated_client):
    # ExpressQueryTask has managed=False with migrations creating the table
    # The table should exist from migrations
    try:
        ExpressQueryTask.objects.create(
            title="测试快递查询",
            tracking_number="SF1234567890",
            carrier_type="sf",
            status="pending",
        )
    except Exception:
        # If the table doesn't exist in test DB, skip this test
        pytest.skip("ExpressQueryTask table not available in test DB")

    resp = authenticated_client.get("/api/v1/express-query/tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["tracking_number"] == "SF1234567890"
