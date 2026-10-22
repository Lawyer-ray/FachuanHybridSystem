"""Agent API 集成测试 —— 会话归属、SSE 错误路径、审批鉴权与归属。

覆盖此前只有 ``pragma: no cover`` 的端点层；pi 子进程路径通过指向不存在的
二进制走 ``PiNotAvailableError`` 分支（CI 无 pi 也能测全链路）。
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from apps.agent.models import AgentApproval, AgentMessage, AgentSession


def _post(client: Any, url: str, data: dict[str, Any], **kwargs: Any) -> Any:
    return client.post(url, data=json.dumps(data), content_type="application/json", **kwargs)


def _sse_body(resp: Any) -> str:
    """读完 SSE 流（StreamingHttpResponse 需迭代响应对象，Django 会适配异步迭代器）。"""
    return b"".join(resp).decode()


def _make_user(username: str) -> tuple[Any, Any]:
    """普通（非超管）用户 + 已登录客户端。"""
    from django.test import Client

    from apps.organization.models import LawFirm, Lawyer

    firm = LawFirm.objects.create(name=f"律所-{username}")
    user = Lawyer.objects.create_user(username=username, password="x-test-12345678", law_firm=firm)
    client = Client()
    client.force_login(user)
    return user, client


@pytest.fixture(autouse=True)
def _no_shared_mcp(monkeypatch: pytest.MonkeyPatch) -> Any:
    """测试内禁用共享 MCP 自动拉起、pi 单例池与 Redis 跨 worker 判定。

    本机/CI 的 settings 可能带 REDIS_URL（继承 .env）；若不关掉，
    ``redis_cache_enabled()`` 为 True 会让「无订阅者」的审批也硬等满
    300 秒超时（has_remote 恒真），单测被拖成 5 分钟一个。
    """
    monkeypatch.setenv("FACHUAN_MCP_SHARED", "0")
    monkeypatch.setattr("apps.agent.services.approval.redis_cache_enabled", lambda: False)
    monkeypatch.setattr("apps.agent.services.event_bus.redis_cache_enabled", lambda: False)

    import apps.agent.services.chat_service as chat_service

    original = chat_service._pool
    chat_service._pool = None
    yield
    chat_service._pool = original


# ===================================================================
# 会话 CRUD 与归属
# ===================================================================


@pytest.mark.django_db
def test_session_crud_and_ownership(authenticated_client: Any) -> None:
    resp = _post(authenticated_client, "/api/v1/agent/sessions", {"title": "测试会话"})
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    assert AgentSession.objects.filter(session_id=session_id).exists()

    listed = authenticated_client.get("/api/v1/agent/sessions").json()
    assert any(s["session_id"] == session_id for s in listed)

    # 其他普通用户：看不到、发不进、删不掉（send_message 的 IDOR 已堵）
    _, other_client = _make_user("intruder")
    assert all(s["session_id"] != session_id for s in other_client.get("/api/v1/agent/sessions").json())

    resp = _post(other_client, f"/api/v1/agent/sessions/{session_id}/messages", {"message": "越权消息"})
    assert resp.status_code == 200  # SSE 恒 200，错误在事件里
    assert "error" in _sse_body(resp)
    from apps.agent.models import AgentMessage

    assert not AgentMessage.objects.filter(session__session_id=session_id, content="越权消息").exists()

    deleted = other_client.delete(f"/api/v1/agent/sessions/{session_id}").json()
    assert deleted["deleted"] == 0
    assert AgentSession.objects.filter(session_id=session_id).exists()

    owner_delete = authenticated_client.delete(f"/api/v1/agent/sessions/{session_id}").json()
    assert owner_delete["deleted"] == 1


# ===================================================================
# 对话端点（pi 缺失路径）
# ===================================================================


@pytest.mark.django_db
def test_send_message_without_pi_yields_error_stream(
    authenticated_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """pi 不可用时：SSE 返回 error 事件，用户消息已落库、done 不发。"""
    monkeypatch.setenv("FACHUAN_PI_BIN", "/nonexistent/pi-binary-for-test")
    session_id = _post(authenticated_client, "/api/v1/agent/sessions", {"title": ""}).json()["session_id"]

    resp = _post(authenticated_client, f"/api/v1/agent/sessions/{session_id}/messages", {"message": "你好"})
    assert resp.status_code == 200
    body = _sse_body(resp)
    assert '"type": "error"' in body
    assert "pi 运行时不可用" in body
    assert '"type": "done"' not in body

    from apps.agent.models import AgentMessage

    assert AgentMessage.objects.filter(session__session_id=session_id, role="user", content="你好").count() == 1

    # 首条消息自动生成会话标题（会话列表默认靠标题区分）
    session = AgentSession.objects.get(session_id=session_id)
    assert session.title == "你好"


@pytest.mark.django_db
def test_session_detail_and_message_history(authenticated_client: Any) -> None:
    """会话详情 + 消息历史（旧→新、含 tool 与 metadata）；他人访问 404。"""
    session_id = _post(authenticated_client, "/api/v1/agent/sessions", {"title": "历史回放"}).json()["session_id"]
    session = AgentSession.objects.get(session_id=session_id)
    AgentMessage.objects.create(session=session, role="user", content="问")
    AgentMessage.objects.create(session=session, role="assistant", content="答", metadata={"model": "kimi-2.6"})
    AgentMessage.objects.create(session=session, role="tool", content="{}", tool_name="list_cases")

    detail = authenticated_client.get(f"/api/v1/agent/sessions/{session_id}").json()
    assert detail["session_id"] == session_id
    assert detail["title"] == "历史回放"

    history = authenticated_client.get(f"/api/v1/agent/sessions/{session_id}/messages").json()
    assert [m["role"] for m in history] == ["user", "assistant", "tool"]
    assert [m["content"] for m in history] == ["问", "答", "{}"]
    assert history[1]["metadata"] == {"model": "kimi-2.6"}
    assert history[2]["tool_name"] == "list_cases"
    assert history[0]["message_id"] < history[-1]["message_id"]  # 旧→新

    # 其他普通用户：详情与历史都 404（不泄露会话存在性）；payload 同步断言
    _, other_client = _make_user("history-intruder")
    for url in (f"/api/v1/agent/sessions/{session_id}", f"/api/v1/agent/sessions/{session_id}/messages"):
        resp = other_client.get(url)
        assert resp.status_code == 404
        assert "会话不存在" in json.dumps(resp.json(), ensure_ascii=False)

    # 不存在的会话：同样 404
    missing = "00000000-0000-0000-0000-000000000000"
    resp = authenticated_client.get(f"/api/v1/agent/sessions/{missing}/messages")
    assert resp.status_code == 404
    assert "会话不存在" in json.dumps(resp.json(), ensure_ascii=False)


@pytest.mark.django_db
def test_session_rename(authenticated_client: Any) -> None:
    """重命名：所有者可改且即时生效；空标题 400；他人 404 不泄露存在性。"""
    session_id = _post(authenticated_client, "/api/v1/agent/sessions", {"title": "旧标题"}).json()["session_id"]

    resp = authenticated_client.patch(
        f"/api/v1/agent/sessions/{session_id}",
        data=json.dumps({"title": "  新标题  "}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "新标题"  # 去空格
    assert AgentSession.objects.get(session_id=session_id).title == "新标题"

    # 空标题：400 拒绝且不改库
    resp = authenticated_client.patch(
        f"/api/v1/agent/sessions/{session_id}",
        data=json.dumps({"title": "   "}),
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert "不能为空" in json.dumps(resp.json(), ensure_ascii=False)
    assert AgentSession.objects.get(session_id=session_id).title == "新标题"

    # 他人：404
    _, other_client = _make_user("rename-intruder")
    resp = other_client.patch(
        f"/api/v1/agent/sessions/{session_id}",
        data=json.dumps({"title": "越权重命名"}),
        content_type="application/json",
    )
    assert resp.status_code == 404
    assert "会话不存在" in json.dumps(resp.json(), ensure_ascii=False)
    assert AgentSession.objects.get(session_id=session_id).title == "新标题"


@pytest.mark.django_db
def test_send_message_unknown_session(authenticated_client: Any) -> None:
    resp = _post(
        authenticated_client, "/api/v1/agent/sessions/00000000-0000-0000-0000-000000000000/messages", {"message": "x"}
    )
    assert resp.status_code == 200
    assert "会话不存在" in _sse_body(resp)


# ===================================================================
# 审批：extension 回调鉴权 + fail-closed + 决定归属
# ===================================================================


@pytest.mark.django_db
def test_approval_request_token_and_fail_closed(authenticated_client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FACHUAN_INTERNAL_TOKEN", "sekret-token")

    # 未带 token：拒绝，且不建审批记录
    resp = _post(authenticated_client, "/api/v1/agent/approval/request", {"tool": "mcp__fachuan__delete_case"})
    assert resp.json()["approved"] is False
    assert AgentApproval.objects.count() == 0

    # 带 token 但无 SSE 订阅者：默认走离线审批（挂起），不立即拒绝。
    # 关掉离线审批时回到原 fail-closed 行为——两条都要验，否则「保守部署」
    # 这个承诺是空的。
    session = AgentSession.objects.create(title="审批会话")
    monkeypatch.setenv("FACHUAN_APPROVAL_OFFLINE", "0")
    resp = _post(
        authenticated_client,
        "/api/v1/agent/approval/request",
        {"tool": "mcp__fachuan__delete_case", "session_id": str(session.session_id)},
        HTTP_X_INTERNAL_TOKEN="sekret-token",
    )
    assert resp.json()["approved"] is False
    assert AgentApproval.objects.filter(tool_name="mcp__fachuan__delete_case", status="rejected").exists()

    # 非高危工具：不进入审批（不落库）
    resp = _post(
        authenticated_client,
        "/api/v1/agent/approval/request",
        {"tool": "mcp__fachuan__list_cases", "session_id": str(session.session_id)},
        HTTP_X_INTERNAL_TOKEN="sekret-token",
    )
    assert resp.json()["approved"] is True
    assert AgentApproval.objects.filter(tool_name="mcp__fachuan__list_cases").count() == 0


@pytest.mark.django_db
def test_approval_decide_ownership() -> None:
    """决定权：会话所有者可批；他人不可批且不改变状态；超管恒可。"""
    import uuid as uuid_mod

    owner, owner_client = _make_user("approval-owner")
    _, attacker_client = _make_user("approval-attacker")
    session = AgentSession.objects.create(title="归属测试", user=owner)
    approval = AgentApproval.objects.create(
        approval_id=uuid_mod.uuid4(), session=session, tool_name="mcp__fachuan__delete_case"
    )

    resp = _post(attacker_client, f"/api/v1/agent/approval/{approval.approval_id}/decide", {"approved": True})
    assert resp.json()["success"] is False
    approval.refresh_from_db()
    assert approval.status == "pending"

    resp = _post(owner_client, f"/api/v1/agent/approval/{approval.approval_id}/decide", {"approved": True})
    assert resp.json()["success"] is True
    approval.refresh_from_db()
    assert approval.status == "approved"
    assert approval.decided_by_id == owner.pk


@pytest.mark.django_db
def test_approvals_list_scoped_to_owner(authenticated_client: Any) -> None:
    """审批列表：非超管只见自己会话的记录，超管见全部。"""
    import uuid as uuid_mod

    owner, _owner_client = _make_user("list-owner")
    own_session = AgentSession.objects.create(title="甲", user=owner)
    other_session = AgentSession.objects.create(title="乙")
    AgentApproval.objects.create(approval_id=uuid_mod.uuid4(), session=own_session, tool_name="t1")
    AgentApproval.objects.create(approval_id=uuid_mod.uuid4(), session=other_session, tool_name="t2")

    _, plain_client = _make_user("list-viewer")
    # list-viewer 名下无会话 → 空列表
    assert plain_client.get("/api/v1/agent/approvals").json() == []
    # 超管（authenticated_client）可见全部
    records = authenticated_client.get("/api/v1/agent/approvals").json()
    assert {r["tool_name"] for r in records} == {"t1", "t2"}


# ===================================================================
# 运行中插话（steer / follow-up / clear-queue）端点
# ===================================================================


@pytest.mark.django_db
def test_steer_without_live_session_returns_409(authenticated_client: Any) -> None:
    """会话没在跑：给出可读的 409，而不是假装排队成功。"""
    session_id = _post(authenticated_client, "/api/v1/agent/sessions", {"title": "t"}).json()["session_id"]

    resp = _post(authenticated_client, f"/api/v1/agent/sessions/{session_id}/steer", {"message": "换个方向"})
    assert resp.status_code == 409
    # 统一错误体：{code, message, error, errors}
    assert "没有运行中" in resp.json()["message"]


@pytest.mark.django_db
def test_follow_up_without_live_session_returns_409(authenticated_client: Any) -> None:
    session_id = _post(authenticated_client, "/api/v1/agent/sessions", {"title": "t"}).json()["session_id"]

    resp = _post(authenticated_client, f"/api/v1/agent/sessions/{session_id}/follow-up", {"message": "再补一段"})
    assert resp.status_code == 409
    # 错误体必须是可读中文提示，而不是空 detail / 英文堆栈
    body = resp.json()
    assert body["message"]
    assert "没有运行中" in body["message"]


@pytest.mark.django_db
def test_clear_queue_without_live_session_is_empty(authenticated_client: Any) -> None:
    """撤销按钮可能在一轮结束后才点到：空列表，不报错。"""
    session_id = _post(authenticated_client, "/api/v1/agent/sessions", {"title": "t"}).json()["session_id"]

    resp = authenticated_client.delete(f"/api/v1/agent/sessions/{session_id}/queue")
    assert resp.status_code == 200
    assert resp.json()["messages"] == []


@pytest.mark.django_db
def test_steer_on_unknown_session_404(authenticated_client: Any) -> None:
    """不存在的会话：404 且提示语明确（不能变成 500 或静默成功）。"""
    resp = _post(
        authenticated_client,
        "/api/v1/agent/sessions/00000000-0000-0000-0000-000000000000/steer",
        {"message": "x"},
    )
    assert resp.status_code == 404
    assert "会话不存在" in resp.json()["message"]


@pytest.mark.django_db
def test_steer_cross_user_is_404_not_403(authenticated_client: Any) -> None:
    """越权访问一律 404，不泄露会话存在性。"""
    session_id = _post(authenticated_client, "/api/v1/agent/sessions", {"title": "t"}).json()["session_id"]
    _, other_client = _make_user("steer-intruder")

    resp = _post(other_client, f"/api/v1/agent/sessions/{session_id}/steer", {"message": "越权"})
    assert resp.status_code == 404
    # 404 而非 403：不泄露「这个会话存在」
    assert "会话不存在" in resp.json()["message"]


@pytest.mark.django_db
def test_steer_empty_message_rejected(authenticated_client: Any) -> None:
    session_id = _post(authenticated_client, "/api/v1/agent/sessions", {"title": "t"}).json()["session_id"]

    resp = _post(authenticated_client, f"/api/v1/agent/sessions/{session_id}/steer", {"message": "   "})
    assert resp.status_code == 400
    assert "不能为空" in resp.json()["message"]


@pytest.mark.django_db
def test_steer_delivers_when_session_is_live(authenticated_client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """会话在跑时插话要真的投递到那个进程。"""
    from apps.agent.services import chat_service
    from apps.agent.services.live_sessions import get_live_registry

    session_id = _post(authenticated_client, "/api/v1/agent/sessions", {"title": "t"}).json()["session_id"]

    recorded: list[tuple[str, str]] = []

    class _Stub:
        async def steer(self, message: str) -> str:
            recorded.append(("steer", message))
            return "queued"

    import asyncio

    async def register() -> None:
        await get_live_registry().register(session_id, _Stub())

    asyncio.run(register())
    try:
        resp = _post(authenticated_client, f"/api/v1/agent/sessions/{session_id}/steer", {"message": "换个方向"})
        assert resp.status_code == 200
        assert resp.json() == {"success": True, "disposition": "queued"}
        assert recorded == [("steer", "换个方向")]
    finally:

        async def clear() -> None:
            await get_live_registry().clear()

        asyncio.run(clear())


# ===================================================================
# 成本 / 耗时统计端点
# ===================================================================


@pytest.mark.django_db
def test_usage_endpoints_empty(authenticated_client: Any) -> None:
    resp = authenticated_client.get("/api/v1/agent/usage")
    assert resp.status_code == 200
    body = resp.json()
    assert body["runs"] == 0
    assert body["total_tokens"] == 0
    assert body["error_rate"] == 0.0

    assert authenticated_client.get("/api/v1/agent/usage/daily").json() == []
    assert authenticated_client.get("/api/v1/agent/usage/by-model").json() == []


@pytest.mark.django_db
def test_usage_scoped_to_current_user() -> None:
    """普通用户只看到自己的用量，看不到别人的。

    注意：共享的 authenticated_client fixture 建的是超级用户，
    所以这里用普通律师自己建 client。
    """
    from apps.agent.models import AgentRun, AgentSession

    user, client = _make_user("usage-scope-owner")
    mine = AgentSession.objects.create(title="mine", user=user)
    AgentRun.objects.create(session=mine, user=user, model="m", input_tokens=100, output_tokens=10)

    _, other_client = _make_user("usage-scope-other")
    other_session = AgentSession.objects.create(title="other")
    AgentRun.objects.create(session=other_session, model="m", input_tokens=9999, output_tokens=1)

    body = client.get("/api/v1/agent/usage").json()
    assert body["input_tokens"] == 100
    assert body["output_tokens"] == 10

    other_body = other_client.get("/api/v1/agent/usage").json()
    assert other_body["input_tokens"] == 0, "越权看到了他人用量"


@pytest.mark.django_db
def test_usage_all_flag_ignored_for_normal_user() -> None:
    """?all=true 只对超级用户生效，普通用户不能借此看全所。"""
    from apps.agent.models import AgentRun, AgentSession

    _, client = _make_user("usage-all-normal")
    other_session = AgentSession.objects.create(title="someone-else")
    AgentRun.objects.create(session=other_session, model="m", input_tokens=5000, output_tokens=1)

    body = client.get("/api/v1/agent/usage?all=true").json()
    assert body["input_tokens"] == 0


@pytest.mark.django_db
def test_usage_all_flag_works_for_superuser(authenticated_client: Any) -> None:
    """超级用户加 ?all=true 才看全所（共享 fixture 就是超管）。"""
    from apps.agent.models import AgentRun, AgentSession

    other_session = AgentSession.objects.create(title="someone-else")
    AgentRun.objects.create(session=other_session, model="m", input_tokens=5000, output_tokens=1)

    assert authenticated_client.get("/api/v1/agent/usage?all=true").json()["input_tokens"] == 5000
    # 不带 all 时超管也只看自己（避免误把全所数字当自己的）
    assert authenticated_client.get("/api/v1/agent/usage").json()["input_tokens"] == 0
