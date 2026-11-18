"""Agent 后端协议：三个「pi 专属假设」的显式化。

注册表测试（``test_agent_backends_registry.py``）只管「谁注册了、取得到吗」；
本文件管的是**接入第二个 agent 时会爆的三处遗漏假设**：

1. **运行中控制**（:class:`LiveBackendHandle`）——``live_sessions`` 存具体
   ``PiRpcSession`` 的后果是「同一张表混两种不兼容对象」，HTTP 插话端点无法区分。
   协议先立好，接线留给 ``PiBackend``。
2. **错误分类**（:class:`BackendError` / :class:`BackendErrorKind`）——编排层
   目前靠 ``except PiNotAvailableError / PiError / PoolQueueTimeoutError`` 选文案，
   等于把 ``if agent == "pi"`` 搬进 except 子句。
3. **同会话并发**（``BackendCapabilities.concurrent_in_session``）——「同会话只允许
   一个运行」此前只写在 ``live_sessions`` 的注释里，想开双答时无从判断。

全部是**结构性**断言，不构造真实子进程、不连网络：本层只有约定可测。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from apps.agent.backends import (
    MAKE_HANDLE_METHOD,
    AgentBackend,
    BackendCapabilities,
    BackendError,
    BackendErrorKind,
    LiveBackendHandle,
    RunContext,
)
from apps.agent.pi.pool import PoolQueueTimeoutError
from apps.agent.pi.rpc_client import PiError, PiNotAvailableError


def _ctx(run_id: str = "run-1") -> RunContext:
    return RunContext(
        run_id=run_id,
        session="session-1",
        user_id=None,
        prompt="你好",
        user_token="token",  # pragma: allowlist secret
        model=None,
        tool_selection=None,
    )


class TestBackendErrorKind:
    def test_kinds_are_stable_strings(self) -> None:
        """取值会进日志、进 ``AgentRun.error_kind``，改名等于历史数据对不上。"""
        assert {kind.name: kind.value for kind in BackendErrorKind} == {
            "UNAVAILABLE": "unavailable",
            "BUSY": "busy",
            "AUTH": "auth",
            "RATE_LIMITED": "rate_limited",
            "CONTEXT_OVERFLOW": "context_overflow",
            "UNKNOWN": "unknown",
        }

    def test_kind_is_str_enum(self) -> None:
        """``StrEnum`` 才能直接塞进 JSON 事件与 DB 字段，不必到处 ``.value``。"""
        assert BackendErrorKind.BUSY == "busy"
        assert isinstance(BackendErrorKind.BUSY, str)

    def test_unknown_is_the_catch_all(self) -> None:
        """兜底分类必须存在：没有 ``UNKNOWN`` 就会有人为了「塞进某个分类」
        而把错误标错，用户看到与事实不符的提示。"""
        assert BackendErrorKind.UNKNOWN.value == "unknown"


class TestBackendError:
    def test_is_runtime_error(self) -> None:
        """与 pi 现有 ``PiError`` / ``PoolQueueTimeoutError`` 同根，
        将来收编 pi 异常时只写 ``except RuntimeError`` 的旧代码行为不变。"""
        error = BackendError(BackendErrorKind.UNAVAILABLE, "pi 没装")
        assert isinstance(error, RuntimeError)

    def test_carries_kind_and_message(self) -> None:
        error = BackendError(BackendErrorKind.CONTEXT_OVERFLOW, "上下文超窗")
        assert error.kind is BackendErrorKind.CONTEXT_OVERFLOW
        assert error.message == "上下文超窗"
        assert "上下文超窗" in str(error)

    def test_retryable_defaults_to_false(self) -> None:
        """默认不可重试：编排层拿不到明确信号时不该自动重放，
        否则 ``AUTH`` / ``CONTEXT_OVERFLOW`` 会被白白重试，用户等更久、账单更高。"""
        assert BackendError(BackendErrorKind.AUTH, "401").retryable is False

    def test_retryable_can_be_set(self) -> None:
        error = BackendError(BackendErrorKind.RATE_LIMITED, "429", retryable=True)
        assert error.retryable is True

    def test_wrap_keeps_original_exception_as_cause(self) -> None:
        """转换等于在边界处「换衣服」：排障信息（原类型 / traceback）必须留在 cause 里，
        否则日志里只剩一句转述，后端内部错误无从定位。"""
        original = PiNotAvailableError("pi 不在 PATH")
        error = BackendError.wrap(original, BackendErrorKind.UNAVAILABLE)
        assert error.kind is BackendErrorKind.UNAVAILABLE
        assert error.__cause__ is original
        assert "pi 不在 PATH" in error.message

    def test_wrap_falls_back_to_exception_class_name_on_empty_message(self) -> None:
        """空消息的异常不能转出一条空白错误——用户会看到「运行失败：」。"""
        error = BackendError.wrap(ValueError(), BackendErrorKind.UNKNOWN)
        assert error.message == "ValueError"

    def test_pi_exceptions_map_onto_kinds(self) -> None:
        """迁移路径的映射表要真的成立：``PiNotAvailableError → UNAVAILABLE``、
        ``PoolQueueTimeoutError → BUSY``。两个原始异常都必须是 ``RuntimeError``
        子类，否则 ``BackendError`` 的基类选择就站不住。"""
        assert isinstance(PiNotAvailableError("x"), PiError)
        assert issubclass(PiNotAvailableError, RuntimeError)
        assert issubclass(PoolQueueTimeoutError, RuntimeError)

        unavailable = BackendError.wrap(PiNotAvailableError("x"), BackendErrorKind.UNAVAILABLE)
        busy = BackendError.wrap(PoolQueueTimeoutError("排队超时"), BackendErrorKind.BUSY, retryable=True)
        assert unavailable.kind is BackendErrorKind.UNAVAILABLE
        assert busy.kind is BackendErrorKind.BUSY
        assert busy.retryable is True


class _FakeHandle:
    """最小可实现控制柄：证明协议可被结构化满足，不碰任何真实进程。"""

    kind = "fake"

    def __init__(self, run_id: str = "run-1") -> None:
        self.run_id = run_id
        self.calls: list[tuple[str, str]] = []
        self.stats: dict[str, Any] = {}

    async def steer(self, message: str) -> str:
        self.calls.append(("steer", message))
        return "queued"

    async def follow_up(self, message: str) -> str:
        self.calls.append(("follow_up", message))
        return "queued"

    async def abort(self) -> bool:
        self.calls.append(("abort", ""))
        return True

    async def get_stats(self) -> dict[str, Any]:
        self.calls.append(("get_stats", ""))
        return self.stats


class TestLiveBackendHandle:
    def test_fake_handle_satisfies_protocol(self) -> None:
        assert isinstance(_FakeHandle(), LiveBackendHandle)

    def test_missing_abort_does_not_satisfy_protocol(self) -> None:
        """``runtime_checkable`` 只查属性存在性——少一个方法必须不通过，
        否则 HTTP 中止端点会在运行期 ``AttributeError``。"""

        class _NoAbort:
            kind = "fake"
            run_id = "run-1"

            async def steer(self, message: str) -> str:
                return "queued"

            async def follow_up(self, message: str) -> str:
                return "queued"

            async def get_stats(self) -> dict[str, Any]:
                return {}

        assert not isinstance(_NoAbort(), LiveBackendHandle)

    def test_handle_round_trip_through_protocol_typed_variable(self) -> None:
        """按协议类型使用（而不是按具体类）时，五个方法都取得到、都跑得通。"""
        handle: LiveBackendHandle = _FakeHandle(run_id="run-42")
        assert handle.run_id == "run-42"
        assert handle.kind == "fake"

        async def _drive() -> list[str]:
            return [
                await handle.steer("先看第 3 条"),
                await handle.follow_up("再补一个反例"),
                str(await handle.abort()),
            ]

        assert asyncio.run(_drive()) == ["queued", "queued", "True"]

    def test_pi_rpc_session_shape_can_be_wrapped(self) -> None:
        """pi 的 ``PiRpcSession`` 具备包成 handle 所需的全部方法名。

        不构造真实例（那要起子进程），只验证**协议结构**：
        steer / follow_up / abort / get_session_stats 都是协程方法，
        且 ``get_stats`` 只差一次改名转调（映射写进 ``PiBackend``）。
        """
        from apps.agent.pi.rpc_client import PiRpcSession

        for name in ("steer", "follow_up", "abort", "get_session_stats"):
            method = getattr(PiRpcSession, name)
            assert asyncio.iscoroutinefunction(method), f"PiRpcSession.{name} 必须是协程方法"

        # 协议要求 get_stats，pi 叫 get_session_stats——这一层差异由 PiBackend 抹平
        assert not hasattr(PiRpcSession, "get_stats")


class TestConcurrentInSessionCapability:
    def test_defaults_to_false(self) -> None:
        """默认不能并发：新后端没验证过就被并行拉起会污染会话上下文，
        且没有任何测试能提前发现。想并发必须显式声明。"""
        caps = BackendCapabilities(
            streaming=True,
            tool_calls=True,
            approval=True,
            compaction=True,
            steer=True,
        )
        assert caps.concurrent_in_session is False

    def test_old_construction_still_works(self) -> None:
        """加可选字段不能破坏既有构造方式（``PiBackend`` 等实现方按位置/关键字
        传五个必填字段的老代码必须原样可跑）。"""
        caps = BackendCapabilities(
            streaming=False,
            tool_calls=False,
            approval=False,
            compaction=False,
            steer=False,
        )
        assert (caps.streaming, caps.tool_calls, caps.approval, caps.compaction, caps.steer) == (
            False,
            False,
            False,
            False,
            False,
        )

    def test_can_be_declared_explicitly(self) -> None:
        caps = BackendCapabilities(
            streaming=True,
            tool_calls=True,
            approval=False,
            compaction=True,
            steer=True,
            concurrent_in_session=True,
        )
        assert caps.concurrent_in_session is True

    def test_stays_frozen(self) -> None:
        """能力是后端的静态属性：运行期改会让前端 UI 形态无法预判。"""
        from dataclasses import FrozenInstanceError

        caps = BackendCapabilities(
            streaming=True,
            tool_calls=True,
            approval=True,
            compaction=True,
            steer=True,
        )
        with pytest.raises(FrozenInstanceError):
            caps.concurrent_in_session = True  # type: ignore[misc]


class _BackendWithoutHandle:
    """不实现 ``make_handle`` 的后端：``make_handle`` 是**可选**方法。"""

    kind = "no-handle"
    capabilities = BackendCapabilities(
        streaming=False,
        tool_calls=False,
        approval=False,
        compaction=False,
        steer=False,
    )

    def stream(self, ctx: RunContext) -> Any:
        async def _gen() -> Any:
            yield {"type": "done", "session_id": str(ctx.session), "agent": self.kind, "run_id": ctx.run_id}

        return _gen()


class _BackendWithHandle(_BackendWithoutHandle):
    kind = "with-handle"

    def make_handle(self, ctx: RunContext, inner: Any) -> LiveBackendHandle | None:
        return _FakeHandle(run_id=ctx.run_id) if inner is not None else None


class TestMakeHandleIsOptional:
    def test_method_name_constant(self) -> None:
        """调用方统一按这个常量 ``getattr``，不各处硬编码字符串。"""
        assert MAKE_HANDLE_METHOD == "make_handle"

    def test_backend_without_make_handle_still_satisfies_protocol(self) -> None:
        """把 ``make_handle`` **写进协议** 会让所有不支持插话的后端失去协议资格
        （``runtime_checkable`` 只查属性存在性，写了就算必填），所以它只能留在
        协议外面做可选约定——这条断言就是这个决定的守卫。"""
        backend = _BackendWithoutHandle()
        assert isinstance(backend, AgentBackend)
        assert getattr(backend, MAKE_HANDLE_METHOD, None) is None

    def test_backend_with_make_handle_returns_usable_handle(self) -> None:
        backend = _BackendWithHandle()
        assert isinstance(backend, AgentBackend)
        make_handle = getattr(backend, MAKE_HANDLE_METHOD, None)
        assert callable(make_handle)

        handle = make_handle(_ctx(run_id="run-7"), inner=object())
        assert isinstance(handle, LiveBackendHandle)
        assert handle.run_id == "run-7"

    def test_make_handle_may_return_none(self) -> None:
        """返回 ``None`` = 这一轮不支持控制（例如后端本身没在跑）。"""
        handle = _BackendWithHandle().make_handle(_ctx(), inner=None)
        assert handle is None
