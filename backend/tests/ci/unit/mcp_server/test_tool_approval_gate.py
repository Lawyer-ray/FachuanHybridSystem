"""服务端审批闸门（入口 B）的契约门禁。

## 为什么要有这道门禁

闸门是本分支唯一「先判后调」的中间件，三类静默失效都只有测试能发现：

1. **假拦截**：照抄 ``tool_tier_gate`` 的「先 ``call_next`` 后过滤」顺序，工具
   已经真执行了、再返回「需要审批」。用户看到"被拦住了"，数据已经删了。
   核心断言因此是 **handler 调用 0 次**，不是"返回了 isError"。
2. **fail-open**：拿不到会话 id、审批服务抛错、台账读失败时顺手放行。
   这些都是"拦不住"，必须逐条钉死。
3. **台账不单次消费**：一次审批放行多次调用（Redis 里 ``get`` + ``delete``
   两步走，并发重试都能命中）。台账必须删掉才算命中。

装置沿用 ``test_tool_tier_gate.py`` 的做法：构造最小 ``ctx`` + ``call_next``，
只组合本模块挂上去的中间件（链头那两道 SDK 内置件要完整会话，与本闸门无关）。
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

import pytest
from django.core.cache import cache
from pydantic import BaseModel

import mcp_server.tool_approval_gate as gate_module
from apps.agent.services.approval import RiskLevel, classify_risk
from mcp_server.identity import request_authorization, request_session_id
from mcp_server.tool_approval_gate import (
    GATE_ENV,
    MODE_DRY,
    MODE_OFF,
    WAIT_ENV,
    annotations_for,
    grant_key,
    install_tool_approval_gate,
)

#: 低风险工具（只读注解 + 无写前缀）：必须直通。
LOW_TOOL = "get_case"
#: 高危工具（``delete`` 命中 DANGER_PATTERNS）：必须拦。
HIGH_TOOL = "delete_case"


def _install_on_fake_server() -> SimpleNamespace:
    """模块加载期把闸门挂到一个假 server 上，同时**预热注解快照**。

    ``install_tool_approval_gate`` 会调 ``prime_tool_annotations()``，那一步读
    MCP 工具表是同步的；放在模块加载期（``asyncio.run`` 之前）才安全——
    在事件循环里懒加载会起线程 ``join(10)``（见 ``approval/annotations.py``）。
    """
    server = SimpleNamespace(middleware=[])
    assert install_tool_approval_gate(server) is True, "测试装置应能挂上中间件"
    return server


_SERVER = _install_on_fake_server()
GATE = next(item for item in _SERVER.middleware if isinstance(item, gate_module.ToolApprovalGateMiddleware))


class _Ctx:
    """``ServerRequestContext`` 的最小替身：闸门只读 ``method`` / ``params``。"""

    def __init__(self, method: str, params: Mapping[str, Any] | None = None) -> None:
        self.method = method
        self.params = params


class _ApprovalRecorder:
    """替身 ``request_approval``：记录入参，按预设结论返回 ``(approved, id, reason)``。"""

    def __init__(
        self,
        approved: bool,
        approval_id: str = "",
        reason: str = "用户拒绝或超时",
    ) -> None:
        self.approved = approved
        self.approval_id = approval_id
        self.reason = reason
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> tuple[bool, str, str]:
        self.calls.append(kwargs)
        return self.approved, self.approval_id, self.reason


def _wire(result: Any) -> dict[str, Any]:
    """中间件返回值 → 线上 wire dict（``ServerRunner._dump_result`` 的口径）。"""
    if isinstance(result, BaseModel):
        return result.model_dump(by_alias=True, mode="json", exclude_none=True)
    assert isinstance(result, dict), f"闸门返回了意外的类型: {type(result).__name__}"
    return result


def _run_chain(
    method: str,
    tool_name: str,
    tool_args: Mapping[str, Any] | None,
    *,
    called: list[dict[str, Any]],
) -> dict[str, Any]:
    """跑一遍「闸门 + handler」链，返回最终 wire dict。

    ``called`` 是 handler 的调用记录——**拦截路径必须留空**，这是本门禁的
    核心断言（把"先执行再返回需审批"的假拦截钉死）。
    """

    async def _inner(_ctx: Any) -> dict[str, Any]:
        called.append({"tool": tool_name, "args": dict(tool_args or {})})
        return {"content": [{"type": "text", "text": "已执行"}], "isError": False}

    params = None if method != "tools/call" else {"name": tool_name, "arguments": dict(tool_args or {})}
    return _wire(asyncio.run(GATE(_Ctx(method, params), _inner)))


def _text_of(result: Mapping[str, Any]) -> str:
    return str(result["content"][0]["text"])


@pytest.fixture(autouse=True)
def _clean_gate_env(monkeypatch: pytest.MonkeyPatch) -> Any:
    """每个用例：清开关、清身份 ContextVar、清缓存（台账是进程级 LocMem）。"""
    monkeypatch.delenv(GATE_ENV, raising=False)
    monkeypatch.delenv(WAIT_ENV, raising=False)
    token_session = request_session_id.set("")
    token_auth = request_authorization.set("")
    cache.clear()
    yield
    cache.clear()
    request_session_id.reset(token_session)
    request_authorization.reset(token_auth)


class TestRiskPremises:
    """先把「这两个工具分别判什么级」钉死，后面的用例才有意义。"""

    def test_low_tool_is_low(self) -> None:
        level = classify_risk(LOW_TOOL, {"case_id": 1}, annotations=annotations_for(LOW_TOOL))
        assert level is RiskLevel.LOW

    def test_high_tool_is_high(self) -> None:
        level = classify_risk(HIGH_TOOL, {"case_id": 1}, annotations=annotations_for(HIGH_TOOL))
        assert level in gate_module.BLOCKING_LEVELS, f"{HIGH_TOOL} 应命中拦截等级，实得 {level}"

    def test_annotations_snapshot_is_pre_generated(self) -> None:
        """注解快照必须非空——空表说明退回了纯名字判定，是灰度时要看见的信号。"""
        assert gate_module._TOOL_ANNOTATIONS, "启动时预生成的注解快照为空（classify_risk 会退回纯名字判定）"


class TestPassThrough:
    """不该拦的路径一律直通，且不发起任何审批。"""

    def test_low_risk_tool_runs_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        recorder = _ApprovalRecorder(approved=False)
        monkeypatch.setattr(gate_module, "request_approval", recorder)
        called: list[dict[str, Any]] = []

        result = _run_chain("tools/call", LOW_TOOL, {"case_id": 1}, called=called)

        assert len(called) == 1, "低风险工具必须真的执行"
        assert result.get("isError") is False
        assert not recorder.calls, "低/中风险免审批（与 flow.py 同一口径）"

    def test_off_mode_is_transparent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(GATE_ENV, MODE_OFF)
        recorder = _ApprovalRecorder(approved=False)
        monkeypatch.setattr(gate_module, "request_approval", recorder)
        called: list[dict[str, Any]] = []

        result = _run_chain("tools/call", HIGH_TOOL, {"case_id": 7}, called=called)

        assert len(called) == 1, "off = 完全透传（一键回滚）"
        assert result.get("isError") is False
        assert not recorder.calls

    def test_dry_mode_logs_and_does_not_block(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv(GATE_ENV, MODE_DRY)
        recorder = _ApprovalRecorder(approved=False)
        monkeypatch.setattr(gate_module, "request_approval", recorder)
        called: list[dict[str, Any]] = []

        with caplog.at_level("WARNING", logger="mcp_server.tool_approval_gate"):
            result = _run_chain("tools/call", HIGH_TOOL, {"case_id": 7}, called=called)

        assert len(called) == 1, "dry 只观察不拦"
        assert result.get("isError") is False
        assert not recorder.calls, "dry 模式不该发起审批"
        assert any("[dry]" in record.getMessage() for record in caplog.records), (
            "dry 模式必须留下 WARNING，否则灰度时看不出会拦掉什么"
        )

    def test_non_tools_call_methods_untouched(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``tools/list`` 等方法零影响（尤其不能把工具面弄脏）。"""
        recorder = _ApprovalRecorder(approved=False)
        monkeypatch.setattr(gate_module, "request_approval", recorder)
        called: list[dict[str, Any]] = []

        result = _run_chain("tools/list", HIGH_TOOL, {}, called=called)

        assert len(called) == 1
        assert result.get("isError") is False
        assert not recorder.calls


class TestBlocking:
    """核心：高危工具在未获批准前**一次都不能执行**。"""

    def test_high_risk_without_grant_never_runs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        approval_id = "abcd1234" * 4
        recorder = _ApprovalRecorder(approved=False, approval_id=approval_id, reason="用户拒绝或超时")
        monkeypatch.setattr(gate_module, "request_approval", recorder)
        called: list[dict[str, Any]] = []

        result = _run_chain("tools/call", HIGH_TOOL, {"case_id": 7}, called=called)

        assert called == [], "命中拦截时绝不能调 call_next（先执行再返回「需审批」是假拦截）"
        assert result.get("isError") is True, "业务失败必须走 isError"
        assert "error" not in result, "禁止 return {'error': ...} 假装成功"
        text = _text_of(result)
        assert f"approval_id={approval_id}" in text, "文案必须带上审批单号，否则律师对不上卡"
        assert "不要重复调用" in text and "原样重试一次" in text, f"缺少可执行指引: {text}"
        assert len(recorder.calls) == 1
        assert recorder.calls[0]["tool_name"] == HIGH_TOOL
        assert recorder.calls[0]["tool_args"] == {"case_id": 7}

    def test_blocked_without_session_header(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """dsh / openai-agents 不带 ``X-Fachuan-Session``：仍要拦，不许 fail-open。"""
        recorder = _ApprovalRecorder(
            approved=False, approval_id="f" * 32, reason="无人在线且不允许离线审批，按拒绝处理"
        )
        monkeypatch.setattr(gate_module, "request_approval", recorder)
        called: list[dict[str, Any]] = []

        result = _run_chain("tools/call", HIGH_TOOL, {"case_id": 7}, called=called)

        assert called == [], "没有会话头不是放行理由"
        assert result.get("isError") is True
        assert recorder.calls[0]["session_id"] is None, "空串必须归一成 None（审批内核按 None 走无会话分支）"

    def test_session_id_is_forwarded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        request_session_id.set("sess-abc")
        recorder = _ApprovalRecorder(approved=False, approval_id="0" * 32)
        monkeypatch.setattr(gate_module, "request_approval", recorder)
        called: list[dict[str, Any]] = []

        _run_chain("tools/call", HIGH_TOOL, {"case_id": 7}, called=called)

        assert recorder.calls[0]["session_id"] == "sess-abc", "审批卡要推到对的会话通道"

    def test_wait_timeout_is_capped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """等待上限 ``min(env, 150)``：再大也会比客户端 200s 超时先返回。"""
        monkeypatch.setenv(WAIT_ENV, "300")
        recorder = _ApprovalRecorder(approved=False, approval_id="1" * 32)
        monkeypatch.setattr(gate_module, "request_approval", recorder)
        called: list[dict[str, Any]] = []

        _run_chain("tools/call", HIGH_TOOL, {"case_id": 7}, called=called)

        assert recorder.calls[0]["timeout"] == gate_module.MAX_WAIT_SECONDS == 150.0

    def test_approval_failure_is_fail_closed(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """审批服务抛错（ORM/Redis/未知）→ 拒绝 + WARNING，绝不回滚成放行。"""

        async def _boom(**kwargs: Any) -> tuple[bool, str, str]:
            raise RuntimeError("redis 挂了")

        monkeypatch.setattr(gate_module, "request_approval", _boom)
        called: list[dict[str, Any]] = []

        with caplog.at_level("WARNING", logger="mcp_server.tool_approval_gate"):
            result = _run_chain("tools/call", HIGH_TOOL, {"case_id": 7}, called=called)

        assert called == [], "异常路径也必须拦住"
        assert result.get("isError") is True
        assert "fail-closed" in _text_of(result)
        assert any(record.levelno >= 30 for record in caplog.records), "异常必须留 WARNING（不许 debug 吞掉）"


class TestGrantLedger:
    """台账：批准后原样重试直接过，且**单次消费**。"""

    def test_grant_lets_one_retry_through_and_is_consumed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        recorder = _ApprovalRecorder(approved=False, approval_id="2" * 32)
        monkeypatch.setattr(gate_module, "request_approval", recorder)
        key = grant_key(HIGH_TOOL, {"case_id": 7})
        cache.set(key, "earlier-approval", gate_module.GRANT_TTL)
        called: list[dict[str, Any]] = []

        first = _run_chain("tools/call", HIGH_TOOL, {"case_id": 7}, called=called)

        assert len(called) == 1, "台账命中要直接放行"
        assert first.get("isError") is False
        assert not recorder.calls, "台账命中不该再发起审批"
        assert cache.get(key) is None, "台账必须被消费（单次放行）"

        second = _run_chain("tools/call", HIGH_TOOL, {"case_id": 7}, called=called)

        assert len(called) == 1, "台账消费后第二次必须重新走审批"
        assert second.get("isError") is True
        assert len(recorder.calls) == 1

    def test_approval_granted_writes_grant_for_client_retry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """批准后执行；客户端 200s 超时重试同一调用应直接放行，不再弹第二张卡。"""
        recorder = _ApprovalRecorder(approved=True, approval_id="3" * 32, reason="用户同意")
        monkeypatch.setattr(gate_module, "request_approval", recorder)
        called: list[dict[str, Any]] = []

        first = _run_chain("tools/call", HIGH_TOOL, {"case_id": 7}, called=called)
        retry = _run_chain("tools/call", HIGH_TOOL, {"case_id": 7}, called=called)

        assert len(called) == 2, "批准后 + 重试各执行一次"
        assert first.get("isError") is False and retry.get("isError") is False
        assert len(recorder.calls) == 1, "重试走台账，不该再发起一次审批"

    def test_grant_for_other_args_does_not_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """批准的是「删 A 案」，不能拿同一张台账去执行「删 B 案」。"""
        recorder = _ApprovalRecorder(approved=False, approval_id="4" * 32)
        monkeypatch.setattr(gate_module, "request_approval", recorder)
        cache.set(grant_key(HIGH_TOOL, {"case_id": 2}), "earlier-approval", gate_module.GRANT_TTL)
        called: list[dict[str, Any]] = []

        result = _run_chain("tools/call", HIGH_TOOL, {"case_id": 1}, called=called)

        assert called == [], "参数不同的调用必须重新走审批"
        assert result.get("isError") is True
        assert len(recorder.calls) == 1

    def test_grant_key_separates_args_and_identity(self) -> None:
        """台账按「人 + 工具 + 参数」隔离：批准删 A 案不等于能删 B 案，也不跨人。"""
        assert grant_key(HIGH_TOOL, {"case_id": 1}) != grant_key(HIGH_TOOL, {"case_id": 2})
        token = request_authorization.set("Bearer token-A")
        try:
            key_a = grant_key(HIGH_TOOL, {"case_id": 1})
        finally:
            request_authorization.reset(token)
        token = request_authorization.set("Bearer token-B")
        try:
            key_b = grant_key(HIGH_TOOL, {"case_id": 1})
        finally:
            request_authorization.reset(token)
        assert key_a != key_b, "不同律师必须各有各的台账"
        assert key_a.startswith(gate_module.GRANT_KEY_PREFIX)
