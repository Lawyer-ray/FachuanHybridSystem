"""``GET /skills/resolve/{ref}/content`` —— 运行时正文出口（MCP ``get_agent_skill`` 的数据源）。

这条端点直接决定模型「打开技能时看到什么」，所以三件事必须钉死：

1. **只交付可交付的**：已停用 / 草稿 / 他人私有 → 404（这条出口给模型，不能像管理面
   那样把工作区草稿返出去）。
2. **三种 ref 都认**：``builtin:<name>`` / ``skill:<uuid>`` / 裸 ``name``——模型只知道
   名字，路径参数却常带 key。
3. **按字节分段且 UTF-8 安全**：单次上限 16000 字节；切在多字节字符中间时宁可少回
   几个字节（``next_start`` 跟着走），因为模型会把 U+FFFD 当正文照抄。
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from apps.agent.models import AgentSkill
from apps.agent.services.skills.constants import CONTENT_PAGE_BYTES
from apps.agent.services.skills.render import scope_preamble
from apps.organization.models import LawFirm, Lawyer

TEST_PASSWORD = "x-test-12345678"  # pragma: allowlist secret
BASE = "/api/v1/agent/skills"
CONTENT = f"{BASE}/resolve"


def _make_user(username: str) -> tuple[Lawyer, Any]:
    from django.test import Client

    firm = LawFirm.objects.create(name=f"技能正文所-{username}")
    user = Lawyer.objects.create_user(username=username, password=TEST_PASSWORD, law_firm=firm)
    client = Client()
    client.force_login(user)
    return user, client


def _send(client: Any, method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
    kwargs: dict[str, Any] = {"content_type": "application/json"}
    if payload is not None:
        kwargs["data"] = json.dumps(payload)
    return getattr(client, method)(url, **kwargs)


def _create(client: Any, *, name: str, body: str) -> dict:
    response = _send(
        client,
        "post",
        BASE,
        {"name": name, "title": "合同审查", "description": "审查合同时使用", "body": body},
    )
    assert response.status_code == 201, response.content.decode("utf-8", "ignore")
    return response.json()


def _content(client: Any, ref: str, query: str = "") -> Any:
    return _send(client, "get", f"{CONTENT}/{ref}/content{query}")


def _rendered(scope: str, body: str) -> str:
    """运行时正文的期望形状（来源声明 + 正文，无 frontmatter）。"""
    return f"{scope_preamble(scope)}\n\n{body.strip()}\n"


@pytest.mark.django_db
class TestRefResolution:
    def test_personal_by_key_and_bare_name(self) -> None:
        _, client = _make_user("skill-content-refs")
        detail = _create(client, name="my-contract-review", body="# 做法\n1. 看主体")
        expected = _rendered("lawyer", "# 做法\n1. 看主体")
        for ref in (detail["key"], "my-contract-review", detail["key"].removeprefix("skill:")):
            body = _content(client, ref).json()
            assert body["key"] == detail["key"]
            assert body["name"] == "my-contract-review"
            assert body["scope"] == "lawyer"
            assert body["version"] == 1
            assert body["content"] == expected
            assert body["total_bytes"] == len(expected.encode("utf-8"))
            assert body["truncated"] is False
            assert body["next_start"] is None

    def test_builtin_by_key_and_bare_name(self) -> None:
        """内置条目的字典刻意不带正文（带 mtime 缓存），正文必须从 SKILL.md 读。"""
        _, client = _make_user("skill-content-builtin")
        for ref in ("builtin:web-research", "web-research"):
            body = _content(client, ref).json()
            assert body["key"] == "builtin:web-research"
            assert body["scope"] == "builtin"
            assert body["version"] == 0
            assert body["content"].startswith(scope_preamble("builtin"))
            # 只有前言（D2 缺陷形态）说明正文没被读出来
            assert len(body["content"].strip()) > len(scope_preamble("builtin")) + 20
            assert "联网检索" in body["content"]


@pytest.mark.django_db
class TestNotDeliverable:
    def test_disabled_personal_is_404(self) -> None:
        _, client = _make_user("skill-content-disabled")
        detail = _create(client, name="off-one", body="# 做法")
        AgentSkill.objects.filter(pk=detail["key"].removeprefix("skill:")).update(enabled=False)
        assert _content(client, detail["key"]).status_code == 404

    def test_other_lawyers_private_skill_is_404(self) -> None:
        _, owner_client = _make_user("skill-content-owner")
        _, other_client = _make_user("skill-content-other")
        detail = _create(owner_client, name="secret-one", body="# 私有做法")
        assert _content(other_client, detail["key"]).status_code == 404
        assert _content(other_client, "secret-one").status_code == 404

    def test_unpublished_firm_skill_is_404(self) -> None:
        """共享技能没走审批 = 草稿：`resolve_for_user` 只认 ``published_revision``。"""
        user, client = _make_user("skill-content-draft")
        Lawyer.objects.filter(pk=user.pk).update(is_admin=True)
        response = _send(
            client,
            "post",
            BASE,
            {
                "name": "firm-draft",
                "title": "所内草稿",
                "description": "还没审批",
                "body": "# 未生效",
                "scope": "law_firm",
            },
        )
        assert response.status_code == 201, response.content.decode("utf-8", "ignore")
        assert _content(client, response.json()["key"]).status_code == 404


@pytest.mark.django_db
class TestPaging:
    def test_page_boundary_and_reassembly(self) -> None:
        """>16000 字节正文：首页截断、``next_start`` 正确，拼接后等于全文。"""
        _, client = _make_user("skill-content-paging")
        body = "A" * 20_000
        detail = _create(client, name="long-one", body=body)
        expected = _rendered("lawyer", body)
        total = len(expected.encode("utf-8"))

        first = _content(client, detail["key"]).json()
        assert first["total_bytes"] == total
        assert first["truncated"] is True
        assert first["start"] == 0
        assert first["next_start"] == CONTENT_PAGE_BYTES
        assert len(first["content"].encode("utf-8")) == CONTENT_PAGE_BYTES

        second = _content(client, detail["key"], f"?start={first['next_start']}").json()
        assert second["start"] == CONTENT_PAGE_BYTES
        assert second["truncated"] is False
        assert second["next_start"] is None
        assert first["content"] + second["content"] == expected

    @pytest.mark.parametrize("start", [-1, 10**7])
    def test_out_of_range_start_is_422(self, start: int) -> None:
        _, client = _make_user(f"skill-content-start-{start}")
        detail = _create(client, name="short-one", body="# 做法")
        assert _content(client, detail["key"], f"?start={start}").status_code == 422

    def test_utf8_never_split_mid_character(self) -> None:
        """中文 + emoji 正文按小步长逐字节续读：每段都能干净解码且拼回原文。"""
        _, client = _make_user("skill-content-utf8")
        body = "合同审查要点：先看主体资格，再看违约责任。" * 4 + "🚀✅" * 6
        detail = _create(client, name="utf8-one", body=body)
        expected = _rendered("lawyer", body)

        pages: list[str] = []
        start: int | None = 0
        for _guard in range(10_000):  # 防死循环：步长 7 字节，正文不到 1KB
            assert start is not None
            page = _content(client, detail["key"], f"?start={start}&limit=7").json()
            assert "\ufffd" not in page["content"], "分段切坏了多字节字符"
            pages.append(page["content"])
            start = page["next_start"]
            if start is None:
                break
        else:  # pragma: no cover - 只会在分页实现死循环时触发
            pytest.fail("分页没有结束")

        assert "".join(pages) == expected
