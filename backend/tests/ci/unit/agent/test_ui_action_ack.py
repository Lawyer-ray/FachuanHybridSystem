"""UI 动作回执（``services/ui_action/ack.py``）的等待、幂等与积压语义。

为什么这些断言值得写：回执这条链路上每一种失效都**不会报错**，只会让模型看到
一个与事实相反的世界——

- ``resolve`` 不幂等 → 晚到的第二份结果覆盖第一份，模型看到一次从未发生的执行；
- 超时不进积压 → 律师慢一步，结果就永久消失，而模型以为自己「什么都没看见」；
- 积压上限/TTL 没有 → 一屏动作就能把进程内存吃满，或者把 10 分钟前的结果当成刚发生；
- ``ACK_WAIT=0`` 仍登记等待者 → 没人会去取那份结果，等待对象永不释放；
- 环境变量写错就抛 → 一个字符让整条通道消失。

全部用假总线 / 假缓存：这里要钉的是本模块的语义，不是 Redis 或 SSE 的实现。
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

import pytest

from apps.agent.services.ui_action import ack, publish_ui_action
from apps.agent.services.ui_action.manifest import UI_ACTIONS, UiAction

NAVIGATE: UiAction = next(action for action in UI_ACTIONS if action.name == "ui_navigate")


class _FakeCache:
    """最小假缓存：只实现 ``add`` / ``get`` / ``set``。

    ``add`` 的语义必须照真实缓存实现（键存在则返回 ``False`` 且不覆盖）——回执的
    幂等判据就架在「只有第一个写入者成功」上，假货放宽它就等于把那条断言变成假绿。
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

    def set(self, key: str, value: Any, timeout: int | None = None) -> None:
        self.store[key] = value


class _FakeBus:
    """只实现 ``publish_ui_action`` 真正调用的三个方法（口径同 ``test_ui_action_publish``）。"""

    def __init__(self, *, delivered: int = 1) -> None:
        self.delivered = delivered
        self.published: list[tuple[str, dict[str, Any]]] = []

    async def has_subscribers(self, session_id: str) -> bool:
        return True

    async def remote_subscriber_count(self, session_id: str) -> int:
        return 0

    async def publish(self, session_id: str, event: dict[str, Any]) -> int:
        self.published.append((session_id, event))
        return self.delivered


def _call_id() -> str:
    """每个用例独立的 call_id（等待器与积压都是进程级状态，共用 id 会让断言依赖执行顺序）。"""
    return uuid.uuid4().hex


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """清掉进程级积压与下发模式：本机 shell 里导出过开关就会让用例随环境变色。"""
    ack._PENDING.clear()
    monkeypatch.delenv("FACHUAN_UI_ACTION", raising=False)
    monkeypatch.delenv(ack.ACK_WAIT_ENV, raising=False)


@pytest.fixture
def no_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """没有共享缓存（开发环境 InMemoryCache 的等价物）：只剩进程内快路径。"""
    monkeypatch.setattr(ack, "redis_cache_enabled", lambda: False)


@pytest.fixture
def fake_cache(monkeypatch: pytest.MonkeyPatch) -> _FakeCache:
    """有共享缓存：跨 worker 的读写都落在这份假货上。"""
    cache = _FakeCache()
    monkeypatch.setattr(ack, "_cache", lambda: cache)
    monkeypatch.setattr(ack, "redis_cache_enabled", lambda: True)
    return cache


def _install_bus(monkeypatch: pytest.MonkeyPatch, bus: _FakeBus) -> _FakeBus:
    monkeypatch.setattr("apps.agent.services.event_bus.get_bus", lambda: bus)
    return bus


def _session_id() -> str:
    return f"ui-ack-{uuid.uuid4().hex}"


@pytest.mark.asyncio
async def test_resolve_wakes_local_waiter(no_cache: None) -> None:
    """① 同进程快路径：``resolve`` 必须把结果交回正在 ``wait`` 的调用方。"""
    call_id = _call_id()
    payload = {"outcome": "ok", "code": "", "detail": "", "location": "/projects"}
    await ack.register(call_id)

    waiting = asyncio.create_task(ack.wait(call_id, 2.0))
    # 不 sleep：``wait`` 进函数时先看 event 是否已 set，回执先到也不会漏。
    assert await ack.resolve(call_id, payload) is True
    assert await asyncio.wait_for(waiting, 0.5) == payload
    await ack.discard(call_id)


@pytest.mark.asyncio
async def test_wait_reads_ack_written_by_another_process(fake_cache: _FakeCache) -> None:
    """跨 worker：回执只落 Redis（不 set 本进程 event），``wait`` 靠周期轮询拿到它。

    这条正是 v1 判「回执不成立」的那个场景（派发在 MCP 进程、回执 POST 在 Django
    进程）。只做本地 event 的实现会在这里等到超时。
    """
    call_id = _call_id()
    payload = {"outcome": "error", "code": "route_unreachable", "detail": "已跳到 /projects", "location": ""}
    await ack.register(call_id)

    # 模拟另一个进程：只往缓存里写，本进程一无所知。
    fake_cache.store[f"{ack.ACK_KEY_PREFIX}{call_id}"] = json.dumps(payload, ensure_ascii=False)

    assert await ack.wait(call_id, 1.0) == payload
    await ack.discard(call_id)


@pytest.mark.asyncio
async def test_resolve_without_local_waiter_records_once(fake_cache: _FakeCache) -> None:
    """④ 幂等（跨进程侧）：没有等待者时回执写缓存，且同一 call_id 只认第一次。

    第二次返回 ``False`` 不是错误——前端重试就是会撞上这一条，端点据此回
    ``accepted=true / success=false``。
    """
    call_id = _call_id()
    first = {"outcome": "ok", "code": "", "detail": "", "location": "/projects"}
    second = {"outcome": "aborted", "code": "", "detail": "", "location": ""}

    assert await ack.resolve(call_id, first) is True
    assert await ack.resolve(call_id, second) is False

    stored = json.loads(fake_cache.store[f"{ack.ACK_KEY_PREFIX}{call_id}"])
    assert stored == first, "晚到的第二份回执不得覆盖第一次——否则模型看到一次从未发生的执行"


@pytest.mark.asyncio
async def test_resolve_second_submit_does_not_override_local_result(no_cache: None) -> None:
    """④ 幂等（同进程侧）：第二次 ``resolve`` 返回 ``False`` 且保留第一次的结果。"""
    call_id = _call_id()
    first = {"outcome": "ok", "code": "", "detail": "", "location": "/a"}
    second = {"outcome": "aborted", "code": "", "detail": "", "location": "/b"}
    await ack.register(call_id)

    assert await ack.resolve(call_id, first) is True
    assert await ack.resolve(call_id, second) is False
    # 走公开路径读结果：重复提交既不能抛，也不能把第一份改掉。
    assert await ack.wait(call_id, 0.1) == first
    await ack.discard(call_id)


@pytest.mark.asyncio
async def test_resolve_after_discard_reports_nobody_waiting(no_cache: None) -> None:
    """等待方已收工（discard）后再到的回执：``False``（告诉前端「本轮已按超时继续」）。"""
    call_id = _call_id()
    await ack.register(call_id)
    await ack.discard(call_id)

    assert await ack.resolve(call_id, {"outcome": "ok"}) is False


@pytest.mark.asyncio
async def test_timeout_goes_to_pending(monkeypatch: pytest.MonkeyPatch, no_cache: None) -> None:
    """② 等不到回执：返回 ``observed=false`` + ``pending=true``，并登记进积压表。

    积压项此刻只有 ``call_id`` / ``action``，``outcome`` 必须是 ``unknown``——
    页面没回执，模型据此不得断言成功。
    """
    _install_bus(monkeypatch, _FakeBus())
    monkeypatch.setenv(ack.ACK_WAIT_ENV, "0.05")
    session_id = _session_id()

    result = await publish_ui_action(action=NAVIGATE, arguments={"path": "/projects"}, session_id=session_id)

    assert result["status"] == "dispatched"
    assert result["observed"] is False
    assert result["pending"] is True
    assert "ui_action_results" in result["note"], "note 要点出取件工具的名字，模型才知道该搜什么"
    assert "不要断言" in result["note"]

    drained = ack.drain_pending(session_id)
    assert [item["call_id"] for item in drained] == [result["call_id"]]
    assert drained[0]["action"] == "ui_navigate"
    assert drained[0]["outcome"] == "unknown"


@pytest.mark.asyncio
async def test_observed_result_carries_outcome_and_location(
    monkeypatch: pytest.MonkeyPatch,
    no_cache: None,
) -> None:
    """快路径的下发形态：``observed=true`` 且字段直接来自回执（前端产物只换成模型口径的名字）。"""
    _install_bus(monkeypatch, _FakeBus())
    monkeypatch.setenv(ack.ACK_WAIT_ENV, "1")
    session_id = _session_id()

    async def _answer(call_id: str) -> None:
        await asyncio.sleep(0.01)
        await ack.resolve(call_id, {"outcome": "ok", "code": "", "detail": "", "location": "/projects"})

    original_publish = _FakeBus.publish

    async def _publish_then_answer(self: _FakeBus, session_id_: str, event: dict[str, Any]) -> int:
        asyncio.create_task(_answer(event["call_id"]))
        return await original_publish(self, session_id_, event)

    monkeypatch.setattr(_FakeBus, "publish", _publish_then_answer)

    result = await publish_ui_action(action=NAVIGATE, arguments={"path": "/projects"}, session_id=session_id)

    assert result["observed"] is True
    assert "pending" not in result
    assert result["outcome"] == "ok"
    assert result["location"] == "/projects"
    assert "code" not in result, "code 仅 error 时出现（冻结契约）"
    assert ack.drain_pending(session_id) == [], "拿到回执的动作不该进积压表"


@pytest.mark.asyncio
async def test_earlier_results_excludes_current_action(monkeypatch: pytest.MonkeyPatch, no_cache: None) -> None:
    """积压拼在 ``earlier_results``，且**不含当次动作**（drain 在 push 之前）。

    自己拼自己会让模型把「刚下发的这个」读成「上一次的结果」，进而在第二跳里
    基于一个还没有回执的动作做决定。
    """
    _install_bus(monkeypatch, _FakeBus())
    monkeypatch.setenv(ack.ACK_WAIT_ENV, "0.05")
    session_id = _session_id()

    first = await publish_ui_action(action=NAVIGATE, arguments={"path": "/a"}, session_id=session_id)
    second = await publish_ui_action(action=NAVIGATE, arguments={"path": "/b"}, session_id=session_id)

    assert "earlier_results" not in first, "第一次下发时没有任何积压"
    assert second["earlier_results"] == ["ui_navigate 结果未知（页面始终没有回执）"]
    # 积压表里只剩当次这一个：上一条被 drain 走了，当次这条也**没有**被自己拼进返回值。
    assert [item["call_id"] for item in ack.drain_pending(session_id)] == [second["call_id"]]


def test_pending_cap_keeps_newest_twenty(no_cache: None) -> None:
    """③ 上限 20 条且超限丢**最旧**：律师连点 30 下，模型会回头看的只有最近几个。"""
    session_id = _session_id()
    for index in range(ack.PENDING_CAP + 5):
        ack.push_pending(session_id, {"call_id": f"call-{index}", "action": "ui_navigate"})

    drained = ack.drain_pending(session_id)

    assert len(drained) == ack.PENDING_CAP
    assert [item["call_id"] for item in drained] == [f"call-{index}" for index in range(5, ack.PENDING_CAP + 5)]


def test_pending_ttl_drops_expired(no_cache: None) -> None:
    """③ TTL 60s：过期项取不到，也不该让会话字典无限长大。

    时间戳直接改成过去（而不是冻结 clock）：TTL 是「写入时刻 + 60s」的纯比较，
    改数据比 monkeypatch ``time.monotonic`` 小得多，也不会波及同进程的其他用例。
    """
    session_id = _session_id()
    ack.push_pending(session_id, {"call_id": _call_id(), "action": "ui_navigate"})
    ack._PENDING[session_id] = [
        (time.monotonic() - ack.PENDING_TTL - 1, ref) for _stamp, ref in ack._PENDING[session_id]
    ]

    assert ack.drain_pending(session_id) == []
    assert session_id not in ack._PENDING


@pytest.mark.asyncio
async def test_zero_ack_wait_goes_straight_to_pending(monkeypatch: pytest.MonkeyPatch, no_cache: None) -> None:
    """⑤ ``ACK_WAIT=0``：不等、也不登记等待者，直接走积压。

    登记了却没人取，等待对象会永久留在字典里（每次下发漏一个）——所以这里额外断言
    「此刻 resolve 找不到人」。
    """
    _install_bus(monkeypatch, _FakeBus())
    monkeypatch.setenv(ack.ACK_WAIT_ENV, "0")
    session_id = _session_id()

    started = time.monotonic()
    result = await publish_ui_action(action=NAVIGATE, arguments={"path": "/projects"}, session_id=session_id)
    elapsed = time.monotonic() - started

    assert elapsed < 0.5, f"ACK_WAIT=0 必须立刻返回，实测 {elapsed:.2f}s"
    assert result["observed"] is False
    assert result["pending"] is True
    assert "FACHUAN_UI_ACTION_ACK_WAIT=0" in result["note"]
    assert await ack.resolve(result["call_id"], {"outcome": "ok"}) is False
    assert [item["call_id"] for item in ack.drain_pending(session_id)] == [result["call_id"]]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.5", 1.5),
        ("0", 0.0),
        ("-1", 0.0),  # 负值夹到 0（「不等」），不是回默认——负数表达的就是「别等」
        ("99", ack.MAX_ACK_WAIT),  # 夹到硬上限：模型循环里不能无限等
    ],
)
def test_ack_wait_env_clamped(monkeypatch: pytest.MonkeyPatch, raw: str, expected: float) -> None:
    monkeypatch.setenv(ack.ACK_WAIT_ENV, raw)
    assert ack.ack_wait_seconds() == expected


@pytest.mark.parametrize("raw", ["abc", "nan", "inf", ""])
def test_invalid_ack_wait_env_falls_back_with_warning(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    raw: str,
) -> None:
    """⑥ 非法值回默认 + warning（``nan`` / ``inf`` 也算非法：它们会让 clamp 形同虚设）。"""
    monkeypatch.setenv(ack.ACK_WAIT_ENV, raw)
    caplog.set_level("WARNING", logger="apps.agent.services.ui_action.ack")

    assert ack.ack_wait_seconds() == ack.DEFAULT_ACK_WAIT
    if raw:
        assert any(ack.ACK_WAIT_ENV in record.getMessage() for record in caplog.records)
    else:
        assert caplog.records == [], "空值等同上「没配」，不该告警"


def test_ack_wait_default_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ack.ACK_WAIT_ENV, raising=False)
    assert ack.ack_wait_seconds() == ack.DEFAULT_ACK_WAIT == 2.0


def test_dispatch_session_roundtrip(fake_cache: _FakeCache) -> None:
    """归属映射：上行回执靠 ``call_id → session_id`` 认会话（回执没有数据库记录）。"""
    call_id = _call_id()
    ack.mark_dispatch_session(call_id, "session-1")

    assert ack.dispatch_session(call_id) == "session-1"
    assert ack.dispatch_session(_call_id()) is None
