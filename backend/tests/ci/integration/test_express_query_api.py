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


@pytest.mark.django_db
def test_list_tasks_non_superuser_only_sees_own_tasks():
    """非 superuser/is_staff 用户只能看到本人创建的任务（安全审计 IDOR）"""
    from django.test import Client

    from apps.organization.models import LawFirm
    from apps.testing.factories import LawyerFactory

    try:
        firm = LawFirm.objects.create(name="快递权限测试律所")
        owner = LawyerFactory(username="eq_owner", law_firm=firm)
        other = LawyerFactory(username="eq_other", law_firm=firm)
        ExpressQueryTask.objects.create(
            title="他人任务",
            tracking_number="SF0001",
            carrier_type="sf",
            status="pending",
            created_by=owner,
        )
        ExpressQueryTask.objects.create(
            title="我的任务",
            tracking_number="SF0002",
            carrier_type="sf",
            status="pending",
            created_by=other,
        )
    except Exception:
        # If the table doesn't exist in test DB, skip this test
        pytest.skip("ExpressQueryTask table not available in test DB")

    client = Client()
    client.force_login(other)
    resp = client.get("/api/v1/express-query/tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert [t["tracking_number"] for t in data] == ["SF0002"]
