"""``/api/v1/agent/skills*`` 全链路：清单/配额/CRUD/启停/越权 404/内置只读/版本冲突 409。

用 Django test client（与真实路由/鉴权一致），不 mock service：这些端点的价值
就在「参数装配 + 领域错误 → HTTP 状态码」这一层，mock 掉就什么也没测。

写/生命周期端点各自还有专门的用例文件（``test_skill_review_api.py`` 走双轨发布，
``test_skill_content_endpoint.py`` 走正文分段），本文件守住清单与 CRUD 的基本面。
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from apps.agent.models import AgentSkill, AgentSkillPreference, AgentSkillRevision
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


def _published_firm_skill(lawyer: Lawyer, name: str = "firm-rule") -> AgentSkill:
    """已发布的所内技能（``published_revision`` 非空）——写路径的 FOR UPDATE 用例要它。"""
    skill = AgentSkill.objects.create(
        scope=AgentSkill.Scope.LAW_FIRM,
        law_firm=lawyer.law_firm,
        name=name,
        title="所内规范",
        description="全所统一使用",
        body="# 所内正文",
        status=AgentSkill.Status.ACTIVE,
        version=1,
        created_by=lawyer,
    )
    revision = AgentSkillRevision.objects.create(
        skill=skill,
        version=1,
        title=skill.title,
        description=skill.description,
        body=skill.body,
        status=skill.status,
    )
    skill.published_revision = revision
    skill.save(update_fields=["published_revision"])
    return skill


@pytest.mark.django_db
class TestListAndQuota:
    def test_lists_builtin_with_contract_fields(self) -> None:
        """内置条目必须给出 CONTRACT §2 的**完整**字段集（前端只读这些判据）。"""
        _, client = _make_user("skill-api-list")
        body = _send(client, "get", BASE).json()
        web = next(skill for skill in body["skills"] if skill["name"] == "web-research")
        assert web == {
            "key": "builtin:web-research",
            "name": "web-research",
            "title": "web-research",
            "description": web["description"],
            "scope": "builtin",
            "scope_weight": -1,
            "source": "builtin",
            "enabled": True,
            "editable": False,
            "version": 0,
            "status": "active",
            "review_status": "none",
            "review_note": "",
            "published_version": 0,
            "has_unpublished_changes": False,
            "shadowed": [],
            "effective": True,
            "shadowed_by": None,
            "can_edit": False,
            "can_submit": False,
            "can_review": False,
            "can_archive": False,
            "can_restore": False,
            # 内置技能没有可提升的目标层：``can_promote`` 也必须是 False，
            # 且字段本身要在（少一个就 500）
            "can_promote": False,
        }

    def test_scope_filter(self) -> None:
        _, client = _make_user("skill-api-list-scope")
        _create(client, name="mine-one")
        assert [s["scope"] for s in _send(client, "get", f"{BASE}?scope=lawyer").json()["skills"]] == ["lawyer"]
        assert {s["scope"] for s in _send(client, "get", f"{BASE}?scope=builtin").json()["skills"]} == {"builtin"}
        assert _send(client, "get", f"{BASE}?scope=law_firm").json()["skills"] == []
        assert len(_send(client, "get", f"{BASE}?scope=all").json()["skills"]) == len(
            _send(client, "get", BASE).json()["skills"]
        )

    def test_scope_filter_rejects_unknown_value(self) -> None:
        _, client = _make_user("skill-api-list-scope-bad")
        assert _send(client, "get", f"{BASE}?scope=everything").status_code == 422

    def test_quota(self) -> None:
        _, client = _make_user("skill-api-quota")
        _create(client)
        assert _send(client, "get", f"{BASE}/quota").json() == {
            "max_skills": 20,
            "used": 1,
            "by_scope": {"lawyer": 1, "team": 0, "law_firm": 0},
            "max_by_scope": {"lawyer": 20, "team": 30, "law_firm": 60},
            "can_create_firm": False,
            "promotable_scopes": [],
        }

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
        assert body["safety"] == []
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
        mine = next(skill for skill in listed if skill["key"] == detail["key"])
        assert mine["effective"] is True
        assert mine["can_edit"] is True
        assert mine["can_submit"] is False  # 个人技能不走审批

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
            assert body["scope"] == "builtin"
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

    def test_update_published_firm_skill_is_not_500(self) -> None:
        """回归：``FOR UPDATE`` 撞上可空外键的 LEFT OUTER JOIN（线上会 500）。

        ``_resolve_skill_row`` 带 ``select_related("team", "published_revision")``，
        两个外键都可空；PostgreSQL 不允许 ``FOR UPDATE`` 作用于 outer join 的可空侧。
        这条用例特意用**已发布**（``published_revision`` 非空）的所内技能——个人技能
        的 ``published_revision`` 在本路径上同样非空，但共享技能的 join 分支多一个
        ``team``，是最容易踩到的那条。
        """
        user, client = _make_user("skill-api-update-firm")
        Lawyer.objects.filter(pk=user.pk).update(is_admin=True)
        skill = _published_firm_skill(user)
        response = _send(
            client,
            "put",
            f"{BASE}/skill:{skill.pk}",
            {"title": "改过的标题", "description": "改过的描述", "body": "# 改过的正文", "version": 1},
        )
        assert response.status_code == 200, response.content.decode("utf-8", "ignore")
        assert response.json()["version"] == 2

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
        web = next(skill for skill in listed if skill["name"] == "web-research")
        assert web["enabled"] is False
        assert web["effective"] is False

    def test_toggle_personal(self) -> None:
        _, client = _make_user("skill-api-toggle-personal")
        detail = _create(client)
        response = _send(client, "patch", f"{BASE}/{detail['key']}", {"enabled": False})
        assert response.json() == {"key": detail["key"], "enabled": False}
        listed = _send(client, "get", BASE).json()["skills"]
        assert next(skill for skill in listed if skill["key"] == detail["key"])["enabled"] is False

    def test_toggle_unknown_is_404(self) -> None:
        """``ValueError → 404`` 的兼容转换只留给启停端点（见 skill_api 模块 docstring）。"""
        _, client = _make_user("skill-api-toggle-unknown")
        assert _send(client, "patch", f"{BASE}/no-such-skill", {"enabled": True}).status_code == 404
        assert _send(client, "patch", f"{BASE}/Bad_Name", {"enabled": True}).status_code == 404


@pytest.mark.django_db
class TestSharedToggle:
    def test_toggle_shared_skill_writes_only_my_preference(self) -> None:
        """共享技能的 ``AgentSkill.enabled`` 是全所共用的一行。

        一个普通律师点开关绝不能把全所的指令关掉（写穿）；启停必须落在他自己的
        ``AgentSkillPreference`` 上。这条不变量的闸门在 service，但它的**接线**在
        这个端点——写错作用域时不会有任何报错，只会有人说「今天 AI 好像不听话了」。
        """
        from django.test import Client

        admin, admin_client = _make_user("skill-api-shared-admin")
        Lawyer.objects.filter(pk=admin.pk).update(is_admin=True)
        skill = _published_firm_skill(admin)
        member = Lawyer.objects.create_user(
            username="skill-api-shared-member", password=TEST_PASSWORD, law_firm=admin.law_firm
        )
        client = Client()
        client.force_login(member)

        response = _send(client, "patch", f"{BASE}/skill:{skill.pk}", {"enabled": False})
        assert response.json() == {"key": f"skill:{skill.pk}", "enabled": False}
        skill.refresh_from_db()
        assert skill.enabled is True
        assert AgentSkillPreference.objects.filter(
            user=member, skill_key=f"skill:{skill.pk}", enabled=False
        ).exists()
        # 同所管理员不受影响：他自己没关过这条
        listed = _send(admin_client, "get", BASE).json()["skills"]
        assert next(item for item in listed if item["key"] == f"skill:{skill.pk}")["enabled"] is True


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


@pytest.mark.django_db
class TestArchivedLifecycle:
    def test_archived_skill_listed_but_not_effective(self) -> None:
        """下线后：清单里还在（要能点「恢复」），但 ``effective=False`` 且取不到正文。

        ``effective`` 是前端显示「已在用 / 已停用」的唯一判据，它在 API 响应里就必须
        与交付面一致：归档的指令已经不在模型上下文里，前端不能还显示成生效。
        """
        _, client = _make_user("skill-api-archived")
        detail = _create(client)
        archived = _send(client, "post", f"{BASE}/{detail['key']}/archive", {})
        assert archived.status_code == 200, archived.content.decode("utf-8", "ignore")
        assert archived.json()["status"] == "archived"

        listed = next(s for s in _send(client, "get", BASE).json()["skills"] if s["key"] == detail["key"])
        assert listed["status"] == "archived"
        assert listed["effective"] is False
        assert listed["can_restore"] is True
        assert _send(client, "get", f"{BASE}/resolve/{detail['key']}/content").status_code == 404


@pytest.mark.django_db
class TestWriteSwitch:
    def test_write_endpoints_are_503_when_switch_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """运营开关 ``off`` → 写端点 503（不是 403：403 会把律师引去申请权限）。"""
        _, client = _make_user("skill-api-switch-off")
        monkeypatch.setenv("FACHUAN_AGENT_USER_SKILLS", "off")
        response = _send(client, "post", BASE, {"title": "t", "description": "d", "body": "b"})
        assert response.status_code == 503
        # 读端点保留（取证要能看）
        assert _send(client, "get", BASE).status_code == 200
