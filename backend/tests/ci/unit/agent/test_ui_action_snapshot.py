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
from types import SimpleNamespace
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

    # ``available_actions`` / ``blocked_actions`` 恒在：页面没上报就是空表——空表 = 「这页没说」，
    # 而不是「这页没有动作」/「这页什么都做得了」，模型据此仍会先问页面，不会据此断言能力。
    assert result == {
        "status": "ok",
        "route": "/material-prep",
        "state": {"stage": "todo"},
        "available_actions": [],
        "blocked_actions": [],
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
async def test_contract_blocked_actions_reach_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """⑥ ``blocked_actions`` 全链路透传：契约层清洗 → ``accept_snapshot`` → 模型读到的 ``ok`` 里。

    这是本字段唯一有用的形态：模型要同时看到「能做」与「做不了 + 为什么」，才能决定是先补前置
    还是换一条路。只到契约层就断掉时，模型见到的仍是一张没有原因的静态动作表。
    """
    bus = _install_bus(monkeypatch, _FakeBus())
    reason = "当前没有选中材料包：先让律师选一条"

    async def answer() -> dict[str, Any]:
        while not bus.published:
            await asyncio.sleep(0.01)
        body = UiSnapshotIn(
            state={"selected": None},
            route="/material-prep",
            available_actions=["ui_material_prep_judge"],
            blocked_actions=[{"name": "ui_material_prep_judge", "reason": reason}],
        )
        return await snapshot.accept_snapshot(
            bus.published[0][1]["request_id"],
            state=body.state,
            route=body.route,
            available_actions=body.available_actions,
            blocked_actions=body.blocked_actions,
        )

    answering = asyncio.create_task(answer())
    result = await snapshot.request_snapshot("material-prep", _session_id(), timeout_s=1.0)
    receipt = await answering

    assert receipt["accepted"] is True and receipt["success"] is True
    assert result["status"] == "ok"
    assert result["blocked_actions"] == [{"name": "ui_material_prep_judge", "reason": reason}]
    # 不互斥：动作清单是按页面静态算的，同一条可能两边都在（见 state_tool 的 docstring）
    assert result["available_actions"] == ["ui_material_prep_judge"]


@pytest.mark.asyncio
async def test_no_page_state_still_carries_blocked_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    """``no_page_state`` 也带 ``blocked_actions``：页面只是没声明字段，不等于没有做不了的动作。"""
    blocked = [{"name": "ui_material_prep_judge", "reason": "先让律师选一条材料包"}]
    _install_bus(
        monkeypatch,
        _FakeBus(
            answer={"state": {}, "route": "/material-prep", "note": "页面没有声明状态", "blocked_actions": blocked}
        ),
    )

    result = await snapshot.request_snapshot(None, _session_id(), timeout_s=1.0)

    assert result["status"] == "no_page_state"
    assert result["blocked_actions"] == blocked


@pytest.mark.asyncio
async def test_timeout_has_no_blocked_actions_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """没问到就不能带这个键：空表会被模型读成「这页什么都做得了」。"""
    _install_bus(monkeypatch, _FakeBus())

    result = await snapshot.request_snapshot("material-prep", _session_id(), timeout_s=0.1)

    assert result["status"] == "timeout"
    assert "blocked_actions" not in result


@pytest.mark.asyncio
async def test_no_channel_has_no_blocked_actions_key() -> None:
    """同 ``timeout``：没有页面可问时，不许把「没问到」伪装成「没有做不了的动作」。"""
    result = await snapshot.request_snapshot(None, None)

    assert result["status"] == "no_channel"
    assert "blocked_actions" not in result


def test_blocked_actions_truncated_to_ten(caplog: pytest.LogCaptureFixture) -> None:
    """⑦ 超过 10 条只截断（不拒收）+ warn：与 ``available_actions`` 同口径。"""
    items = [{"name": f"ui_action_{i}", "reason": f"原因 {i}"} for i in range(12)]

    with caplog.at_level("WARNING"):
        payload = UiSnapshotIn(state={}, route="/x", blocked_actions=items)

    assert len(payload.blocked_actions) == 10
    assert payload.blocked_actions[0]["name"] == "ui_action_0"
    assert any("blocked_actions" in record.message for record in caplog.records)


def test_malformed_blocked_actions_dropped() -> None:
    """⑧ 形状不对的项整条丢掉（不拒收整份快照）：名字带 ``-``、空原因、多余键、同名重复。"""
    payload = UiSnapshotIn(
        state={},
        route="/material-prep",
        blocked_actions=[
            {"name": "ui_material_prep_judge", "reason": "先让律师选一条"},
            {"name": "ui-material-prep-judge", "reason": "名字里不许有短横"},
            {"name": "ui_material_prep_set_stage", "reason": "   "},
            {"name": "ui_navigate", "reason": "多余键", "extra": "x"},
            {"name": "ui_material_prep_judge", "reason": "同名重复，留第一条"},
            {"name": "ui_copilot_open", "reason": "\x07控制字符被洗掉"},
        ],
    )

    assert payload.blocked_actions == [
        {"name": "ui_material_prep_judge", "reason": "先让律师选一条"},
        {"name": "ui_copilot_open", "reason": "控制字符被洗掉"},
    ]


@pytest.mark.asyncio
async def test_endpoint_passes_actions_and_private_state_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """⑨ 端点那一行透传（``api/ui_api.py``）：漏了它，契约层洗得再干净也永远到不了模型/日志。

    这组字段的失效形态特别安静：``accept_snapshot(blocked_actions=..., private_state=...)`` 都有
    默认空值，少传一个关键字既不报错也不变更任何已有断言，只是模型永远读到「没什么做不了」、
    日志里永远没有私有状态——而这正是这些字段存在要防的那件事。所以这里直接调端点，
    钉「HTTP 那一层逐个传了」。
    """
    from apps.agent.api import ui_api

    captured: dict[str, Any] = {}

    async def fake_accept(request_id: str, **kwargs: Any) -> dict[str, Any]:
        captured["request_id"] = request_id
        captured.update(kwargs)
        return {"accepted": True, "success": True}

    async def allow(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(ui_api.snapshot, "accept_snapshot", fake_accept)
    monkeypatch.setattr(ui_api, "_current_user", lambda _request: SimpleNamespace(pk=7))
    monkeypatch.setattr(ui_api, "_rejection_reason", allow)

    body = UiSnapshotIn(
        state={"selected": None},
        route="/material-prep",
        available_actions=["ui_material_prep_judge"],
        blocked_actions=[{"name": "ui_material_prep_judge", "reason": "先让律师选一条材料包"}],
        private_state={"openDetail": "/material-prep/571"},
    )
    await ui_api.submit_ui_snapshot(object(), "req-through", body)

    assert captured["request_id"] == "req-through"
    assert captured["blocked_actions"] == [{"name": "ui_material_prep_judge", "reason": "先让律师选一条材料包"}]
    # 两个字段成对：只测 blocked 的话，下一次改动里 available 被漏掉也不会有人发现
    assert captured["available_actions"] == ["ui_material_prep_judge"]
    # 私有那一半也要在端点层被钉住：少了这一行，它到不了日志（唯一的可观测面）
    assert captured["private_state"] == {"openDetail": "/material-prep/571"}


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


@pytest.mark.asyncio
async def test_private_state_is_accepted_but_never_reaches_the_model(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """⑩ ``private_state`` 全链路：契约层收下 → 进 payload → **绝不进**模型看到的返回体。

    这是整条改动存在的理由：页面需要有地方放「未提交草稿 / 原始 id / 调试字段」。一旦它漏进
    ``request_snapshot`` 的返回值，页面就再没有这样的地方了——而漏进去不会有任何报错，只会让
    模型把草稿当既成事实（同 ``blocked_actions`` 漏传的那种静默失效）。所以这里同时钉两件事：
    返回体里**没有这个键**，而它进日志时**只有键名、没有值**。
    """
    bus = _install_bus(monkeypatch, _FakeBus())
    draft = "律师还没提交的草稿：甲公司与乙公司于 2025 年签约"

    async def answer() -> dict[str, Any]:
        while not bus.published:
            await asyncio.sleep(0.01)
        body = UiSnapshotIn(
            state={"stage": "todo"},
            route="/material-prep",
            private_state={"draftId": "d-7", "draftText": draft},
        )
        return await snapshot.accept_snapshot(
            bus.published[0][1]["request_id"],
            state=body.state,
            route=body.route,
            private_state=body.private_state,
        )

    with caplog.at_level("INFO"):
        answering = asyncio.create_task(answer())
        result = await snapshot.request_snapshot("material-prep", _session_id(), timeout_s=1.0)
        receipt = await answering

    assert receipt["accepted"] is True and receipt["success"] is True
    assert result["status"] == "ok"
    assert result["state"] == {"stage": "todo"}
    # 钉死：返回体里既没有这个键，也没有它的任何值（键名与值都查一遍，防止换个键名漏进来）。
    assert "private_state" not in result
    assert draft not in json.dumps(result, ensure_ascii=False)
    assert "draftId" not in json.dumps(result, ensure_ascii=False)
    # 唯一的可观测面：一条 info 日志，带键名与字节数，不带值。
    logged = [record.getMessage() for record in caplog.records if "private_state" in record.getMessage()]
    assert len(logged) == 1
    assert "draftId" in logged[0] and "draftText" in logged[0]
    assert "bytes=" in logged[0]
    assert draft not in logged[0]


@pytest.mark.asyncio
async def test_accept_snapshot_carries_private_state_in_the_payload() -> None:
    """``private_state`` 要进 payload：那是它跨进程交给等待方的唯一路径（日志之外）。

    这条与上一条是**一对**：上面钉「模型看不到」，这条钉「没在出口前就被扔掉」。
    """
    request_id = uuid.uuid4().hex
    await snapshot.register(request_id)

    await snapshot.accept_snapshot(
        request_id, state={"stage": "todo"}, route="/material-prep", private_state={"draftId": "d-7"}
    )

    payload = await snapshot.wait(request_id, 0.1)
    assert payload is not None
    assert payload["private_state"] == {"draftId": "d-7"}
    snapshot._FUTURES.pop(request_id, None)


@pytest.mark.asyncio
async def test_private_state_is_scrubbed_before_logging() -> None:
    """隐私不等于可信：这条通道也会进日志，所以与 ``state`` 同口径脱敏。"""
    payload = UiSnapshotIn(private_state={_SENSITIVE_FIELD: _SENSITIVE_VALUE}, route="/x")

    assert payload.private_state[_SENSITIVE_FIELD] == "ab***34"


def test_oversized_private_state_rejected_by_contract() -> None:
    """⑪ ``private_state`` 上限 4000 字（比 ``state`` 宽一倍：不进模型上下文、只进日志）。

    超限同样**直接拒**而不是截断：截断后的结构缺键，比一句「超量了」更难解释。
    """
    with pytest.raises(ValidationError) as excinfo:
        UiSnapshotIn(private_state={f"字段{i}": f"内容 {i}" for i in range(600)}, route="/x")

    message = str(excinfo.value)
    assert "4000" in message
    assert "超过" in message


def test_missing_private_state_keeps_the_existing_body() -> None:
    """⑫ 没传 ``private_state`` 时什么都不变（与原契约逐字一致，页面不上报就是空对象）。"""
    payload = UiSnapshotIn(state={"stage": "todo"}, route="/material-prep")

    assert payload.private_state == {}


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
