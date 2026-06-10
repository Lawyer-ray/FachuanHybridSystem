"""Contacts API integration tests."""

from __future__ import annotations

import json

import pytest

from apps.contacts.models import CaseContact
from apps.contracts.models import Contract
from apps.cases.models import Case


def _make_case():
    contract = Contract.objects.create(name="联系人测试合同", case_type="civil")
    return Case.objects.create(name="联系人测试案件", contract=contract)


# ===================================================================
# Contact CRUD
# ===================================================================


@pytest.mark.django_db
def test_list_contacts(authenticated_client):
    case = _make_case()
    CaseContact.objects.create(case=case, name="王法官", role="judge", phone="010-12345678")
    resp = authenticated_client.get("/api/v1/contacts/contacts", {"case_id": case.id})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert any(c["name"] == "王法官" for c in data)


@pytest.mark.django_db
def test_list_contacts_filter_stage(authenticated_client):
    case = _make_case()
    CaseContact.objects.create(case=case, name="张书记员", role="clerk", stage="first_trial")
    CaseContact.objects.create(case=case, name="李法官", role="judge", stage="second_trial")
    resp = authenticated_client.get("/api/v1/contacts/contacts", {"stage": "first_trial"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1


@pytest.mark.django_db
def test_create_contact(authenticated_client):
    case = _make_case()
    resp = authenticated_client.post(
        "/api/v1/contacts/contacts",
        data=json.dumps({
            "case_id": case.id,
            "name": "赵法官",
            "role": "judge",
            "phone": "010-87654321",
            "address": "北京市海淀区",
        }),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "赵法官"
    assert CaseContact.objects.filter(id=data["id"]).exists()


@pytest.mark.django_db
def test_get_contact_detail(authenticated_client):
    case = _make_case()
    contact = CaseContact.objects.create(case=case, name="孙法官", role="judge", phone="010-11111111")
    resp = authenticated_client.get(f"/api/v1/contacts/contacts/{contact.id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "孙法官"


@pytest.mark.django_db
def test_update_contact(authenticated_client):
    case = _make_case()
    contact = CaseContact.objects.create(case=case, name="更新前", role="judge")
    resp = authenticated_client.put(
        f"/api/v1/contacts/contacts/{contact.id}",
        data=json.dumps({"name": "更新后", "phone": "010-99999999"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "更新后"


@pytest.mark.django_db
def test_delete_contact(authenticated_client):
    case = _make_case()
    contact = CaseContact.objects.create(case=case, name="待删除", role="clerk")
    resp = authenticated_client.delete(f"/api/v1/contacts/contacts/{contact.id}")
    assert resp.status_code == 200
    assert not CaseContact.objects.filter(id=contact.id).exists()


@pytest.mark.django_db
def test_search_contacts(authenticated_client):
    case = _make_case()
    CaseContact.objects.create(case=case, name="搜索测试法官", role="judge", phone="010-12345678")
    resp = authenticated_client.get("/api/v1/contacts/contacts/search", {"q": "搜索测试"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
