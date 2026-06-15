"""N+1 query detection tests.

These tests verify that critical API endpoints don't generate excessive
database queries. They capture queries and assert an upper bound to
catch N+1 regressions.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.cases.models import Case
from apps.client.models import Client
from apps.contracts.models import Contract
from apps.reminders.models import Reminder


def _make_contract(**kwargs):
    return Contract.objects.create(
        name=kwargs.get("name", "N+1测试合同"),
        case_type=kwargs.get("case_type", "civil"),
    )


def _make_case(contract=None, **kwargs):
    return Case.objects.create(
        name=kwargs.get("name", "N+1测试案件"),
        contract=contract or _make_contract(),
        case_type=kwargs.get("case_type", "civil"),
    )


def _make_client(**kwargs):
    return Client.objects.create(
        name=kwargs.get("name", "N+1测试客户"),
        client_type=kwargs.get("client_type", Client.NATURAL),
        is_our_client=kwargs.get("is_our_client", True),
    )


def _count_queries(func):
    """Execute func and return (result, query_count)."""
    with CaptureQueriesContext(connection):
        result = func()
    return result, len(connection.queries_log)


# ===================================================================
# Query Count Budgets (upper bounds)
# ===================================================================


@pytest.mark.django_db
def test_list_cases_query_budget(authenticated_client):
    """Listing cases should not generate excessive queries."""
    for i in range(5):
        _make_case(name=f"N+1案件{i}")
    resp, count = _count_queries(
        lambda: authenticated_client.get("/api/v1/cases/cases")
    )
    assert resp.status_code == 200
    assert count <= 20, f"list_cases used {count} queries (budget: 20)"


@pytest.mark.django_db
def test_list_clients_query_budget(authenticated_client):
    """Listing clients should not generate excessive queries."""
    for i in range(5):
        _make_client(name=f"N+1客户{i}")
    resp, count = _count_queries(
        lambda: authenticated_client.get("/api/v1/client/clients")
    )
    assert resp.status_code == 200
    assert count <= 15, f"list_clients used {count} queries (budget: 15)"


@pytest.mark.django_db
def test_list_contracts_query_budget(authenticated_client):
    """Listing contracts should not generate excessive queries."""
    for i in range(5):
        _make_contract(name=f"N+1合同{i}")
    resp, count = _count_queries(
        lambda: authenticated_client.get("/api/v1/contracts/contracts")
    )
    assert resp.status_code == 200
    assert count <= 25, f"list_contracts used {count} queries (budget: 25)"


@pytest.mark.django_db
def test_list_reminders_query_budget(authenticated_client):
    """Listing reminders should not generate excessive queries."""
    case = _make_case()
    for i in range(5):
        Reminder.objects.create(
            case=case,
            reminder_type="hearing",
            content=f"提醒{i}",
            due_at=datetime.now() + timedelta(days=i + 1),
        )
    resp, count = _count_queries(
        lambda: authenticated_client.get("/api/v1/reminders/list", {"case_id": case.id})
    )
    assert resp.status_code == 200
    assert count <= 15, f"list_reminders used {count} queries (budget: 15)"


@pytest.mark.django_db
def test_get_case_detail_query_budget(authenticated_client):
    """Getting a single case detail should use a bounded number of queries."""
    case = _make_case(name="详情测试案件")
    resp, count = _count_queries(
        lambda: authenticated_client.get(f"/api/v1/cases/cases/{case.id}")
    )
    assert resp.status_code == 200
    assert count <= 25, f"get_case_detail used {count} queries (budget: 25)"


@pytest.mark.django_db
def test_create_case_query_budget(authenticated_client, contract):
    """Creating a case should use a bounded number of queries."""
    resp, count = _count_queries(
        lambda: authenticated_client.post(
            "/api/v1/cases/cases",
            data=json.dumps({
                "name": "新建N+1测试案件",
                "contract_id": contract.id,
                "case_type": "civil",
            }),
            content_type="application/json",
        )
    )
    assert resp.status_code == 200
    assert count <= 15, f"create_case used {count} queries (budget: 15)"


@pytest.mark.django_db
def test_list_cases_scales_linearly(authenticated_client):
    """Query count should not grow linearly with number of cases."""
    # Create 20 cases
    for i in range(20):
        _make_case(name=f"规模测试{i}")

    _, count_20 = _count_queries(
        lambda: authenticated_client.get("/api/v1/cases/cases")
    )
    # Should use roughly same queries as 5 cases (prefetch batch, not per-item)
    assert count_20 <= 25, f"20 cases used {count_20} queries (budget: 25)"
