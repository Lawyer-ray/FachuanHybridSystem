"""``/api/v1/agent/skills*`` 全链路：CRUD、越权 404、内置只读、版本冲突 409。

用 Django test client（与真实路由/鉴权一致），不 mock service：这些端点的价值
就在「参数装配 + 领域错误 → HTTP 状态码」这一层，mock 掉就什么也没测。
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from apps.agent.models import AgentSkillPreference
from apps.organization.models import LawFirm, Lawyer

TEST_PASSWORD = "x-test-12345678"  # pragma: allowlist secret
BASE = "/api/v1/agent/skills"


def _make_user(username: str) -> tuple[Lawyer, Any]:
    from django.test import Client

    firm = LawFirm.objects.create(name=f"技能 API 所-{username}")
    user = Lawyer.objects.create_user(username=username, password=TEST_PASSWORD, law_firm=firm)
    client = Client()
    client.force_login(user)
    return user, client


def _send(client: Any, method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
    kwargs: dict[str, Any] = {"content_type": "application/json"}
    if payload is not None:
        kwargs["data"] = json.dumps(payload)
    return getattr(client, method)(url, **kwargs)


def _create(client: Any, **overrides: Any) -> dict:
    payload = {"title": "合同审查三段式", "description": "审查合同时按三段式给出结论", "body": "# 做法\n1. 看主体"}
    payload.update(overrides)
    response = _send(client, "post", BASE, payload)
    assert response.status_code == 201, response.content.decode("utf-8", "ignore")
    return response.json()


@pytest.mark.django_db
class TestListAndQuota:
    def test_lists_builtin_with_contract_fields(self) -> None:
        _, client = _make_user("skill-api-list")
        body = _send(client, "get", BASE).json()
        web = next(skill for skill in body["skills"] if skill["name"] == "web-research")
        assert web == {
            "key": "builtin:web-research",
            "name": "web-research",
            "title": "web-research",
            "description": web["description"],
            "enabled": True,
            "source": "builtin",
            "scope": "",
            "editable": False,
            "version": 0,
        }

    def test_quota(self) -> None:
        _, client = _make_user("skill-api-quota")
        _create(client)
        assert _send(client, "get", f"{BASE}/quota").json() == {"max_skills": 20, "used": 1}

    def test_requires_auth(self, api_client: Any) -> None:
        assert api_client.get(BASE).status_code in (401, 403)


@pytest.mark.django_db
class TestValidate:
    def test_ok_includes_rendered_preview(self) -> None:
        _, client = _make_user("skill-api-validate-ok")
        response = _send(
            client, "post", f"{BASE}/validate", {"title": "我的技能", "description": "什么时候用", "body": "# 做法"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["errors"] == []
        assert body["preview"].startswith("---\nname: ")
        assert 'description: "什么时候用"' in body["preview"]

    def test_field_errors_listed_all_at_once(self) -> None:
        _, client = _make_user("skill-api-validate-bad")
        response = _send(
            client, "post", f"{BASE}/validate", {"name": "Bad_Name", "title": "", "description": "两行\n描述", "body": ""}
        )
        body = response.json()
        assert body["ok"] is False
        assert {error["field"] for error in body["errors"]} == {"name", "title", "description", "body"}

    def test_reserved_name_reported_by_validate(self) -> None:
        _, client = _make_user("skill-api-validate-reserved")
        body = _send(
            client, "post", f"{BASE}/validate", {"name": "web-research", "title": "t", "description": "d", "body": "b"}
        ).json()
        assert body["ok"] is False
        assert any("保留名" in error["message"] for error in body["errors"])


@pytest.mark.django_db
class TestCreateAndDetail:
    def test_create_generates_name_when_omitted(self) -> None:
        _, client = _make_user("skill-api-create")
        detail = _create(client)
        assert detail["name"].startswith("skill-")
        assert detail["key"] == f"skill:{detail['key'].split(':', 1)[1]}"
        assert detail["source"] == "user"
        assert detail["scope"] == "lawyer"
        assert detail["editable"] is True
        assert detail["version"] == 1
        assert detail["body"] == "# 做法\n1. 看主体"
        listed = _send(client, "get", BASE).json()["skills"]
        assert any(skill["key"] == detail["key"] for skill in listed)

    def test_create_with_explicit_name(self) -> None:
        _, client = _make_user("skill-api-create-named")
        assert _create(client, name="my-contract-review")["name"] == "my-contract-review"

    def test_duplicate_personal_name_is_409(self) -> None:
        _, client = _make_user("skill-api-duplicate-name")
        _create(client, name="my-skill")
        assert _send(client, "post", BASE, {"name": "my-skill", "title": "t", "description": "d", "body": "b"}).status_code == 409

    def test_reserved_builtin_name_is_409(self) -> None:
        _, client = _make_user("skill-api-reserved")
        response = _send(client, "post", BASE, {"name": "web-research", "title": "t", "description": "d", "body": "b"})
        assert response.status_code == 409

    def test_bad_slug_is_422(self) -> None:
        _, client = _make_user("skill-api-bad-slug")
        response = _send(client, "post", BASE, {"name": "Bad_Name", "title": "t", "description": "d", "body": "b"})
        assert response.status_code == 422
        assert "name" in response.content.decode("utf-8", "ignore")

    def test_detail_builtin_by_key_and_bare_name(self) -> None:
        _, client = _make_user("skill-api-detail-builtin")
        for key in ("builtin:web-research", "web-research"):
            body = _send(client, "get", f"{BASE}/{key}").json()
            assert body["key"] == "builtin:web-research"
            assert body["body"]
            assert body["editable"] is False

    def test_detail_personal(self) -> None:
        _, client = _make_user("skill-api-detail-personal")
        detail = _create(client)
        body = _send(client, "get", f"{BASE}/{detail['key']}").json()
        assert body["body"] == detail["body"]

    def test_detail_of_other_lawyer_is_404(self) -> None:
        _, owner_client = _make_user("skill-api-owner")
        _, other_client = _make_user("skill-api-other")
        detail = _create(owner_client)
        assert _send(other_client, "get", f"{BASE}/{detail['key']}").status_code == 404


@pytest.mark.django_db
class TestUpdate:
    def test_update_bumps_version(self) -> None:
        _, client = _make_user("skill-api-update")
        detail = _create(client)
        response = _send(
            client,
            "put",
            f"{BASE}/{detail['key']}",
            {"title": "新标题", "description": "新描述", "body": "# 新正文", "version": 1},
        )
        assert response.status_code == 200
        updated = response.json()
        assert updated["version"] == 2
        assert updated["title"] == "新标题"
        assert updated["body"] == "# 新正文"

    def test_version_conflict_is_409(self) -> None:
        _, client = _make_user("skill-api-version")
        detail = _create(client)
        url = f"{BASE}/{detail['key']}"
        _send(client, "put", url, {"title": "t", "description": "d", "body": "b", "version": 1})
        conflict = _send(client, "put", url, {"title": "t", "description": "d", "body": "b", "version": 1})
        assert conflict.status_code == 409
        assert "v2" in conflict.content.decode("utf-8", "ignore")

    def test_update_builtin_is_404(self) -> None:
        _, client = _make_user("skill-api-update-builtin")
        response = _send(client, "put", f"{BASE}/web-research", {"title": "t", "description": "d", "body": "b", "version": 0})
        assert response.status_code == 404


@pytest.mark.django_db
class TestToggle:
    def test_toggle_builtin_by_bare_name(self) -> None:
        user, client = _make_user("skill-api-toggle-builtin")
        response = _send(client, "patch", f"{BASE}/web-research", {"enabled": False})
        assert response.json() == {"key": "builtin:web-research", "enabled": False}
        assert AgentSkillPreference.objects.filter(user=user, skill_key="builtin:web-research", enabled=False).exists()
        listed = _send(client, "get", BASE).json()["skills"]
        assert next(skill for skill in listed if skill["name"] == "web-research")["enabled"] is False

    def test_toggle_personal(self) -> None:
        _, client = _make_user("skill-api-toggle-personal")
        detail = _create(client)
        response = _send(client, "patch", f"{BASE}/{detail['key']}", {"enabled": False})
        assert response.json() == {"key": detail["key"], "enabled": False}
        listed = _send(client, "get", BASE).json()["skills"]
        assert next(skill for skill in listed if skill["key"] == detail["key"])["enabled"] is False

    def test_toggle_unknown_is_404(self) -> None:
        _, client = _make_user("skill-api-toggle-unknown")
        assert _send(client, "patch", f"{BASE}/no-such-skill", {"enabled": True}).status_code == 404
        assert _send(client, "patch", f"{BASE}/Bad_Name", {"enabled": True}).status_code == 404


@pytest.mark.django_db
class TestDeleteAndDuplicate:
    def test_delete_personal_then_404(self) -> None:
        _, client = _make_user("skill-api-delete")
        detail = _create(client)
        assert _send(client, "delete", f"{BASE}/{detail['key']}").status_code == 204
        assert _send(client, "get", f"{BASE}/{detail['key']}").status_code == 404

    def test_delete_builtin_is_403(self) -> None:
        _, client = _make_user("skill-api-delete-builtin")
        assert _send(client, "delete", f"{BASE}/web-research").status_code == 403

    def test_delete_other_lawyer_is_404(self) -> None:
        _, owner_client = _make_user("skill-api-delete-owner")
        _, other_client = _make_user("skill-api-delete-other")
        detail = _create(owner_client)
        assert _send(other_client, "delete", f"{BASE}/{detail['key']}").status_code == 404

    def test_duplicate_builtin_creates_personal_copy(self) -> None:
        _, client = _make_user("skill-api-duplicate")
        response = _send(client, "post", f"{BASE}/builtin:web-research/duplicate", {})
        assert response.status_code == 201
        copy = response.json()
        assert copy["name"] == "web-research-copy"
        assert copy["source"] == "user"
        assert copy["scope"] == "lawyer"
        assert copy["body"]
        assert copy["title"].endswith("（我的）")

    def test_duplicate_personal_is_403(self) -> None:
        _, client = _make_user("skill-api-duplicate-personal")
        detail = _create(client)
        assert _send(client, "post", f"{BASE}/{detail['key']}/duplicate", {}).status_code == 403
