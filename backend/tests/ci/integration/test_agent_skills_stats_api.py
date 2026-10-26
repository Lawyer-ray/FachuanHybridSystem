"""技能 / 会话统计 / 手动压缩 API 集成测试。

pi 子进程路径全部 mock（CI 无 pi）；端点层只验证契约形状、鉴权与归属。
"""

from __future__ import annotations

import json
from typing import Any

import pytest


def _patch(client: Any, url: str, data: dict[str, Any]) -> Any:
    return client.patch(url, data=json.dumps(data), content_type="application/json")


def _make_user(username: str) -> tuple[Any, Any]:
    from django.test import Client

    from apps.organization.models import LawFirm, Lawyer

    firm = LawFirm.objects.create(name=f"律所-{username}")
    user = Lawyer.objects.create_user(
        username=username, password="x-test-12345678", law_firm=firm  # pragma: allowlist secret
    )
    client = Client()
    client.force_login(user)
    return user, client


def _make_session(user: Any) -> Any:
    from apps.agent.models import AgentSession

    return AgentSession.objects.create(user=user, origin="chat", title="技能测试会话")


# ===================================================================
# GET /skills 与 PATCH /skills/{name}
# ===================================================================


@pytest.mark.django_db
def test_skills_list_and_toggle() -> None:
    user, client = _make_user("skill-api-user")
    resp = client.get("/api/v1/agent/skills")
    assert resp.status_code == 200
    body = resp.json()
    names = [s["name"] for s in body["skills"]]
    assert "web-research" in names
    assert all({"name", "description", "enabled"} <= set(s.keys()) for s in body["skills"])

    resp = _patch(client, "/api/v1/agent/skills/web-research", {"enabled": False})
    assert resp.status_code == 200
    assert resp.json() == {"name": "web-research", "enabled": False}

    # 再查清单：该技能已停用（下一轮对话不再注入）
    body = client.get("/api/v1/agent/skills").json()
    web = next(s for s in body["skills"] if s["name"] == "web-research")
    assert web["enabled"] is False


@pytest.mark.django_db
def test_skills_toggle_rejects_unknown_and_illegal() -> None:
    _, client = _make_user("skill-api-bad")
    assert _patch(client, "/api/v1/agent/skills/no-such-skill", {"enabled": True}).status_code == 404
    # 路径穿越形态在路由层就 404（URL 段含斜杠），不含斜杠的非法名走 service 校验
    assert _patch(client, "/api/v1/agent/skills/Bad_Name", {"enabled": True}).status_code == 404


@pytest.mark.django_db
def test_skills_require_auth(api_client: Any) -> None:
    r = api_client.get("/api/v1/agent/skills")
    assert r.status_code in (401, 403)
    # 未鉴权不能泄露技能清单（技能名本身会暴露内部能力面）
    assert "skills" not in r.content.decode("utf-8", "ignore")


# ===================================================================
# GET /sessions/{id}/stats
# ===================================================================


@pytest.mark.django_db
def test_stats_from_latest_run() -> None:
    from apps.agent.models import AgentRun

    user, client = _make_user("stats-user")
    session = _make_session(user)
    AgentRun.objects.create(
        session=session, output_tokens=10, input_tokens=5, tool_calls=1, duration_ms=100
    )
    AgentRun.objects.create(
        session=session,
        output_tokens=20,
        input_tokens=8,
        cache_read_tokens=100,
        tool_calls=2,
        duration_ms=200,
        context_used_tokens=65536,
        context_total_tokens=131072,
    )
    resp = client.get(f"/api/v1/agent/sessions/{session.session_id}/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["output_tokens"] == 20  # 最新一条
    assert body["cache_read_tokens"] == 100
    assert body["context_used_tokens"] == 65536
    assert body["context_percent"] == 50.0


@pytest.mark.django_db
def test_stats_no_runs_is_zero_watermark_null() -> None:
    user, client = _make_user("stats-empty-user")
    session = _make_session(user)
    body = client.get(f"/api/v1/agent/sessions/{session.session_id}/stats").json()
    assert body["output_tokens"] == 0
    assert body["context_used_tokens"] is None
    assert body["context_percent"] is None


@pytest.mark.django_db
def test_stats_session_ownership() -> None:
    owner, _ = _make_user("stats-owner")
    other, other_client = _make_user("stats-other")
    session = _make_session(owner)
    r = other_client.get(f"/api/v1/agent/sessions/{session.session_id}/stats")
    assert r.status_code == 404
    # 别人的会话按「不存在」处理，响应里不能带出 token 用量等实际情况
    assert "output_tokens" not in r.content.decode("utf-8", "ignore")


# ===================================================================
# POST /sessions/{id}/compact
# ===================================================================


@pytest.mark.django_db
def test_compact_success_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.agent.services import compact_service as svc

    user, client = _make_user("compact-user")
    session = _make_session(user)

    async def fake_compact(*, session: Any, user_id: int | None) -> dict[str, Any]:
        return {"compacted": True, "context_used_tokens": 8192, "context_total_tokens": 131072}

    monkeypatch.setattr(svc, "compact_session", fake_compact)
    resp = client.post(f"/api/v1/agent/sessions/{session.session_id}/compact")
    assert resp.status_code == 200
    assert resp.json() == {"compacted": True, "context_used_tokens": 8192, "context_total_tokens": 131072}


@pytest.mark.django_db
def test_compact_no_history_is_idempotent_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """没历史可压不算错：compacted=False 让前端平静提示，而不是弹错误。"""
    from apps.agent.services import compact_service as svc

    user, client = _make_user("compact-empty-user")
    session = _make_session(user)
    monkeypatch.setattr(svc, "has_pi_session", lambda session_id: False)
    resp = client.post(f"/api/v1/agent/sessions/{session.session_id}/compact")
    assert resp.status_code == 200
    assert resp.json()["compacted"] is False


@pytest.mark.django_db
def test_compact_busy_maps_to_429(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.agent.services import compact_service as svc
    from apps.agent.services.compact_service import CompactBusyError

    user, client = _make_user("compact-busy-user")
    session = _make_session(user)

    async def fake_compact(*, session: Any, user_id: int | None) -> dict[str, Any]:
        raise CompactBusyError("当前使用人数较多，请稍后再试")

    monkeypatch.setattr(svc, "compact_session", fake_compact)
    resp = client.post(f"/api/v1/agent/sessions/{session.session_id}/compact")
    assert resp.status_code == 429
    # 429 必须带上可读原因：只给状态码，前端只能显示「出错了」
    body = resp.content.decode("utf-8", "ignore")
    assert "较多" in body or "稍后" in body


@pytest.mark.django_db
def test_compact_requires_auth_and_ownership(api_client: Any) -> None:
    assert api_client.post("/api/v1/agent/sessions/whatever/compact").status_code in (401, 403)
    owner, _ = _make_user("compact-owner")
    other, other_client = _make_user("compact-other")
    session = _make_session(owner)
    assert other_client.post(f"/api/v1/agent/sessions/{session.session_id}/compact").status_code == 404
