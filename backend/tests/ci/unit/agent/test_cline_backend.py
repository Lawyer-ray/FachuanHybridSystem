"""``ClineBackend`` —— 第八个后端的接缝、帧翻译、能力声明与故障注入。

全部离线（不打网关、不连共享 MCP、不起 node）：

1. **身份与能力**：``kind == "cline"``；``streaming`` / ``tool_calls`` 为真（bridge 实测
   有 ``content_start(text)`` 增量与 ``contentType:"tool"`` 事件）；``approval`` 恒
   ``False``（cline 自己的 ``ToolApprovalRequest`` 未接线，这是事实不是待办）。
2. **工具名归一化**：``fachuan__asean_law_countries`` → ``mcp__fachuan__asean_law_countries``。
   不归一化时 ``short_tool_name`` 只认 ``mcp__fachuan__`` 前缀，写类工具会静默降级成低风险。
3. **帧翻译**：桥的 ``delta`` / ``usage`` / ``tool_call`` / ``tool_result`` → 契约帧；
   同一 ``tool_call_id`` 只发一次 ``tool_call``。
4. **故障注入**：node 或桥脚本缺失 → ``available=False``；桥路径不存在时
   ``stream()`` 报 ``UNAVAILABLE``（不是 UNKNOWN）。
5. **取消不是错误**：``_pump`` 被取消时原样抛 ``CancelledError``（包成 ``BackendError``
   会让 ``AgentRun`` 把「用户按停止」记成失败）。
6. **收尾事实**：``result_for`` 取得到模型、且有界。
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest

from apps.agent.backends import cline_backend as mod
from apps.agent.backends import registry
from apps.agent.backends.base import AgentBackend, BackendError, BackendErrorKind, RunContext


def _ctx(**kw: Any) -> RunContext:
    base: dict[str, Any] = {
        "run_id": "run-cline-test",
        "session": SimpleNamespace(session_id="sess-cline-test"),
        "user_id": 1,
        "prompt": "hello",
        "user_token": "tok",
        "model": None,
        "tool_selection": None,
    }
    base.update(kw)
    return RunContext(**base)


class TestIdentity:
    def test_kind_is_stable(self) -> None:
        assert mod.ClineBackend().kind == "cline"

    def test_capabilities_are_facts(self) -> None:
        caps = mod.backend_capabilities() if hasattr(mod, "backend_capabilities") else mod.ClineBackend().capabilities
        assert caps.streaming is True
        assert caps.tool_calls is True
        # cline 的 ToolApprovalRequest 未接线：不能声称有闸门（MCP 服务端闸门仍兜底）
        assert caps.approval is False
        assert caps.steer is False
        assert caps.concurrent_in_session is True

    def test_satisfies_protocol(self) -> None:
        assert isinstance(mod.ClineBackend(), AgentBackend)


class TestToolName:
    def test_fachuan_prefix(self) -> None:
        assert mod.normalize_tool_name("fachuan__asean_law_countries") == (
            "asean_law_countries",
            "mcp__fachuan__asean_law_countries",
        )

    def test_other_server_kept_verbatim(self) -> None:
        assert mod.normalize_tool_name("memory__search") == ("search", "memory__search")

    def test_already_canonical(self) -> None:
        assert mod.normalize_tool_name("mcp__fachuan__delete_case") == ("delete_case", "mcp__fachuan__delete_case")

    def test_empty(self) -> None:
        assert mod.normalize_tool_name("") == ("", "")


class TestFrames:
    def setup_method(self) -> None:
        self.backend = mod.ClineBackend()
        self.announced: set[str] = set()

    def test_delta(self) -> None:
        assert self.backend._frame("delta", {"content": "你好"}, self.announced) == {"type": "delta", "content": "你好"}

    def test_usage(self) -> None:
        frame = self.backend._frame(
            "usage",
            {"input_tokens": 10, "output_tokens": 2, "cache_read_tokens": 5, "cache_write_tokens": 1},
            self.announced,
        )
        assert frame == {
            "type": "usage",
            "input_tokens": 10,
            "output_tokens": 2,
            "cache_read_tokens": 5,
            "cache_write_tokens": 1,
        }

    def test_tool_call_normalized_and_deduped(self) -> None:
        msg = {"tool_call_id": "c1", "name": "fachuan__delete_case", "arguments": {"id": 1}}
        first = self.backend._frame("tool_call", msg, self.announced)
        assert first is not None
        assert first["name"] == "delete_case"
        assert "id" in (first["arguments"] or "")
        assert self.backend._frame("tool_call", msg, self.announced) is None

    def test_tool_result(self) -> None:
        frame = self.backend._frame(
            "tool_result",
            {"tool_call_id": "c1", "name": "fachuan__x", "result": "ok", "is_error": True},
            self.announced,
        )
        assert frame == {"type": "tool_result", "tool_call_id": "c1", "name": "x", "result": "ok", "is_error": True}

    def test_unknown_kind_ignored(self) -> None:
        assert self.backend._frame("ready", {}, self.announced) is None


class TestAvailabilityAndFailure:
    def test_unavailable_without_bridge(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        monkeypatch.setattr(mod, "bridge_path", lambda: tmp_path / "missing.mjs")
        assert mod.is_available() is False

    def test_stream_reports_unavailable(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        monkeypatch.setattr(mod, "bridge_path", lambda: tmp_path / "missing.mjs")
        backend = mod.ClineBackend()

        async def _run() -> None:
            await backend._resolve_gateway(_ctx())  # 网关解析在桥检查之前会成功/失败都行
            async for _ in backend._stream(_ctx()):
                pass

        with pytest.raises(BackendError):
            asyncio.run(_run())


class _FakeProc:
    """``asyncio.subprocess.Process`` 的最小替身：只给 ``_pump`` 用的 stdout。"""

    def __init__(self, lines: list[bytes]) -> None:
        self._lines = list(lines)
        self.returncode = None
        self.stdin = None

    @property
    def stdout(self) -> Any:
        outer = self

        class _Reader:
            async def readline(self) -> bytes:
                if not outer._lines:
                    return b""
                return outer._lines.pop(0)

        return _Reader()


class TestPump:
    def test_translates_until_done(self) -> None:
        backend = mod.ClineBackend()
        proc = _FakeProc(
            [
                json.dumps({"type": "ready"}).encode() + b"\n",
                json.dumps({"type": "delta", "content": "12"}).encode() + b"\n",
                json.dumps({"type": "tool_call", "tool_call_id": "c1", "name": "fachuan__x"}).encode() + b"\n",
                json.dumps({"type": "done", "reason": "completed"}).encode() + b"\n",
            ]
        )

        async def _collect() -> list[dict[str, Any]]:
            return [f async for f in backend._pump(_ctx(), proc, set())]

        frames = asyncio.run(_collect())
        assert [f["type"] for f in frames] == ["delta", "tool_call"]
        assert all(f["agent"] == "cline" for f in frames)

    def test_bridge_error_raises_backend_error(self) -> None:
        backend = mod.ClineBackend()
        proc = _FakeProc([json.dumps({"type": "error", "message": "boom"}).encode() + b"\n"])

        async def _collect() -> None:
            async for _ in backend._pump(_ctx(), proc, set()):
                pass

        with pytest.raises(BackendError) as excinfo:
            asyncio.run(_collect())
        assert excinfo.value.kind == BackendErrorKind.UNKNOWN

    def test_cancel_propagates(self) -> None:
        """用户按停止 → CancelledError 原样上抛，不包成 BackendError。"""
        backend = mod.ClineBackend()

        class _SlowProc(_FakeProc):
            @property
            def stdout(self) -> Any:
                class _Reader:
                    async def readline(self) -> bytes:
                        await asyncio.sleep(10)
                        return b""

                return _Reader()

        async def _scenario() -> None:
            task = asyncio.ensure_future(_anext(backend._pump(_ctx(), _SlowProc([]), set())))
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        asyncio.run(_scenario())


async def _anext(agen: Any) -> Any:
    return await agen.__anext__()


class TestResultFor:
    def test_roundtrip_and_bound(self) -> None:
        backend = mod.ClineBackend()
        backend._remember_result("r1", mod.ClineRunResult(model="kimi-2.6"))
        assert backend.result_for("r1") is not None
        assert backend.result_for("r1").model == "kimi-2.6"
        assert backend.result_for("nope") is None
        for i in range(mod.MAX_KEPT_RESULTS + 3):
            backend._remember_result(f"x{i}", mod.ClineRunResult(model="m"))
        assert len(backend._results) == mod.MAX_KEPT_RESULTS


class TestMcp:
    def test_headers_carry_three_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 必须把「端口是否在听」钉死：``_mcp`` 会真探 127.0.0.1:8011（``port_open``），
        # CI runner 上没有共享 MCP 在听，不打桩这条用例在 CI 必红（本地开发机常驻 MCP，
        # 所以本地一直绿——这就是它「只在 CI 红」的原因）。同 test_antigravity_backend.py 的写法。
        monkeypatch.setattr(mod, "port_open", lambda *_a, **_k: True)
        monkeypatch.setattr(mod, "shared_enabled", lambda: True)
        url, headers = mod.ClineBackend()._mcp(_ctx(), "sess-1")
        assert url and url.endswith("/mcp")
        assert headers["Authorization"] == "Bearer tok"
        assert headers[mod.SESSION_HEADER] == "sess-1"
        assert headers[mod.TOOL_TIER_HEADER] in {mod.TIER_FULL, mod.TIER_LITE}

    def test_no_token_no_toolface(self) -> None:
        assert mod.ClineBackend()._mcp(_ctx(user_token=""), "sess-1") == (None, {})


class TestRegistration:
    def test_registers_when_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(mod, "is_available", lambda: True)
        registry.clear()
        try:
            from apps.agent.backends import builtin

            builtin._attempted.discard("cline")
            builtin.ensure_registered()
            assert "cline" in registry.available_kinds()
        finally:
            registry.clear()
            builtin._registered = False
