"""Client API integration tests."""

from __future__ import annotations

import json

import pytest

from apps.client.models import Client, PropertyClue


# ===================================================================
# Client CRUD
# ===================================================================


@pytest.mark.django_db
def test_list_clients(authenticated_client):
    Client.objects.create(name="客户甲", client_type=Client.NATURAL, is_our_client=True)
    Client.objects.create(name="客户乙", client_type=Client.LEGAL, is_our_client=False)
    resp = authenticated_client.get("/api/v1/client/clients")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 2


@pytest.mark.django_db
def test_list_clients_filter_type(authenticated_client):
    Client.objects.create(name="自然人客户", client_type=Client.NATURAL, is_our_client=True)
    Client.objects.create(name="法人客户", client_type=Client.LEGAL, is_our_client=True)
    resp = authenticated_client.get("/api/v1/client/clients", {"client_type": "natural"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert all(c["client_type"] == "natural" for c in data)


@pytest.mark.django_db
def test_list_clients_filter_our_client(authenticated_client):
    Client.objects.create(name="我方客户", client_type=Client.NATURAL, is_our_client=True)
    Client.objects.create(name="对方客户", client_type=Client.NATURAL, is_our_client=False)
    resp = authenticated_client.get("/api/v1/client/clients", {"is_our_client": "true"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1


@pytest.mark.django_db
def test_list_clients_search(authenticated_client):
    Client.objects.create(name="张三", client_type=Client.NATURAL, is_our_client=True)
    Client.objects.create(name="李四", client_type=Client.NATURAL, is_our_client=True)
    resp = authenticated_client.get("/api/v1/client/clients", {"search": "张三"})
    assert resp.status_code == 200
    data = resp.json()
    assert any("张三" in c["name"] for c in data)


@pytest.mark.django_db
def test_create_client(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/client/clients",
        data=json.dumps({"name": "新客户", "client_type": "natural", "is_our_client": True, "phone": "13800000000"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "新客户"
    assert Client.objects.filter(id=data["id"]).exists()


@pytest.mark.django_db
def test_create_legal_client(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/client/clients",
        data=json.dumps({"name": "某某公司", "client_type": "legal", "legal_representative": "王五"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["client_type"] == "legal"


@pytest.mark.django_db
def test_get_client_detail(authenticated_client):
    client = Client.objects.create(name="详情客户", client_type=Client.NATURAL, is_our_client=True)
    resp = authenticated_client.get(f"/api/v1/client/clients/{client.id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "详情客户"


@pytest.mark.django_db
def test_update_client(authenticated_client):
    client = Client.objects.create(name="更新前", client_type=Client.NATURAL, is_our_client=True)
    resp = authenticated_client.put(
        f"/api/v1/client/clients/{client.id}",
        data=json.dumps({"name": "更新后"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "更新后"


@pytest.mark.django_db
def test_delete_client(authenticated_client):
    client = Client.objects.create(name="待删除", client_type=Client.NATURAL, is_our_client=True)
    resp = authenticated_client.delete(f"/api/v1/client/clients/{client.id}")
    assert resp.status_code == 204
    assert not Client.objects.filter(id=client.id).exists()


@pytest.mark.django_db
def test_get_related_items(authenticated_client):
    client = Client.objects.create(name="关联客户", client_type=Client.NATURAL, is_our_client=True)
    resp = authenticated_client.get(f"/api/v1/client/clients/{client.id}/related-items")
    assert resp.status_code == 200
    data = resp.json()
    assert "cases" in data
    assert "contracts" in data


# ===================================================================
# Parse Text
# ===================================================================


@pytest.mark.django_db
def test_parse_client_text(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/client/clients/parse-text",
        data=json.dumps({"text": "张三 13800138000 北京市朝阳区", "parse_multiple": False}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "client" in data


@pytest.mark.django_db
def test_parse_client_text_multi(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/client/clients/parse-text",
        data=json.dumps({"text": "张三 13800138000\n李四 13900139000", "parse_multiple": True}),
        content_type="application/json",
    )
    assert resp.status_code == 200


@pytest.mark.django_db
def test_parse_text_get(authenticated_client):
    resp = authenticated_client.get("/api/v1/client/parse-text", {"text": "张三 13800138000"})
    assert resp.status_code == 200


# ===================================================================
# Validate ID Card
# ===================================================================


@pytest.mark.django_db
def test_validate_id_card_valid(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/client/clients/validate-id-card",
        data=json.dumps({"id_number": "110101199001011234"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "valid" in data
    assert "message" in data


@pytest.mark.django_db
def test_validate_id_card_invalid(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/client/clients/validate-id-card",
        data=json.dumps({"id_number": "12345"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["valid"] is False


# ===================================================================
# OA Credential Check
# ===================================================================


@pytest.mark.django_db
def test_check_oa_credential(authenticated_client):
    resp = authenticated_client.get("/api/v1/client/clients/check-oa-credential")
    assert resp.status_code == 200
    assert "has_credential" in resp.json()


# ===================================================================
# Property Clue CRUD
# ===================================================================


@pytest.mark.django_db
def test_list_property_clues(authenticated_client):
    client = Client.objects.create(name="财产线索客户", client_type=Client.NATURAL)
    PropertyClue.objects.create(client=client, clue_type="bank", content="工商银行 6222xxxx")
    resp = authenticated_client.get(f"/api/v1/client/clients/{client.id}/property-clues")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.django_db
def test_create_property_clue(authenticated_client):
    client = Client.objects.create(name="新建线索客户", client_type=Client.NATURAL)
    resp = authenticated_client.post(
        f"/api/v1/client/clients/{client.id}/property-clues",
        data=json.dumps({"clue_type": "bank", "content": "建设银行 6227xxxx"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["clue_type"] == "bank"
    assert PropertyClue.objects.filter(id=data["id"]).exists()


@pytest.mark.django_db
def test_get_property_clue_detail(authenticated_client):
    client = Client.objects.create(name="线索详情客户", client_type=Client.NATURAL)
    clue = PropertyClue.objects.create(client=client, clue_type="real_estate", content="朝阳区房产")
    resp = authenticated_client.get(f"/api/v1/client/property-clues/{clue.id}")
    assert resp.status_code == 200
    assert resp.json()["content"] == "朝阳区房产"


@pytest.mark.django_db
def test_update_property_clue(authenticated_client):
    client = Client.objects.create(name="更新线索客户", client_type=Client.NATURAL)
    clue = PropertyClue.objects.create(client=client, clue_type="bank", content="旧信息")
    resp = authenticated_client.put(
        f"/api/v1/client/property-clues/{clue.id}",
        data=json.dumps({"content": "新信息"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["content"] == "新信息"


@pytest.mark.django_db
def test_delete_property_clue(authenticated_client):
    client = Client.objects.create(name="删除线索客户", client_type=Client.NATURAL)
    clue = PropertyClue.objects.create(client=client, clue_type="other", content="京A12345")
    resp = authenticated_client.delete(f"/api/v1/client/property-clues/{clue.id}")
    assert resp.status_code == 204
    assert not PropertyClue.objects.filter(id=clue.id).exists()


@pytest.mark.django_db
def test_get_content_template(authenticated_client):
    resp = authenticated_client.get("/api/v1/client/property-clues/content-template", {"clue_type": "bank"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["clue_type"] == "bank"
    assert "template" in data
