"""Enterprise Data API integration tests."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


_META = {"provider": "qcc", "transport": "mcp", "tool": "search", "capability": "search"}


def _mock_service():
    svc = MagicMock()
    svc.list_providers.return_value = {"items": []}
    svc.search_companies.return_value = {"query": {"keyword": "测试"}, "data": [], "meta": _META}
    svc.get_company_profile.return_value = {"query": {"company_id": "12345"}, "data": [], "meta": _META}
    svc.get_company_risks.return_value = {"query": {"company_id": "12345"}, "data": [], "meta": _META}
    svc.get_company_shareholders.return_value = {"query": {"company_id": "12345"}, "data": [], "meta": _META}
    svc.get_company_personnel.return_value = {"query": {"company_id": "12345"}, "data": [], "meta": _META}
    svc.get_person_profile.return_value = {"query": {"hcgid": "hcgid123"}, "data": [], "meta": _META}
    svc.search_bidding_info.return_value = {"query": {"keyword": "测试招标"}, "data": [], "meta": _META}
    return svc


@pytest.mark.django_db
def test_list_providers(authenticated_client):
    with patch("apps.enterprise_data.api.enterprise_data_api._service", return_value=_mock_service()):
        resp = authenticated_client.get("/api/v1/enterprise-data/providers")
        assert resp.status_code == 200


@pytest.mark.django_db
def test_search_companies(authenticated_client):
    with patch("apps.enterprise_data.api.enterprise_data_api._service", return_value=_mock_service()):
        resp = authenticated_client.get("/api/v1/enterprise-data/companies/search", {"keyword": "测试"})
        assert resp.status_code == 200


@pytest.mark.django_db
def test_get_company_profile(authenticated_client):
    with patch("apps.enterprise_data.api.enterprise_data_api._service", return_value=_mock_service()):
        resp = authenticated_client.get("/api/v1/enterprise-data/companies/12345")
        assert resp.status_code == 200


@pytest.mark.django_db
def test_get_company_risks(authenticated_client):
    with patch("apps.enterprise_data.api.enterprise_data_api._service", return_value=_mock_service()):
        resp = authenticated_client.get(
            "/api/v1/enterprise-data/companies/12345/risks",
            {"risk_type": "自身风险"},
        )
        assert resp.status_code == 200


@pytest.mark.django_db
def test_get_company_shareholders(authenticated_client):
    with patch("apps.enterprise_data.api.enterprise_data_api._service", return_value=_mock_service()):
        resp = authenticated_client.get("/api/v1/enterprise-data/companies/12345/shareholders")
        assert resp.status_code == 200


@pytest.mark.django_db
def test_get_company_personnel(authenticated_client):
    with patch("apps.enterprise_data.api.enterprise_data_api._service", return_value=_mock_service()):
        resp = authenticated_client.get("/api/v1/enterprise-data/companies/12345/personnel")
        assert resp.status_code == 200


@pytest.mark.django_db
def test_get_person_profile(authenticated_client):
    with patch("apps.enterprise_data.api.enterprise_data_api._service", return_value=_mock_service()):
        resp = authenticated_client.get("/api/v1/enterprise-data/personnel/hcgid123")
        assert resp.status_code == 200


@pytest.mark.django_db
def test_search_bidding_info(authenticated_client):
    with patch("apps.enterprise_data.api.enterprise_data_api._service", return_value=_mock_service()):
        resp = authenticated_client.get(
            "/api/v1/enterprise-data/biddings/search",
            {"keyword": "测试招标"},
        )
        assert resp.status_code == 200
