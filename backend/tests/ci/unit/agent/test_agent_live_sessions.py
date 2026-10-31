"""运行中插话（steer / follow_up / clear_queue）与运行中会话注册表。

关键约束（与审批相反）：``PiRpcSession`` 持有真实子进程管道，无法跨进程传递，
所以插话只能在「跑着这个会话的 worker」内生效。找不到就如实报错，不假装成功。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from apps.agent.pi.rpc_client import PiError
from apps.agent.services.chat_service import SessionNotLiveError, clear_queue_session, follow_up_session, steer_session
from apps.agent.services.live_sessions import LiveSessionRegistry, SessionBusyError, get_live_registry


class _StubPiSession:
    """记录收到的命令，供断言。"""

    def __init__(self, fail: bool = False) -> None:
        self.commands: list[tuple[str, str]] = []
        self._fail = fail

    async def prompt(self, message: str) -> None:
        self.commands.append(("prompt", message))

    async def steer(self, message: str) -> str:
        if self._fail:
            raise PiError("steer 被拒绝: already settled")
        self.commands.append(("steer", message))
        return "queued"

    async def follow_up(self, message: str) -> str:
        if self._fail:
            raise PiError("follow_up 被拒绝: already settled")
        self.commands.append(("follow_up", message))
        return "queued"

    async def clear_queue(self) -> list[str]:
        self.commands.append(("clear_queue", ""))
        return ["改方向", "再补一句"]


@pytest.fixture(autouse=True)
def _clean_registry() -> Any:
    """每个用例前后清空全局注册表，避免互相污染。"""
    registry = get_live_registry()

    def _clear() -> None:
        try:
            asyncio.run(registry.clear())
        except RuntimeError as exc:
            # 已有事件循环在跑时 asyncio.run 会拒绝调用，此处无需清理。
            del exc

    _clear()
    yield
    _clear()


class TestLiveSessionRegistry:
    def test_register_and_get(self) -> None:
        async def run() -> Any:
            reg = LiveSessionRegistry()
            stub = _StubPiSession()
            await reg.register("s1", stub)
            assert await reg.get("s1") is stub
            assert await reg.is_live("s1") is True
            return reg

        asyncio.run(run())

    def test_get_unknown_returns_none(self) -> None:
        async def run() -> Any:
            return await LiveSessionRegistry().get("nope")

        assert asyncio.run(run()) is None

    def test_duplicate_register_raises_busy(self) -> None:
        """同一会话不允许两条并行对话（模型会看到两份冲突上下文）。"""

        async def run() -> None:
            reg = LiveSessionRegistry()
            await reg.register("s1", _StubPiSession())
            await reg.register("s1", _StubPiSession())

        with pytest.raises(SessionBusyError):
            asyncio.run(run())

    def test_reregister_same_object_is_idempotent(self) -> None:
        async def run() -> None:
            reg = LiveSessionRegistry()
            stub = _StubPiSession()
            await reg.register("s1", stub)
            await reg.register("s1", stub)
            assert await reg.get("s1") is stub

        asyncio.run(run())

    def test_unregister_only_removes_matching_object(self) -> None:
        """后到的会话不能被前一个的清理误删（先结束后注册的极端顺序）。"""

        async def run() -> None:
            reg = LiveSessionRegistry()
            first = _StubPiSession()
            await reg.register("s1", first)
            await reg.unregister("s1", _StubPiSession())  # 不是表里那个
            assert await reg.get("s1") is first
            await reg.unregister("s1", first)
            assert await reg.get("s1") is None

        asyncio.run(run())


class TestSteerService:
    def test_steer_delivers_to_live_session(self) -> None:
        async def run() -> list[tuple[str, str]]:
            stub = _StubPiSession()
            await get_live_registry().register("s1", stub)
            disposition = await steer_session(session_id="s1", message="换个方向")
            assert disposition == "queued"
            return stub.commands

        assert asyncio.run(run()) == [("steer", "换个方向")]

    def test_steer_without_live_session_raises(self) -> None:
        async def run() -> None:
            await steer_session(session_id="missing", message="x")

        with pytest.raises(SessionNotLiveError):
            asyncio.run(run())

    def test_steer_propagates_pi_rejection(self) -> None:
        """pi 拒绝（已 settle）要抛出，由 API 层转 409，不能静默吞掉。"""

        async def run() -> None:
            await get_live_registry().register("s1", _StubPiSession(fail=True))
            await steer_session(session_id="s1", message="x")

        with pytest.raises(PiError):
            asyncio.run(run())


class TestFollowUpService:
    def test_follow_up_delivers(self) -> None:
        async def run() -> list[tuple[str, str]]:
            stub = _StubPiSession()
            await get_live_registry().register("s2", stub)
            await follow_up_session(session_id="s2", message="再补一段")
            return stub.commands

        assert asyncio.run(run()) == [("follow_up", "再补一段")]

    def test_follow_up_without_live_session_raises(self) -> None:
        async def run() -> None:
            await follow_up_session(session_id="missing", message="x")

        with pytest.raises(SessionNotLiveError):
            asyncio.run(run())


class TestClearQueueService:
    def test_clear_queue_returns_retracted_texts(self) -> None:
        async def run() -> list[str]:
            await get_live_registry().register("s3", _StubPiSession())
            return await clear_queue_session(session_id="s3")

        assert asyncio.run(run()) == ["改方向", "再补一句"]

    def test_clear_queue_without_live_session_is_empty_not_error(self) -> None:
        """「撤销」按钮可能刚好在上一轮结束后被点，不该报错。"""

        async def run() -> list[str]:
            return await clear_queue_session(session_id="missing")

        assert asyncio.run(run()) == []


class TestChatServiceRegistersLiveSession:
    """stream_chat 运行期间必须登记 pi_session，结束时注销。

    没有这一步，POST /steer 找不到目标进程——插话功能就是空的。
    """

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_registers_while_streaming_and_unregisters_after(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from asgiref.sync import sync_to_async

        from apps.agent.models import AgentSession
        from apps.agent.services import chat_service
        from apps.agent.services.event_bus import EventBus

        observed: dict[str, Any] = {}
        stub_pi = _StubPiSession()

        class _Acquire:
            async def __aenter__(self) -> _StubPiSession:
                return stub_pi

            async def __aexit__(self, *exc: object) -> bool:
                return False

        class _Pool:
            def acquire(self, **kwargs: Any) -> _Acquire:
                return _Acquire()

        async def fake_stream(pi_session: Any, *, agent: str = "pi") -> Any:
            # 流式期间：此时应当已经登记
            observed["live_during"] = await get_live_registry().is_live(str(session.session_id))
            yield {"type": "delta", "content": "答"}
            yield {"type": "done"}

        async def fake_pool() -> Any:
            return _Pool()

        async def fake_model() -> str | None:
            return None

        monkeypatch.setattr(chat_service, "get_pool", fake_pool)
        monkeypatch.setattr(chat_service, "_resolve_model", fake_model)
        monkeypatch.setattr(chat_service, "stream_events", fake_stream)
        monkeypatch.setattr(EventBus, "_ensure_relay", lambda self: None)

        session = await sync_to_async(AgentSession.objects.create)(title="")
        async for _ in chat_service.stream_chat(session=session, user_message="问题", user_id=None):
            pass

        observed["live_after"] = await get_live_registry().is_live(str(session.session_id))
        assert observed["live_during"] is True, "运行期间未登记，插话无法投递"
        assert observed["live_after"] is False, "结束后未注销，注册表泄漏"

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_steer_reaches_the_running_process(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """端到端：流式进行中调 steer_session 能落到同一个桩进程上。"""
        from asgiref.sync import sync_to_async

        from apps.agent.models import AgentSession
        from apps.agent.services import chat_service
        from apps.agent.services.event_bus import EventBus

        stub_pi = _StubPiSession()

        class _Acquire:
            async def __aenter__(self) -> _StubPiSession:
                return stub_pi

            async def __aexit__(self, *exc: object) -> bool:
                return False

        class _Pool:
            def acquire(self, **kwargs: Any) -> _Acquire:
                return _Acquire()

        async def fake_stream(pi_session: Any, *, agent: str = "pi") -> Any:
            yield {"type": "delta", "content": "开头"}
            await steer_session(session_id=str(session.session_id), message="改成这样")
            yield {"type": "done"}

        async def fake_pool() -> Any:
            return _Pool()

        async def fake_model() -> str | None:
            return None

        monkeypatch.setattr(chat_service, "get_pool", fake_pool)
        monkeypatch.setattr(chat_service, "_resolve_model", fake_model)
        monkeypatch.setattr(chat_service, "stream_events", fake_stream)
        monkeypatch.setattr(EventBus, "_ensure_relay", lambda self: None)

        session = await sync_to_async(AgentSession.objects.create)(title="")
        async for _ in chat_service.stream_chat(session=session, user_message="q", user_id=None):
            pass

        assert ("steer", "改成这样") in stub_pi.commands
