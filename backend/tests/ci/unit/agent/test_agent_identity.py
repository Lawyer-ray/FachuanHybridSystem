"""Agent 按用户身份执行 —— 凭证铸造、env/mcp.json 配线、取消落库。

confused deputy 修复的分层验证：apps/agent 侧（铸 token → pi env → mcp.json
header 引用 → 取消路径保住部分回答）；mcp_server 侧的透传在
``tests/ci/unit/mcp_server/``。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from apps.agent.models import AgentMessage, AgentSession
from apps.agent.pi.user_token import USER_TOKEN_ENV, mint_user_access_token
from apps.agent.services import chat_service


def _make_lawyer(username: str) -> Any:
    """普通激活律师（同步调用需自行包 sync_to_async）。"""
    from apps.organization.models import LawFirm, Lawyer

    firm = LawFirm.objects.create(name=f"律所-{username}")
    return Lawyer.objects.create_user(  # pragma: allowlist secret
        username=username,
        password="x-test-12345678",  # pragma: allowlist secret
        law_firm=firm,
    )


# ===================================================================
# 凭证铸造
# ===================================================================


@pytest.mark.django_db
def test_mint_token_carries_user_identity() -> None:
    user = _make_lawyer("agent-token-user")
    token = mint_user_access_token(user.pk)

    from ninja_jwt.tokens import AccessToken

    claims = AccessToken(token).payload
    assert claims["user_id"] == user.pk
    # 无状态 access：不带 refresh 才有的 pwd_ver（改密失效只作用于 refresh）
    assert "pwd_ver" not in claims


@pytest.mark.django_db
def test_mint_rejects_inactive_user() -> None:
    user = _make_lawyer("agent-token-inactive")
    user.is_active = False
    user.save()
    with pytest.raises(ValueError):
        mint_user_access_token(user.pk)


@pytest.mark.django_db
def test_mint_missing_user_raises() -> None:
    with pytest.raises(Exception):
        mint_user_access_token(10**9)


# ===================================================================
# env / mcp.json 配线
# ===================================================================


def test_session_env_carries_user_token() -> None:
    session = AgentSession(title="t")
    env = chat_service._session_env(session, 7, user_token="tok-123")
    assert env["FACHUAN_USER_TOKEN"] == "tok-123"
    assert env["FACHUAN_SESSION_ID"] == str(session.session_id)
    assert env["FACHUAN_USER_ID"] == "7"


def test_session_env_writes_empty_token_when_absent() -> None:
    """无 token 也要写空串：pi 的 ${VAR} 展开得到空值而非字面量，mcp 侧据此回退。"""
    env = chat_service._session_env(None, None)
    assert env[USER_TOKEN_ENV] == ""


@pytest.mark.django_db
def test_write_pi_config_carries_token_header(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
    """共享 MCP 模式的 mcp.json 必须以 env 引用携带律师身份头。"""
    from apps.agent.pi.shared_mcp import write_pi_config

    monkeypatch.delenv("FACHUAN_MCP_SHARED", raising=False)
    config_path = write_pi_config(tmp_path)  # type: ignore[arg-type]
    server = json.loads(config_path.read_text(encoding="utf-8"))["mcpServers"]["fachuan"]
    assert server["type"] == "streamable-http"
    assert server["headers"] == {"Authorization": f"Bearer ${{{USER_TOKEN_ENV}}}"}


def test_write_pi_mcp_config_stdio_has_no_header(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.agent.pi.shared_mcp import write_pi_mcp_config

    monkeypatch.setenv("FACHUAN_MCP_SHARED", "0")
    config_path = write_pi_mcp_config(tmp_path)  # type: ignore[arg-type]
    server = json.loads(config_path.read_text(encoding="utf-8"))["mcpServers"]["fachuan"]
    assert "headers" not in server
    assert server["command"]


# ===================================================================
# stream_chat：取消保文本 / 铸凭证失败 fail-closed / 标题与模型回写
# ===================================================================


class _FakePiSession:
    async def prompt(self, message: str) -> None:
        return None


class _FakeAcquire:
    async def __aenter__(self) -> _FakePiSession:
        return _FakePiSession()

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


class _FakePool:
    def acquire(self, **kwargs: Any) -> _FakeAcquire:
        return _FakeAcquire()


@pytest.fixture()
def _fake_runtime(monkeypatch: pytest.MonkeyPatch) -> asyncio.Event:
    """替掉 pi 进程/模型解析/Redis 中继，stream_chat 只剩编排逻辑可测。"""
    from apps.agent.services.event_bus import EventBus

    release = asyncio.Event()

    async def fake_stream(pi_session: Any, *, agent: str = "pi") -> Any:
        yield {"type": "delta", "content": "第一段"}
        await release.wait()
        yield {"type": "done"}

    async def fake_get_pool() -> Any:
        return _FakePool()

    async def fake_model() -> str | None:
        return None

    monkeypatch.setattr(chat_service, "get_pool", fake_get_pool)
    monkeypatch.setattr(chat_service, "_resolve_model", fake_model)
    monkeypatch.setattr(chat_service, "stream_events", fake_stream)
    monkeypatch.setattr(EventBus, "_ensure_relay", lambda self: None)
    return release


def _make_session_sync() -> AgentSession:
    return AgentSession.objects.create(title="")


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_cancel_persists_partial_assistant_text(_fake_runtime: asyncio.Event) -> None:
    """客户端中途断开：已流出的部分回答要落库并标 truncated（此前会整段丢失）。

    async 测试里的 ORM 写经 asgiref 执行器线程的独立连接提交，逃出
    pytest-django 的事务包裹——用 transaction=True 以真实提交语义断言。
    """
    from asgiref.sync import sync_to_async

    user = await sync_to_async(_make_lawyer)("agent-cancel-user")
    session = await sync_to_async(_make_session_sync)()
    release: asyncio.Event = _fake_runtime

    agen = chat_service.stream_chat(session=session, user_message="问题", user_id=user.pk)
    it = agen.__aiter__()
    types: list[str] = []
    for _ in range(3):  # meta / activity / delta
        types.append((await it.__anext__())["type"])
    assert "delta" in types

    await agen.aclose()  # 模拟前端停止：生成器收到 GeneratorExit
    release.set()  # 放行 fake stream 的挂起分支，让 pending task 收尾

    msg = None
    deadline = asyncio.get_running_loop().time() + 5.0
    while asyncio.get_running_loop().time() < deadline:
        msg = await AgentMessage.objects.filter(session=session, role="assistant").afirst()
        if msg is not None:
            break
        await asyncio.sleep(0.05)
    assert msg is not None, "取消路径未落库助手文本"
    assert msg.content == "第一段"
    assert msg.metadata.get("truncated") is True


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_happy_path_records_title_and_persists_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """正常跑完：标题自动生成、llm_model 回写实际模型、回答不带 truncated。"""
    from asgiref.sync import sync_to_async

    user = await sync_to_async(_make_lawyer)("agent-happy-user")
    session = await sync_to_async(_make_session_sync)()

    async def fake_stream(pi_session: Any, *, agent: str = "pi") -> Any:
        yield {"type": "delta", "content": "完整回答"}
        yield {"type": "done"}

    async def fake_model() -> str | None:
        return "kimi-2.6"

    async def fake_get_pool() -> Any:
        return _FakePool()

    monkeypatch.setattr(chat_service, "get_pool", fake_get_pool)
    monkeypatch.setattr(chat_service, "_resolve_model", fake_model)
    monkeypatch.setattr(chat_service, "stream_events", fake_stream)
    from apps.agent.services.event_bus import EventBus

    monkeypatch.setattr(EventBus, "_ensure_relay", lambda self: None)

    events = [
        e["type"] async for e in chat_service.stream_chat(session=session, user_message="查一下案件", user_id=user.pk)
    ]
    assert events[-1] == "done"

    await sync_to_async(session.refresh_from_db)()
    assert session.title == "查一下案件"
    assert session.llm_model == "kimi-2.6"

    msg = await AgentMessage.objects.filter(session=session, role="assistant").afirst()
    assert msg is not None
    assert msg.content == "完整回答"
    assert "truncated" not in (msg.metadata or {})


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_auto_title_strips_anchor_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    """自动标题剥离前端注入的锚点行——否则列表标题全是「[当前业务：…]」。"""
    from asgiref.sync import sync_to_async

    user = await sync_to_async(_make_lawyer)("agent-title-anchor-user")
    session = await sync_to_async(_make_session_sync)()

    async def fake_stream(pi_session: Any, *, agent: str = "pi") -> Any:
        yield {"type": "delta", "content": "回答"}
        yield {"type": "done"}

    async def fake_get_pool() -> Any:
        return _FakePool()

    monkeypatch.setattr(chat_service, "get_pool", fake_get_pool)
    monkeypatch.setattr(chat_service, "stream_events", fake_stream)
    from apps.agent.services.event_bus import EventBus

    monkeypatch.setattr(EventBus, "_ensure_relay", lambda self: None)

    anchored = "[当前业务：本委托「某公司」 contract_id=8]\n梳理一下本案材料要点"
    events = [
        e["type"] async for e in chat_service.stream_chat(session=session, user_message=anchored, user_id=user.pk)
    ]
    assert events[-1] == "done"
    await session.arefresh_from_db()
    assert session.title == "梳理一下本案材料要点"


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_mint_failure_rejects_turn_without_persisting(monkeypatch: pytest.MonkeyPatch) -> None:
    """铸不出用户凭证：整轮拒绝，用户消息也不落库（不退回超管服务账号）。"""
    from asgiref.sync import sync_to_async

    session = await sync_to_async(_make_session_sync)()

    def boom(user_id: int) -> str:
        raise RuntimeError("user gone")

    monkeypatch.setattr(chat_service, "mint_user_access_token", boom)

    events = [e async for e in chat_service.stream_chat(session=session, user_message="问题", user_id=1)]
    assert [e["type"] for e in events] == ["error"]
    assert "凭证" in events[0]["message"]
    assert await AgentMessage.objects.filter(session=session).acount() == 0
