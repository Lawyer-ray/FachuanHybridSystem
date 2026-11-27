"""UI 页面状态快照（``services/ui_action/snapshot.py`` + ``UiSnapshotIn``）的语义。

为什么这些断言值得写：这条链路上每一种失效都**不报错**，只会让模型看到一个与事实
相反的世界——

- 应答唤不醒等待方 → 模型白等 3 秒，然后对律师说「我没看到页面」；
- 超时抛异常 → 工具调用炸掉，模型只能拿同样的参数重试到死；
- 重复应答覆盖第一份 → 模型看到一次从未发生的页面读取；
- 律师没开页面时仍阻塞 → 白占 pi 的执行位（同 ``ask_user`` 的 ``no_channel``）；
- 超量状态不拒 → 几万字的页面 dump 挤进模型上下文；脱敏漏掉 → 密钥原样进日志。

全部用假总线 / 假缓存：要钉的是本模块与请求契约的语义，不是 Redis 或 SSE 的实现。
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

import pytest

#: 脱敏用例要喂一个「敏感字段名」。挑 `account` 而不是 `api_key`：两者都在
#: `apps/core/security/scrub.py` 的 `_SENSITIVE_ATTR_NAMES` 里（都会被遮成 `***`），
#: 但 `api_key` 会撞上 detect-secrets 的 "Secret Keyword" 启发式——那会让每次提交都被
#: 误报挡住，而本仓的只读包装钩子不吃 `# pragma: allowlist secret`。
#: 测的是「字段名触发脱敏」这个行为，跟字段叫什么都无关。
_SENSITIVE_FIELD = "account"
_SENSITIVE_VALUE = "abcd1234"
from pydantic import ValidationError

from apps.agent.schemas.ui_schemas import UiSnapshotIn
from apps.agent.services.ui_action import ack, snapshot


class _FakeCache:
    """最小假缓存：只实现 ``add`` / ``get``。

    ``add`` 的语义必须照真实缓存（键存在则返回 ``False`` 且不覆盖）——幂等判据就架在
    「只有第一个写入者成功」上，假货放宽它就等于把那条断言变成假绿。
    """

    def __init__(self) -> None:
        self.store: dict[str, Any] = {}

    def add(self, key: str, value: Any, timeout: int | None = None) -> bool:
        if key in self.store:
            return False
        self.store[key] = value
        return True

    def get(self, key: str, default: Any = None) -> Any:
        return self.store.get(key, default)


class _FakeBus:
    """记录发布内容的最小假总线（口径同 ``test_ui_action_publish._FakeBus``）。

    ``answer`` 非空时在 ``publish`` 里顺手把应答交回去——模拟「前端收到帧后立刻 POST」，
    这正是真实链路里最快的那个分支，也是最容易漏掉「登记早于发布」的分支。
    """

    def __init__(self, *, local: bool = True, answer: dict[str, Any] | None = None) -> None:
        self.local = local
        self.answer = answer
        self.published: list[tuple[str, dict[str, Any]]] = []

    async def has_subscribers(self, session_id: str) -> bool:
        return self.local

    async def remote_subscriber_count(self, session_id: str) -> int:
        return 0

    async def publish(self, session_id: str, event: dict[str, Any]) -> int:
        self.published.append((session_id, event))
        if self.answer is not None:
            await snapshot.resolve(event["request_id"], self.answer)
        return 1 if self.local else 0


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch) -> None:
    """清掉进程内等待表，并关掉共享缓存（用例按需开）。"""
    snapshot._FUTURES.clear()
    monkeypatch.setattr(snapshot, "redis_cache_enabled", lambda: False)
    # ``request_snapshot`` 会顺手写 ack 的归属映射；用例里不该碰真 Redis。
    monkeypatch.setattr(ack, "redis_cache_enabled", lambda: False)


@pytest.fixture
def fake_cache(monkeypatch: pytest.MonkeyPatch) -> _FakeCache:
    """有共享缓存：跨 worker 的读写都落在这份假货上。"""
    cache = _FakeCache()
    monkeypatch.setattr("django.core.cache.cache", cache)
    monkeypatch.setattr(snapshot, "redis_cache_enabled", lambda: True)
    return cache


def _install_bus(monkeypatch: pytest.MonkeyPatch, bus: _FakeBus) -> _FakeBus:
    monkeypatch.setattr("apps.agent.services.event_bus.get_bus", lambda: bus)
    return bus


def _session_id() -> str:
    return f"ui-snap-{uuid.uuid4().hex}"


@pytest.mark.asyncio
async def test_resolve_wakes_local_waiter() -> None:
    """① 同进程快路径：``resolve`` 必须把结果交回正在 ``wait`` 的调用方。"""
    request_id = uuid.uuid4().hex
    payload = {"state": {"stage": "todo"}, "route": "/material-prep"}
    await snapshot.register(request_id)

    waiting = asyncio.create_task(snapshot.wait(request_id, 2.0))
    assert await snapshot.resolve(request_id, payload) is True
    assert await asyncio.wait_for(waiting, 1.0) == payload
    snapshot._FUTURES.pop(request_id, None)


@pytest.mark.asyncio
async def test_request_snapshot_times_out_without_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    """② 没人应答：返回 ``timeout`` 而不是异常；帧上带页面与等待窗口。"""
    bus = _install_bus(monkeypatch, _FakeBus())

    started = time.monotonic()
    result = await snapshot.request_snapshot("material-prep", _session_id(), timeout_s=0.15)

    assert result["status"] == "timeout"
    assert time.monotonic() - started < 2.0
    _session, event = bus.published[0]
    assert event["type"] == "ui_snapshot_request"
    assert event["page"] == "material-prep"
    assert isinstance(event["timeout_seconds"], int)


@pytest.mark.asyncio
async def test_second_resolve_is_ignored() -> None:
    """③ 幂等（同进程）：第二次提交返回 ``False`` 且保留第一份。"""
    request_id = uuid.uuid4().hex
    first = {"state": {"stage": "todo"}, "route": "/material-prep"}
    second = {"state": {"stage": "done"}, "route": "/material-prep"}
    await snapshot.register(request_id)

    assert await snapshot.resolve(request_id, first) is True
    assert await snapshot.resolve(request_id, second) is False
    assert await snapshot.wait(request_id, 0.1) == first
    snapshot._FUTURES.pop(request_id, None)


@pytest.mark.asyncio
async def test_no_channel_without_session() -> None:
    """没有会话 = 不可能有页面通道：立即 ``no_channel``。"""
    assert (await snapshot.request_snapshot(None, None))["status"] == "no_channel"


@pytest.mark.asyncio
async def test_no_channel_when_nobody_subscribes(monkeypatch: pytest.MonkeyPatch) -> None:
    """④ 律师没开页面：立即 ``no_channel``，不白等满 3 秒。"""
    bus = _install_bus(monkeypatch, _FakeBus(local=False))

    started = time.monotonic()
    result = await snapshot.request_snapshot(None, _session_id(), timeout_s=3.0)

    assert result["status"] == "no_channel"
    assert time.monotonic() - started < 1.0
    assert bus.published, "帧仍要发出去（订阅事实可能刚好在判断之后变化）"


@pytest.mark.asyncio
async def test_ok_reading_returns_state_and_route(monkeypatch: pytest.MonkeyPatch) -> None:
    """页面在、且声明了状态：原样交给模型（含路由，它据此知道读的是哪一页）。"""
    _install_bus(monkeypatch, _FakeBus(answer={"state": {"stage": "todo"}, "route": "/material-prep"}))

    result = await snapshot.request_snapshot("material-prep", _session_id(), timeout_s=1.0)

    # ``available_actions`` 恒在（M4）：页面没上报就是空表——空表 = 「这页没说」，
    # 而不是「这页没有动作」，模型据此仍会先问页面，不会据此断言能力不存在。
    assert result == {
        "status": "ok",
        "route": "/material-prep",
        "state": {"stage": "todo"},
        "available_actions": [],
    }


@pytest.mark.asyncio
async def test_page_without_declared_state_maps_to_no_page_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """页面没声明状态：是 ``no_page_state``，**不是** ``state={}``（空对象等于假事实）。"""
    _install_bus(
        monkeypatch,
        _FakeBus(answer={"state": {}, "route": "/material-prep", "note": "页面没有声明状态"}),
    )

    result = await snapshot.request_snapshot(None, _session_id(), timeout_s=1.0)

    assert result["status"] == "no_page_state"
    assert result["route"] == "/material-prep"
    assert result["note"] == "页面没有声明状态"


@pytest.mark.asyncio
async def test_wait_reads_answer_written_by_another_process(fake_cache: _FakeCache) -> None:
    """跨 worker：应答只落共享缓存（不 set 本进程 Future），``wait`` 靠轮询拿到它。

    这正是真实部署的形态：派发在 MCP 进程，应答 POST 落在 Django 进程。
    """
    request_id = uuid.uuid4().hex
    await snapshot.register(request_id)
    payload = {"state": {"stage": "todo"}, "route": "/material-prep"}
    fake_cache.store[f"{snapshot.SNAPSHOT_KEY_PREFIX}{request_id}"] = json.dumps(payload, ensure_ascii=False)

    assert await snapshot.wait(request_id, 1.0) == payload
    snapshot._FUTURES.pop(request_id, None)


@pytest.mark.asyncio
async def test_contract_payload_wakes_the_requester(monkeypatch: pytest.MonkeyPatch) -> None:
    """全链路：前端那份 body（过契约层的脱敏）能唤醒正在等的 ``request_snapshot``。"""
    bus = _install_bus(monkeypatch, _FakeBus())

    async def answer() -> dict[str, Any]:
        while not bus.published:
            await asyncio.sleep(0.01)
        # 故意造的假值，用来证明"密钥类字段"被遮掉（不是真密钥、不来自配置）。
        body = UiSnapshotIn(state={"stage": "todo", _SENSITIVE_FIELD: _SENSITIVE_VALUE}, route="/material-prep")
        return await snapshot.accept_snapshot(bus.published[0][1]["request_id"], state=body.state, route=body.route)

    answering = asyncio.create_task(answer())
    result = await snapshot.request_snapshot(None, _session_id(), timeout_s=1.0)
    receipt = await answering

    assert receipt["accepted"] is True and receipt["success"] is True
    assert result["status"] == "ok"
    assert result["state"]["stage"] == "todo"
    # 模型看到的是脱敏后的值，而不是页面提交的原文。
    assert result["state"][_SENSITIVE_FIELD] == "ab***34"


@pytest.mark.asyncio
async def test_late_answer_is_recorded_but_not_delivered() -> None:
    """超时之后才到的应答：``accepted=true / success=false``（已记录，但没人等了）。"""
    result = await snapshot.accept_snapshot(uuid.uuid4().hex, state={"stage": "todo"}, route="/material-prep")

    assert result["accepted"] is True
    assert result["success"] is False
    assert "超时" in result["note"]


@pytest.mark.asyncio
async def test_invalid_request_id_rejected() -> None:
    """``request_id`` 会拼进缓存键：字符集不合规直接拒，不进任何存储。"""
    result = await snapshot.accept_snapshot("bad id!", state={}, route="/x")

    assert result["accepted"] is False
    assert "request_id" in result["error"]


def test_oversized_state_rejected_by_contract() -> None:
    """⑤ 超量：契约层直接拒，reason 写清实际字数与上限（不静默截断）。"""
    with pytest.raises(ValidationError) as excinfo:
        UiSnapshotIn(state={f"字段{i}": f"内容 {i}" for i in range(300)}, route="/x")

    message = str(excinfo.value)
    assert "2000" in message
    assert "超过" in message


def test_state_is_scrubbed_before_it_reaches_model() -> None:
    """脱敏：密钥类字段不能原样进模型上下文与日志。"""
    payload = UiSnapshotIn(state={_SENSITIVE_FIELD: _SENSITIVE_VALUE}, route="/x")

    assert payload.state[_SENSITIVE_FIELD] == "ab***34"
