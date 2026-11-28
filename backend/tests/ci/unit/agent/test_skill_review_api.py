"""共享技能双轨发布的 REST 面：提审 / 审批 / 驳回 / 下线 / 恢复 / 版本对比。

核心不变量（CONTRACT §12 第 6 条）：**编辑不换线上，发布才换线上。** 任何一次
``PUT`` 只改工作区并置 ``review_status=pending``；``status`` 与 ``published_revision``
纹丝不动，``/skills/resolve/{ref}/content`` 继续交付已批准的那一版。只有 ``approve``
会把线上指针挪到新快照。

这条不变量值得一个专门的 API 文件：它跨越「写路径（user_skills）→ 审批（review）→
读路径（resolve）」三层，任何一层的实现漂移都会在**这里**表现为「改一个错别字，
全所 AI 立刻失去这条指令」。
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from apps.agent.models import AgentSkill
from apps.agent.services.skills.render import scope_preamble
from apps.organization.models import LawFirm, Lawyer

TEST_PASSWORD = "x-test-12345678"  # pragma: allowlist secret
BASE = "/api/v1/agent/skills"


def _make_user(username: str, *, is_admin: bool = False) -> tuple[Lawyer, Any]:
    from django.test import Client

    firm = LawFirm.objects.create(name=f"技能审批所-{username}")
    user = Lawyer.objects.create_user(username=username, password=TEST_PASSWORD, law_firm=firm)
    if is_admin:
        # 技能权限只认 lawyer.is_admin（不是 is_superuser / is_staff）
        Lawyer.objects.filter(pk=user.pk).update(is_admin=True)
        user.refresh_from_db()
    client = Client()
    client.force_login(user)
    return user, client


def _send(client: Any, method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
    kwargs: dict[str, Any] = {"content_type": "application/json"}
    if payload is not None:
        kwargs["data"] = json.dumps(payload)
    return getattr(client, method)(url, **kwargs)


def _create_firm_skill(client: Any, *, name: str = "firm-rule", body: str) -> dict:
    response = _send(
        client,
        "post",
        BASE,
        {
            "name": name,
            "title": "所内规范",
            "description": "全所统一使用",
            "body": body,
            "scope": "law_firm",
        },
    )
    assert response.status_code == 201, response.content.decode("utf-8", "ignore")
    return response.json()


def _live_content(client: Any, key: str) -> str:
    response = _send(client, "get", f"{BASE}/resolve/{key}/content")
    assert response.status_code == 200, response.content.decode("utf-8", "ignore")
    return response.json()["content"]


def _rendered(body: str) -> str:
    return f"{scope_preamble('law_firm')}\n\n{body.strip()}\n"


@pytest.mark.django_db
class TestDoubleTrackPublish:
    def test_publish_only_on_approve(self) -> None:
        """新建（草稿）→ 提审 → 通过（v1 上线）→ 编辑（v2 待审）→ 通过（v2 上线）。"""
        _, client = _make_user("review-publish", is_admin=True)
        created = _create_firm_skill(client, body="# 第一版")
        key = created["key"]
        assert created["status"] == "draft"
        assert created["published_version"] == 1
        # 没走审批的共享指令不进交付面
        assert _send(client, "get", f"{BASE}/resolve/{key}/content").status_code == 404

        submitted = _send(client, "post", f"{BASE}/{key}/submit", {"note": "请审"}).json()
        assert submitted["review_status"] == "pending"
        assert submitted["status"] == "draft"
        assert _send(client, "get", f"{BASE}/resolve/{key}/content").status_code == 404

        approved = _send(
            client, "post", f"{BASE}/{key}/review", {"decision": "approve", "acknowledged_firm_wide": True}
        ).json()
        assert approved["status"] == "active"
        assert approved["review_status"] == "none"
        assert approved["published_version"] == 1
        assert approved["has_unpublished_changes"] is False
        assert _live_content(client, key) == _rendered("# 第一版")

        updated = _send(
            client,
            "put",
            f"{BASE}/{key}",
            {"title": "所内规范", "description": "全所统一使用", "body": "# 第二版", "version": 1},
        ).json()
        assert updated["version"] == 2
        assert updated["review_status"] == "pending"
        assert updated["published_version"] == 1
        assert updated["has_unpublished_changes"] is True
        # 双轨核心：工作区改了，线上一个字都没变
        assert _live_content(client, key) == _rendered("# 第一版")
        # 编辑共享技能本身就把修订流置为 pending，重复提审会被 ``can_submit`` 拒绝
        # （作者改完直接等审批即可，那一步的点击已由本次 PUT 完成）。
        assert _send(client, "post", f"{BASE}/{key}/submit", {}).status_code == 403

        republished = _send(
            client, "post", f"{BASE}/{key}/review", {"decision": "approve", "acknowledged_firm_wide": True}
        ).json()
        assert republished["published_version"] == 2
        assert republished["has_unpublished_changes"] is False
        assert _live_content(client, key) == _rendered("# 第二版")

    def test_reject_keeps_published_revision(self) -> None:
        """驳回只改修订流：线上仍是已批准那一版（作者改错别字不该让全所失去指令）。"""
        _, client = _make_user("review-reject", is_admin=True)
        created = _create_firm_skill(client, body="# 第一版")
        key = created["key"]
        _send(client, "post", f"{BASE}/{key}/submit", {})
        _send(client, "post", f"{BASE}/{key}/review", {"decision": "approve", "acknowledged_firm_wide": True})
        _send(
            client,
            "put",
            f"{BASE}/{key}",
            {"title": "所内规范", "description": "全所统一使用", "body": "# 不该生效", "version": 1},
        )

        rejected = _send(client, "post", f"{BASE}/{key}/review", {"decision": "reject", "note": "措辞不合规"}).json()
        assert rejected["review_status"] == "rejected"
        assert rejected["review_note"] == "措辞不合规"
        assert rejected["status"] == "active"
        assert rejected["published_version"] == 1
        assert _live_content(client, key) == _rendered("# 第一版")

        stored = AgentSkill.objects.get(pk=key.removeprefix("skill:"))
        assert stored.status == AgentSkill.Status.ACTIVE
        assert stored.published_revision is not None
        assert stored.published_revision.version == 1

    def test_discard_draft_rolls_workspace_back_to_published(self) -> None:
        """放弃工作区：把线上已批准版回填，待审/驳回态一并清掉。"""
        _, client = _make_user("review-discard", is_admin=True)
        created = _create_firm_skill(client, body="# 第一版")
        key = created["key"]
        _send(client, "post", f"{BASE}/{key}/submit", {})
        _send(client, "post", f"{BASE}/{key}/review", {"decision": "approve", "acknowledged_firm_wide": True})
        _send(
            client,
            "put",
            f"{BASE}/{key}",
            {"title": "所内规范", "description": "全所统一使用", "body": "# 第二版", "version": 1},
        )

        discarded = _send(client, "post", f"{BASE}/{key}/discard-draft", {}).json()
        assert discarded["body"] == "# 第一版"
        assert discarded["version"] == 1
        assert discarded["review_status"] == "none"
        assert discarded["has_unpublished_changes"] is False
        assert _live_content(client, key) == _rendered("# 第一版")

    def test_archive_then_restore_requires_new_review(self) -> None:
        """下线立刻退出交付面；恢复回 ``draft``（恢复即生效等于绕过一次审批）。"""
        _, client = _make_user("review-archive", is_admin=True)
        created = _create_firm_skill(client, body="# 第一版")
        key = created["key"]
        _send(client, "post", f"{BASE}/{key}/submit", {})
        _send(client, "post", f"{BASE}/{key}/review", {"decision": "approve", "acknowledged_firm_wide": True})
        assert _live_content(client, key) == _rendered("# 第一版")

        archived = _send(client, "post", f"{BASE}/{key}/archive", {}).json()
        assert archived["status"] == "archived"
        assert _send(client, "get", f"{BASE}/resolve/{key}/content").status_code == 404

        restored = _send(client, "post", f"{BASE}/{key}/restore", {}).json()
        assert restored["status"] == "draft"
        assert _send(client, "get", f"{BASE}/resolve/{key}/content").status_code == 404


@pytest.mark.django_db
class TestDiff:
    def test_default_compares_published_with_workspace(self) -> None:
        _, client = _make_user("review-diff", is_admin=True)
        created = _create_firm_skill(client, body="# 第一版")
        key = created["key"]
        _send(client, "post", f"{BASE}/{key}/submit", {})
        _send(client, "post", f"{BASE}/{key}/review", {"decision": "approve", "acknowledged_firm_wide": True})
        _send(
            client,
            "put",
            f"{BASE}/{key}",
            {"title": "所内规范", "description": "全所统一使用", "body": "# 第二版", "version": 1},
        )

        diff = _send(client, "get", f"{BASE}/{key}/diff").json()
        assert diff["v1"] == 1
        assert diff["v2"] == 2
        assert [hunk["op"] for hunk in diff["hunks"]] == ["del", "ins"]
        assert diff["hunks"][0]["lines"] == ["# 第一版"]
        assert diff["hunks"][1]["lines"] == ["# 第二版"]

    def test_unknown_version_is_422(self) -> None:
        _, client = _make_user("review-diff-bad", is_admin=True)
        created = _create_firm_skill(client, body="# 第一版")
        assert _send(client, "get", f"{BASE}/{created['key']}/diff?v1=99").status_code == 422


@pytest.mark.django_db
class TestReviewPermissions:
    def _pending_firm_skill(self, client: Any) -> str:
        created = _create_firm_skill(client, body="# 第一版")
        _send(client, "post", f"{BASE}/{created['key']}/submit", {})
        return created["key"]

    def test_ordinary_lawyer_cannot_review(self) -> None:
        from django.test import Client

        admin, admin_client = _make_user("review-perm-author", is_admin=True)
        key = self._pending_firm_skill(admin_client)
        ordinary = Lawyer.objects.create_user(
            username="review-perm-ordinary", password=TEST_PASSWORD, law_firm=admin.law_firm
        )
        client = Client()
        client.force_login(ordinary)
        response = _send(client, "post", f"{BASE}/{key}/review", {"decision": "approve"})
        assert response.status_code == 403

    def test_other_firm_admin_cannot_review(self) -> None:
        _, admin_client = _make_user("review-perm-owner", is_admin=True)
        key = self._pending_firm_skill(admin_client)
        _, other_admin_client = _make_user("review-perm-outsider", is_admin=True)
        response = _send(
            other_admin_client, "post", f"{BASE}/{key}/review", {"decision": "approve", "acknowledged_firm_wide": True}
        )
        assert response.status_code == 403

    def test_reject_without_note_is_422(self) -> None:
        _, client = _make_user("review-perm-note", is_admin=True)
        key = self._pending_firm_skill(client)
        response = _send(client, "post", f"{BASE}/{key}/review", {"decision": "reject"})
        assert response.status_code == 422
        assert "note" in response.content.decode("utf-8", "ignore")

    def test_unknown_decision_is_422(self) -> None:
        _, client = _make_user("review-perm-decision", is_admin=True)
        key = self._pending_firm_skill(client)
        assert _send(client, "post", f"{BASE}/{key}/review", {"decision": "maybe"}).status_code == 422

    def test_approve_without_firm_wide_ack_is_422(self) -> None:
        """管理员自审自发要显式确认影响范围（生产有 0/1 名管理员的律所，不能靠双人）。"""
        _, client = _make_user("review-perm-ack", is_admin=True)
        key = self._pending_firm_skill(client)
        response = _send(client, "post", f"{BASE}/{key}/review", {"decision": "approve"})
        assert response.status_code == 422
        assert "acknowledged_firm_wide" in response.content.decode("utf-8", "ignore")
