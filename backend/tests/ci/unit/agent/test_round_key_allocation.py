"""轮次级 API key 分配（``services/chat/multi.py`` × ``backends/key_scheduler.py``）。

网关对**每把 key** 限 3 并发（实测 429 + ``retry-after: 60``，那一栏的表现是
「卡住 60 秒」），而后端自己的 ``_next_key`` 是全局轮转计数：它只保证「先后两次
通常不同」，**不保证**同一轮的 N 栏落在不同 key 上，也不知道哪把已经满了。
所以「三 agent 用三把 key」必须由编排层在轮次级别显式分配。

本文件钉的是编排层承诺的那份契约：

1. **三栏 → 三把互不相同**的 key（同一轮内不撞）；
2. **单栏 → 一把**（不分的话这一栏与同时跑的另一个人撞在同一把上照样 429）；
3. **租约一定归还**：正常结束、某栏抛异常、客户端断开三条路径跑完
   ``get_key_scheduler().snapshot()`` 都必须清零——漏还一把 key 是那一路并发
   额度永久少 1，之后越来越容易 429，且没有任何报错；
4. **拿不到 key 池时传 ``None`` 且不报错**（没有可用 provider / 读配置失败），
   行为退回「各栏自己轮转」，与引入 key 分配前逐字一致；
5. **配额降级只跑主答时，没用上的那几把立刻归还**，不从本轮白占着额度。

全部离线：注册表注入假后端（``stream()`` 只吐预置事件），网关配置用桩替换，
既不读库也不调真模型。数据库用 ``django_db(transaction=True)``：
``stream_multi`` 跨 ``asyncio.create_task`` 并发写库（与 ``test_dual_stream.py``
同一口径）。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any, cast

import pytest

from apps.agent.backends import BackendCapabilities, RunContext, register
from apps.agent.backends import registry as registry_module
from apps.agent.backends.gateway_cache import GatewaySettings
from apps.agent.backends.key_scheduler import get_key_scheduler
from apps.agent.models import AgentSession
from apps.agent.services.chat import budget, multi
from apps.agent.services.chat import stream as stream_module

#: 会话的主答后端。kind 刻意不用 ``pi`` / ``dsh``：那两个名字属于真实后端，
#: ``builtin.ensure_registered()`` 会把它们补回注册表，然后本轮真的去起子进程。
PRIMARY = "fake-primary"
SECONDARY = "fake-secondary"
THIRD = "fake-third"

#: 桩里的 key 池（比栏数多，模拟实测的 5 把）
KEYS = ("sk-A", "sk-B", "sk-C", "sk-D", "sk-E")

_CAPS = BackendCapabilities(
    streaming=True,
    tool_calls=False,
    approval=False,
    compaction=False,
    steer=False,
)


def _settings(keys: tuple[str, ...]) -> GatewaySettings:
    """桩的网关配置快照（只用到 ``api_keys``，其余字段填最小合法值）。"""
    return GatewaySettings(
        base_url="http://gateway.test",
        api_keys=keys,
        models=("m-primary",),
        default_model="m-primary",
        enable_thinking=False,
    )


def _use_key_pool(monkeypatch: pytest.MonkeyPatch, keys: tuple[str, ...] | None) -> None:
    """把 ``multi`` 取 key 池的那一步换成桩；``None`` = 没有可用 provider。

    桩的是 :func:`gateway_cache.load_api_keys`（``multi`` 现在委托它），
    不是 ``get_gateway_settings``——后者已不在 ``multi`` 的调用路径上，
    patch 它会「成功但无效」，测试会以为桩生效了。
    """

    async def _load(_model_hint: str | None) -> tuple[str, ...]:
        return () if keys is None else keys

    monkeypatch.setattr(multi, "load_api_keys", _load)


def _inflight() -> int:
    """当前在飞计数之和（``snapshot()`` 的键是指纹，可以安全断言/打印）。"""
    return sum(get_key_scheduler().snapshot().values())


def _ok_script(text: str) -> list[dict[str, Any]]:
    """一轮成功的事件脚本（delta → usage）。

    **不含 ``done``**：收尾事件由编排层 ``stream_chat`` 统一发（见
    ``backends/base.py`` 契约）；假后端自己发一个，测到的就是「假后端违约」。
    """
    return [
        {"type": "delta", "content": text},
        {"type": "usage", "input_tokens": 1, "output_tokens": 1},
    ]


class _KeyRecordingBackend:
    """按预置脚本吐事件，并记下本轮 ``RunContext``（含 ``api_key``）。

    ``probes`` 非空时，还在**开跑那一刻**记一次调度器在飞计数：用来证明
    「某一栏跑的时候，这一轮到底占着几把 key」——那是「降级不多占」「单栏只占
    一把」唯一能观测到的时刻（跑完就都归还了）。
    """

    def __init__(
        self,
        kind: str,
        script: list[dict[str, Any]] | BaseException,
        contexts: dict[str, RunContext],
        *,
        probes: dict[str, int] | None = None,
        block_on: asyncio.Event | None = None,
    ) -> None:
        self.kind = kind
        self.capabilities = _CAPS
        self._script = script
        self._contexts = contexts
        self._probes = probes
        self._block_on = block_on

    def stream(self, ctx: RunContext) -> AsyncGenerator[dict[str, Any] | None, None]:
        return self._stream(ctx)

    async def _stream(self, ctx: RunContext) -> AsyncGenerator[dict[str, Any] | None, None]:
        self._contexts[self.kind] = ctx
        if self._probes is not None:
            self._probes[self.kind] = _inflight()
        if isinstance(self._script, BaseException):
            raise self._script
        for event in self._script:
            # 让出一个 tick：假后端不 await 的话先起的那一栏会一口气跑完，
            # 测不到「三栏真的同时在飞」这件事。
            await asyncio.sleep(0)
            yield event
        if self._block_on is not None:
            # 模拟「这一栏还在跑」：客户端断开时它必须被 cancel，而租约仍要归还。
            await self._block_on.wait()


def _guard_get_backend(kind: str) -> Any:
    """取后端，并断言「只取本用例注入的假后端」。

    真实后端一旦被 ``ensure_registered`` 补回注册表，本轮就会去读库 / 起子进程，
    断言随之变成一条看不出根因的「key 不对」。
    """
    from apps.agent.backends import get

    backend = get(kind)
    assert isinstance(backend, _KeyRecordingBackend), f"取到了真实后端 {kind!r}，注册表未被隔离"
    return backend


@pytest.fixture(autouse=True)
def _isolated_globals(monkeypatch: pytest.MonkeyPatch) -> Any:
    """注册表 / aux 席位 / key 调度器都是进程内全局状态：每条用例前后清空。

    收尾再断言一次 ``snapshot()`` 全清：漏还的计数会跨用例累积，让后面的断言
    变成「看运气」（也是生产里「越来越容易 429」的同一个机制）。
    """
    registry_module.clear()
    budget._budget.reset()
    get_key_scheduler().reset()
    # 两个模块都用 ``from ... import ensure_registered`` 取了本地名，
    # 只改 ``builtin`` 的属性对它们无效，必须逐个替换引用点。
    monkeypatch.setattr(stream_module, "ensure_registered", lambda: None)
    monkeypatch.setattr(multi, "ensure_registered", lambda: None)
    monkeypatch.setattr(stream_module, "get_backend", _guard_get_backend)
    monkeypatch.delenv("FACHUAN_AGENT_AUX_SLOTS", raising=False)
    monkeypatch.delenv("FACHUAN_AGENT_AUX_RATIO", raising=False)
    yield
    assert get_key_scheduler().snapshot() == {}, "用例结束时仍有 key 租约没归还"
    registry_module.clear()
    budget._budget.reset()
    get_key_scheduler().reset()


async def _make_session() -> AgentSession:
    return await AgentSession.objects.acreate(title="轮次 key 分配", agent_kind=PRIMARY)


def _register_ok(contexts: dict[str, RunContext], *kinds: str, probes: dict[str, int] | None = None) -> None:
    """注册一批「正常回答」的假后端，并把每栏的 ``RunContext`` 记进 ``contexts``。"""
    for kind in kinds:
        register(_KeyRecordingBackend(kind, _ok_script(kind), contexts, probes=probes))


async def _collect_multi(session: AgentSession, kinds: list[str]) -> list[dict[str, Any]]:
    return [
        event
        async for event in multi.stream_multi(session=session, user_message="合同有效吗", user_id=None, kinds=kinds)
    ]


class TestThreeColumns:
    """三栏：一轮里三个 agent 各拿一把**不同**的 key。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_three_columns_get_three_distinct_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _use_key_pool(monkeypatch, KEYS)
        contexts: dict[str, RunContext] = {}
        _register_ok(contexts, PRIMARY, SECONDARY, THIRD)
        session = await _make_session()

        events = await _collect_multi(session, [PRIMARY, SECONDARY, THIRD])

        assert set(contexts) == {PRIMARY, SECONDARY, THIRD}
        keys = {kind: ctx.api_key for kind, ctx in contexts.items()}
        # 这是本任务的字面要求：三栏三把不同的 key（撞一把就是 3 并发打满，
        # 再加一个人提问就 429 + 等 60 秒）
        assert len(set(keys.values())) == 3, f"三栏拿到了重复的 key: {keys}"
        assert set(keys.values()) <= set(KEYS), keys

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_three_columns_release_every_lease(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """三栏跑完必须一把不剩：漏还的额度是永久的，且没有任何报错。"""
        _use_key_pool(monkeypatch, KEYS)
        contexts: dict[str, RunContext] = {}
        probes: dict[str, int] = {}
        _register_ok(contexts, PRIMARY, SECONDARY, THIRD, probes=probes)
        session = await _make_session()

        events = await _collect_multi(session, [PRIMARY, SECONDARY, THIRD])

        assert get_key_scheduler().snapshot() == {}
        # 三栏同时在飞时确实占着 3 把（不是「分配了但只传下去一把」）
        assert max(probes.values()) == 3, probes
        # 顺带确认没破坏既有契约：三栏各一个 done、各一份正文
        assert [event["type"] for event in events].count("done") == 3
        assert len([event for event in events if event.get("type") == "delta"]) == 3


class TestSingleColumn:
    """单栏（``len(agents)==1`` 走透传）：也要分配，且只占一把。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_single_column_gets_one_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _use_key_pool(monkeypatch, KEYS)
        contexts: dict[str, RunContext] = {}
        probes: dict[str, int] = {}
        _register_ok(contexts, PRIMARY, probes=probes)
        session = await _make_session()

        events = [
            event
            async for event in multi.stream_multi(
                session=session, user_message="合同有效吗", user_id=None, kinds=[PRIMARY]
            )
        ]

        assert set(contexts) == {PRIMARY}
        assert contexts[PRIMARY].api_key in KEYS
        # 单栏只占一把：打开这一栏时在飞计数恰好是 1
        assert probes == {PRIMARY: 1}
        # 透传路径的 done 不带 agent（既有契约，单栏时前端不需要分流）
        dones = [event for event in events if event.get("type") == "done"]
        assert len(dones) == 1
        assert "agent" not in dones[0]
        assert get_key_scheduler().snapshot() == {}


class TestLeaseReturned:
    """租约归还：正常 / 抛异常 / 客户端断开三条路径都不能漏。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_secondary_failure_still_releases_its_lease(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _use_key_pool(monkeypatch, KEYS)
        contexts: dict[str, RunContext] = {}
        register(_KeyRecordingBackend(PRIMARY, _ok_script("主答正文"), contexts))
        register(_KeyRecordingBackend(SECONDARY, RuntimeError("次答炸了"), contexts))
        session = await _make_session()

        events = [
            event
            async for event in multi.stream_multi(
                session=session, user_message="合同有效吗", user_id=None, kinds=[PRIMARY, SECONDARY]
            )
        ]

        # 失败矩阵不受影响：失败方一条 error、每栏各一个 done
        errors = [event for event in events if event.get("type") == "error"]
        assert len(errors) == 1
        assert [event["type"] for event in events].count("done") == 2
        # 关键：炸掉那一栏的 key 也要还回去
        assert get_key_scheduler().snapshot() == {}

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_primary_failure_still_releases_its_lease(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _use_key_pool(monkeypatch, KEYS)
        contexts: dict[str, RunContext] = {}
        register(_KeyRecordingBackend(PRIMARY, RuntimeError("主答炸了"), contexts))
        register(_KeyRecordingBackend(SECONDARY, _ok_script("次答正文"), contexts))
        session = await _make_session()

        await _collect_multi(session, [PRIMARY, SECONDARY])

        assert get_key_scheduler().snapshot() == {}

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_client_disconnect_releases_every_lease(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """客户端中途断开（按停止）：已开跑的栏被 cancel，租约仍要全部归还。

        这是最容易漏的一条路径：被 cancel 的协程未必还能被调度到它的 ``finally``，
        所以整轮另挂了一层兜底（见 ``stream_multi`` 里 ``stack.callback`` 的注释）。
        """
        _use_key_pool(monkeypatch, KEYS)
        contexts: dict[str, RunContext] = {}
        # 次答卡住不结束：主答出完字后本轮仍在流里，断开时它还在飞
        register(_KeyRecordingBackend(PRIMARY, _ok_script("主答正文"), contexts))
        register(_KeyRecordingBackend(SECONDARY, [], contexts, block_on=asyncio.Event()))
        session = await _make_session()

        events: list[dict[str, Any]] = []
        # ``aclose()`` 只在异步生成器上有（返回值声明的是 ``AsyncIterator``）
        stream = cast(
            AsyncGenerator[dict[str, Any], None],
            multi.stream_multi(session=session, user_message="合同有效吗", user_id=None, kinds=[PRIMARY, SECONDARY]),
        )
        async for event in stream:
            events.append(event)
            if event.get("type") == "delta":  # 主答已经出字，用户此刻按了停止
                break
        await stream.aclose()

        assert get_key_scheduler().snapshot() == {}
        # 被 cancel 的次答还会跑完自己的 finally（含落库）：等它收尾，
        # 既让上面的断言稳定，也避免用例结束时留下未完成的协程。
        await asyncio.sleep(0.2)
        assert get_key_scheduler().snapshot() == {}


class TestNoKeyPool:
    """拿不到 key 池：传 ``None``、不报错、行为退回后端自己的轮转。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_missing_provider_passes_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _use_key_pool(monkeypatch, None)
        contexts: dict[str, RunContext] = {}
        _register_ok(contexts, PRIMARY, SECONDARY, THIRD)
        session = await _make_session()

        events = await _collect_multi(session, [PRIMARY, SECONDARY, THIRD])

        assert {ctx.api_key for ctx in contexts.values()} == {None}
        # 没有 key 池不是错误：三栏照常跑完、没有任何 error
        assert [event["type"] for event in events].count("error") == 0
        assert [event["type"] for event in events].count("done") == 3
        assert get_key_scheduler().snapshot() == {}

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_provider_lookup_failure_passes_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """读网关配置本身抛错时也不许把整轮打死（运维问题不该让律师提问失败）。"""

        # 在**真正的边界**打桩（gateway_cache 读配置那一步），而不是替换
        # ``load_api_keys`` 本身——后者的职责正是「读失败就返回空」，把它整个换掉
        # 等于绕过了要测的那段兜底逻辑。
        from apps.agent.backends import gateway_cache

        def _boom(_model_hint: str | None) -> None:
            raise RuntimeError("读库失败")

        monkeypatch.setattr(gateway_cache, "get_gateway_settings", _boom)
        contexts: dict[str, RunContext] = {}
        _register_ok(contexts, PRIMARY, SECONDARY)
        session = await _make_session()

        events = await _collect_multi(session, [PRIMARY, SECONDARY])

        assert {ctx.api_key for ctx in contexts.values()} == {None}
        assert [event["type"] for event in events].count("error") == 0
        assert get_key_scheduler().snapshot() == {}


class TestQuotaDegraded:
    """配额降级（只跑主答）：没用上的那几把 key 不该被本轮白占着。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_degraded_releases_unused_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FACHUAN_AGENT_AUX_SLOTS", "0")  # 对比能力关闭 = 走降级路径
        _use_key_pool(monkeypatch, KEYS)
        contexts: dict[str, RunContext] = {}
        probes: dict[str, int] = {}
        _register_ok(contexts, PRIMARY, SECONDARY, THIRD, probes=probes)
        session = await _make_session()

        events = await _collect_multi(session, [PRIMARY, SECONDARY, THIRD])

        # 只有主答真的跑起来了
        assert set(contexts) == {PRIMARY}
        assert contexts[PRIMARY].api_key in KEYS
        # 主答开跑那一刻，本轮只占一把：另外两把在被判定降级时就已归还
        assert probes == {PRIMARY: 1}, probes
        # 降级仍是 activity{degraded} + 单栏 done（既有契约不变）
        degraded = [event for event in events if event.get("status") == multi.ACTIVITY_DEGRADED]
        assert len(degraded) == 1
        assert [event["type"] for event in events].count("done") == 1
        assert get_key_scheduler().snapshot() == {}


class TestKeyPoolLookup:
    """key 池按**主答模型**的 hint 取（一轮跑的是同一个网关），且只取一次。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_pool_looked_up_once_by_primary_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        hints: list[str | None] = []

        async def _record(model_hint: str | None) -> tuple[str, ...]:
            hints.append(model_hint)
            return KEYS

        monkeypatch.setattr(multi, "load_api_keys", _record)
        contexts: dict[str, RunContext] = {}
        _register_ok(contexts, PRIMARY, SECONDARY)
        session = await _make_session()

        events = [
            event
            async for event in multi.stream_multi(
                session=session,
                user_message="合同有效吗",
                user_id=None,
                specs=[multi.AgentSpec(PRIMARY, "m-primary"), multi.AgentSpec(SECONDARY, "m-secondary")],
            )
        ]

        # 整轮只查一次配置（每栏各查一次只是把同一条读库排队 N 遍），hint 取主答
        assert hints == ["m-primary"]
        assert [event["type"] for event in events].count("done") == 2
