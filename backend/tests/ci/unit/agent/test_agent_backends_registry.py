"""Agent 后端抽象层：注册表语义与协议可满足性。

这一层的价值全在「约定」上，所以测试也全是约定测试，不碰任何真实后端：

1. 注册后能按 kind 取到，``available_kinds()`` 稳定有序；
2. 重复 kind **报错**而不是静默覆盖——覆盖会让两个模块的实现在运行期互相顶掉，
   「同一个名字跑出不同行为」是最难查的一类线上问题；
3. 未注册 kind 抛 ``LookupError`` 且带已注册清单——否则「拼错」和「忘了注册」
   长得一模一样；
4. ``BackendCapabilities`` / ``RunContext`` 不可变——运行期改能力声明会让前端
   的 UI 形态无法预判；
5. 一个最小假 backend 能通过 ``isinstance(..., AgentBackend)``：``runtime_checkable``
   是「不用继承也能实现」的前提，破了它整层解耦就退化成显式基类。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from apps.agent.backends import AgentBackend, BackendCapabilities, RunContext, available_kinds, get, register
from apps.agent.backends import registry as registry_module


def _caps(**overrides: Any) -> BackendCapabilities:
    """全能力开启的能力声明，按需覆盖单项。"""
    base: dict[str, Any] = {
        "streaming": True,
        "tool_calls": True,
        "approval": True,
        "compaction": True,
        "steer": True,
    }
    base.update(overrides)
    return BackendCapabilities(**base)


class _FakeBackend:
    """最小可实现后端：不碰网络、不碰进程，只证明协议可被结构化满足。"""

    kind = "fake"
    capabilities = _caps(streaming=False, steer=False)

    def stream(self, ctx: RunContext) -> AsyncIterator[dict[str, Any]]:
        async def _gen() -> AsyncIterator[dict[str, Any]]:
            yield {"type": "meta", "session_id": str(ctx.session), "agent": self.kind, "run_id": ctx.run_id}
            yield {"type": "done", "session_id": str(ctx.session), "agent": self.kind, "run_id": ctx.run_id}

        return _gen()


@pytest.fixture(autouse=True)
def _empty_registry() -> Any:
    """每条用例前后都清空：注册表是模块级全局状态，串用例会出假绿。"""
    registry_module.clear()
    yield
    registry_module.clear()


class TestRegistry:
    def test_registered_backend_is_returned_by_kind(self) -> None:
        backend = _FakeBackend()
        register(backend)
        assert get("fake") is backend

    def test_register_returns_backend_for_decorator_use(self) -> None:
        """``@register`` 用法要求返回原对象，否则类名被替换成 None。"""
        backend = _FakeBackend()
        assert register(backend) is backend

    def test_duplicate_kind_raises_value_error(self) -> None:
        register(_FakeBackend())
        with pytest.raises(ValueError, match="重复注册"):
            register(_FakeBackend())

    def test_duplicate_kind_does_not_overwrite_original(self) -> None:
        """报错之外的另一半约束：原有实现必须原封不动，不能被顶掉。"""
        first = _FakeBackend()
        register(first)
        with pytest.raises(ValueError):
            register(_FakeBackend())
        assert get("fake") is first

    def test_unknown_kind_raises_lookup_error_with_known_kinds(self) -> None:
        register(_FakeBackend())
        with pytest.raises(LookupError) as excinfo:
            get("not-registered")
        message = str(excinfo.value)
        assert "not-registered" in message
        assert "fake" in message, f"错误信息必须带已注册清单，实际: {message}"

    def test_unknown_kind_error_lists_nothing_when_empty(self) -> None:
        with pytest.raises(LookupError, match=r"已注册: \[\]"):
            get("anything")

    def test_available_kinds_is_sorted(self) -> None:
        for kind in ("zulu", "alpha", "mike"):
            backend = _FakeBackend()
            backend.kind = kind
            register(backend)
        assert available_kinds() == ["alpha", "mike", "zulu"]

    def test_available_kinds_returns_copy_not_live_view(self) -> None:
        register(_FakeBackend())
        kinds = available_kinds()
        kinds.append("injected")
        assert available_kinds() == ["fake"]

    def test_clear_removes_backend(self) -> None:
        register(_FakeBackend())
        registry_module.clear()
        with pytest.raises(LookupError):
            get("fake")
        assert available_kinds() == []

    def test_same_kind_can_be_registered_again_after_clear(self) -> None:
        """测试之间要能重复注册同一个 kind，否则每条用例都得换名字。"""
        register(_FakeBackend())
        registry_module.clear()
        register(_FakeBackend())
        assert available_kinds() == ["fake"]


class TestCapabilities:
    def test_capabilities_are_frozen(self) -> None:
        caps = _caps()
        with pytest.raises(FrozenInstanceError):
            caps.streaming = False  # type: ignore[misc]

    def test_capabilities_field_values_are_kept(self) -> None:
        """全 False 的能力声明必须如实回报——它是「缺哪一块」的唯一来源。"""
        caps = _caps(streaming=False, approval=False, compaction=False, steer=False)
        assert (caps.streaming, caps.tool_calls, caps.approval, caps.compaction, caps.steer) == (
            False,
            True,
            False,
            False,
            False,
        )

    def test_run_context_is_frozen(self) -> None:
        ctx = RunContext(
            run_id="run-1",
            session="session-1",
            user_id=1,
            prompt="你好",
            user_token="token",  # pragma: allowlist secret
            model=None,
            tool_selection=None,
        )
        with pytest.raises(FrozenInstanceError):
            ctx.prompt = "改过"  # type: ignore[misc]

    def test_run_context_allows_anonymous_user(self) -> None:
        """``user_id=None`` 是合法取值（测试 / 后台任务场景），不是缺省错误。"""
        ctx = RunContext(
            run_id="run-1",
            session="session-1",
            user_id=None,
            prompt="你好",
            user_token="token",  # pragma: allowlist secret
            model="some-model",
            tool_selection="mcp__fachuan__*",
        )
        assert ctx.user_id is None
        assert ctx.model == "some-model"
        assert ctx.tool_selection == "mcp__fachuan__*"


class TestProtocol:
    def test_fake_backend_satisfies_protocol(self) -> None:
        assert isinstance(_FakeBackend(), AgentBackend)

    def test_object_without_stream_does_not_satisfy_protocol(self) -> None:
        """``runtime_checkable`` 只查属性存在性——把 stream 去掉就必须不通过，
        否则契约形同虚设。"""

        class _Broken:
            kind = "broken"
            capabilities = _caps()

        assert not isinstance(_Broken(), AgentBackend)

    def test_fake_backend_stream_yields_sse_contract_events(self) -> None:
        """``stream()`` 返回异步迭代器（不是 async def 生成器），
        实现方才能直接把下游迭代器交出去。"""
        backend: AgentBackend = _FakeBackend()
        ctx = RunContext(
            run_id="run-1",
            session="session-1",
            user_id=None,
            prompt="你好",
            user_token="token",  # pragma: allowlist secret
            model=None,
            tool_selection=None,
        )

        async def _collect() -> list[dict[str, Any]]:
            return [event async for event in backend.stream(ctx)]

        events = asyncio.run(_collect())
        assert [event["type"] for event in events] == ["meta", "done"]
        for event in events:
            assert event["agent"] == "fake"
            assert event["run_id"] == "run-1"
