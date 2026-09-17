"""当事人检索端点（/api/v1/client/parties/search）集成测试。

背景：party 检索若复用 /clients 的完整 ClientOut（含 identity_docs），当某客户
证件文件路径为空时整条序列化 500。本端点返回精简字段、不携带证件文档，故即使
客户存在证件档案也不受影响。
"""

from __future__ import annotations

import pytest


@pytest.mark.django_db
def test_search_parties_returns_lean_fields(authenticated_client, client_entity) -> None:
    resp = authenticated_client.get("/api/v1/client/parties/search", {"keyword": "Fixture测试客户"})
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)
    hit = next((i for i in items if i["name"] == "Fixture测试客户"), None)
    assert hit is not None
    # 只返回检索填报所需的精简字段，不携带 identity_docs（规避证件序列化缺陷）
    assert set(hit.keys()) == {"id", "name", "phone", "is_our_client"}


@pytest.mark.django_db
def test_search_parties_survives_client_with_identity_docs(authenticated_client, client_entity, db) -> None:
    from apps.client.models import Client, ClientIdentityDoc

    client = Client.objects.get(id=client_entity.id)
    ClientIdentityDoc.objects.create(client=client, doc_type=ClientIdentityDoc.DOC_TYPE_CHOICES[0][0])
    resp = authenticated_client.get("/api/v1/client/parties/search", {"keyword": "Fixture测试客户"})
    assert resp.status_code == 200
    items = resp.json()
    hit = next((i for i in items if i["name"] == "Fixture测试客户"), None)
    assert hit is not None
    assert "identity_docs" not in hit
    assert resp.content.decode().find("identity_docs") == -1


@pytest.mark.django_db
def test_search_parties_filters_our_client(authenticated_client, db) -> None:
    from apps.client.models import Client

    Client.objects.create(name="我方客户主体", client_type=Client.NATURAL, is_our_client=True)
    Client.objects.create(name="对方法务顾问", client_type=Client.NATURAL, is_our_client=False)

    # 委托人：仅返回我方当事人
    ours = authenticated_client.get(
        "/api/v1/client/parties/search",
        {"keyword": "方", "is_our_client": "true"},
    )
    assert ours.status_code == 200
    ours_names = [i["name"] for i in ours.json()]
    assert "我方客户主体" in ours_names
    assert "对方法务顾问" not in ours_names

    # 对方当事人：仅返回非我方当事人
    theirs = authenticated_client.get(
        "/api/v1/client/parties/search",
        {"keyword": "方", "is_our_client": "false"},
    )
    assert theirs.status_code == 200
    theirs_names = [i["name"] for i in theirs.json()]
    assert "对方法务顾问" in theirs_names
    assert "我方客户主体" not in theirs_names
