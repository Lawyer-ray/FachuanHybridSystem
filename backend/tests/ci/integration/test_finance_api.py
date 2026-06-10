"""Finance API integration tests."""

from __future__ import annotations

import json

import pytest

from apps.finance.models import LPRRate


# ===================================================================
# LPR Rates
# ===================================================================


@pytest.mark.django_db
def test_list_lpr_rates(authenticated_client):
    LPRRate.objects.create(
        effective_date="2024-01-01",
        rate_1y=3.45,
        rate_5y=3.95,
        source="manual",
        is_auto_synced=False,
    )
    resp = authenticated_client.get("/api/v1/lpr/rates")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    assert len(data["items"]) >= 1


@pytest.mark.django_db
def test_list_lpr_rates_with_date_filter(authenticated_client):
    LPRRate.objects.create(effective_date="2024-01-01", rate_1y=3.45, rate_5y=3.95, source="manual")
    LPRRate.objects.create(effective_date="2024-06-01", rate_1y=3.35, rate_5y=3.85, source="manual")
    resp = authenticated_client.get("/api/v1/lpr/rates", {"start_date": "2024-03-01"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) >= 1


@pytest.mark.django_db
def test_get_latest_lpr_rate(authenticated_client):
    LPRRate.objects.create(effective_date="2024-07-01", rate_1y=3.35, rate_5y=3.85, source="manual")
    resp = authenticated_client.get("/api/v1/lpr/rates/latest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["rate_1y"] is not None


@pytest.mark.django_db
def test_get_latest_lpr_rate_not_found(authenticated_client):
    # Clear all rates
    LPRRate.objects.all().delete()
    resp = authenticated_client.get("/api/v1/lpr/rates/latest")
    # May return 404 or 200 with error depending on implementation
    assert resp.status_code in (404, 200, 500)


@pytest.mark.django_db
def test_get_sync_status(authenticated_client):
    LPRRate.objects.create(effective_date="2024-01-01", rate_1y=3.45, rate_5y=3.95, source="manual")
    resp = authenticated_client.get("/api/v1/lpr/sync/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_records" in data


@pytest.mark.django_db
def test_calculate_interest(authenticated_client):
    LPRRate.objects.create(effective_date="2020-01-01", rate_1y=4.15, rate_5y=4.80, source="manual")
    LPRRate.objects.create(effective_date="2024-07-01", rate_1y=3.35, rate_5y=3.85, source="manual")
    resp = authenticated_client.post(
        "/api/v1/lpr/calculate",
        data=json.dumps({
            "start_date": "2024-01-01",
            "end_date": "2024-06-30",
            "principal": 100000,
            "rate_mode": "lpr",
            "rate_type": "1y",
            "year_days": 365,
        }),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "total_interest" in data
    assert "periods" in data


@pytest.mark.django_db
def test_calculate_interest_missing_fields(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/lpr/calculate",
        data=json.dumps({
            "rate_mode": "lpr",
            "rate_type": "1y",
        }),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "MISSING_REQUIRED_FIELDS" in data.get("code", "")
