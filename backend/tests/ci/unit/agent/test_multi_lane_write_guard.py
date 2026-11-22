"""多栏并答的**写降级**：工具面摘除 + 审批层兜底拒写。

## 为什么这条缺陷必须两层一起修

三栏同时改同一份 docx 时，谁先落盘，其余栏手里的 `original` 就失效——落笔要么
失败（看起来像模型笨），要么在别处撞上同一串字、改错位置。两层缺一不可：

1. **工具面**（pi）：写类工具从 `--tools` 里摘掉（`--exclude-tools`），模型
   干脆看不到它们。pi 的 `--tools` 是正向白名单、不支持排除语法，所以必须
   新增一个 CLI 参数位。
2. **审批层**（所有后端）：dsh / openai-agents 的工具面不走 `--exclude-tools`，
   它们仍然能发起 `rewrite_folder_file`；审批层看到「多栏 + 写类工具」直接拒绝
   并且**不弹审批卡**——三栏同时改文件是结构性冲突，让人去"批准"它没有意义。

## 单栏必须逐字不变

单栏（只有一栏在跑）时两个新字段保持默认：`_build_args` 的输出与引入本功能前
**逐字一致**（下面把旧参数列表固化成断言），`RunContext.multi_lane is False`、
`tool_exclude is None`。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Sequence
from typing import Any

import pytest

from apps.agent.backends import BackendCapabilities, RunContext, register
from apps.agent.backends import registry as registry_module
from apps.agent.models import AgentApproval, AgentSession
from apps.agent.pi import rpc_client
from apps.agent.services.approval.policy import (
    MULTI_LANE_WRITE_TOOLS,
    clear_multi_lane_session,
    is_multi_lane_session,
    mark_multi_lane_session,
    multi_lane_write_refusal,
)
from apps.agent.services.chat import budget, multi
from apps.agent.services.chat import stream as stream_module

PRIMARY = "fake-primary"
SECONDARY = "fake-secondary"
THIRD = "fake-third"

_CAPS = BackendCapabilities(streaming=True, tool_calls=False, approval=False, compaction=False, steer=False)

#: 写类工具的短名 → pi 口径全名（`--exclude-tools` 按全名匹配）
WRITE_TOOL_FULL_NAMES = frozenset(f"mcp__fachuan__{name}" for name in MULTI_LANE_WRITE_TOOLS)


class _CtxCapturingBackend:
    """把每栏 `RunContext` 记下来的假后端（只吐一条 delta，不起子进程）。"""

    def __init__(self, kind: str, captured: list[RunContext]) -> None:
        self.kind = kind
        self.capabilities = _CAPS
        self._captured = captured

    def stream(self, ctx: RunContext) -> AsyncGenerator[dict[str, Any] | None, None]:
        self._captured.append(ctx)
        return self._stream()

    async def _stream(self) -> AsyncGenerator[dict[str, Any] | None, None]:
        await asyncio.sleep(0)
        yield {"type": "delta", "content": "ok"}


@pytest.fixture(autouse=True)
def _isolated_registry(monkeypatch: pytest.MonkeyPatch) -> Any:
    """注册表/aux 计数是进程内全局状态：每条用例前后清空（同 test_multi_interleave）。"""
    registry_module.clear()
    budget._budget.reset()
    monkeypatch.setattr(stream_module, "ensure_registered", lambda: None)
    monkeypatch.setattr(multi, "ensure_registered", lambda: None)
    monkeypatch.delenv("FACHUAN_AGENT_AUX_SLOTS", raising=False)
    monkeypatch.delenv("FACHUAN_AGENT_AUX_RATIO", raising=False)
    yield
    registry_module.clear()
    budget._budget.reset()


async def _make_session() -> AgentSession:
    return await AgentSession.objects.acreate(title="多栏写降级", agent_kind=PRIMARY)


async def _collect_multi(kinds: Sequence[str]) -> list[RunContext]:
    captured: list[RunContext] = []
    for kind in kinds:
        register(_CtxCapturingBackend(kind, captured))
    session = await _make_session()
    async for _event in multi.stream_multi(session=session, user_message="合同有效吗", user_id=None, kinds=list(kinds)):
        pass
    return captured


class TestPiArgs:
    """`--exclude-tools` 只在真的给了排除项时出现，且位置稳定。"""

    @staticmethod
    def _session(exclude: frozenset[str] | None) -> rpc_client.PiRpcSession:
        return rpc_client.PiRpcSession(
            cwd="/tmp",
            extension_path="/ext/approval-gate.ts",
            tool_selection=rpc_client.TOOL_SELECTION,
            exclude_tools=exclude,
        )

    def test_args_are_byte_identical_without_exclusion(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """单栏/无排除时的启动参数与引入本功能前**逐字一致**（旧列表固化在这里）。"""
        monkeypatch.setattr(rpc_client, "resolve_extensions", lambda primary=None, **_kw: [primary or "/ext/approval-gate.ts"])
        legacy = [
            "pi",
            "--mode",
            "rpc",
            "--approve",
            "--tools",
            rpc_client.TOOL_SELECTION,
            "--extension",
            "/ext/approval-gate.ts",
            "--no-session",
            "--no-skills",
        ]
        assert self._session(None)._build_args("pi") == legacy
        assert self._session(frozenset())._build_args("pi") == legacy

    def test_exclusion_is_appended_after_tools(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(rpc_client, "resolve_extensions", lambda primary=None, **_kw: [primary or "/ext/approval-gate.ts"])
        args = self._session(frozenset({"mcp__fachuan__rewrite_folder_file"}))._build_args("pi")
        index = args.index("--exclude-tools")
        assert args[index - 2 : index] == ["--tools", rpc_client.TOOL_SELECTION]
        assert args[index + 1] == "mcp__fachuan__rewrite_folder_file"


class TestRunContextDefaults:
    def test_defaults_are_single_lane(self) -> None:
        ctx = RunContext(run_id="r", session=None, user_id=None, prompt="p", user_token="t", model=None, tool_selection=None)
        assert ctx.multi_lane is False
        assert ctx.tool_exclude is None


class TestToolFace:
    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_single_lane_keeps_tool_face_unchanged(self) -> None:
        captured = await _collect_multi([PRIMARY])
        assert [ctx.multi_lane for ctx in captured] == [False]
        assert [ctx.tool_exclude for ctx in captured] == [None]

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_three_lanes_lose_write_tools(self) -> None:
        captured = await _collect_multi([PRIMARY, SECONDARY, THIRD])
        assert len(captured) == 3
        assert all(ctx.multi_lane for ctx in captured)
        assert {ctx.tool_exclude for ctx in captured} == {WRITE_TOOL_FULL_NAMES}
        # 写类工具确实不在这批名字里（摘除的是真名，不是写错的前缀）
        assert "mcp__fachuan__rewrite_folder_file" in WRITE_TOOL_FULL_NAMES
        assert "mcp__fachuan__propose_write_patch" not in WRITE_TOOL_FULL_NAMES

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_write_tool_names_exist_in_mcp_registry(self) -> None:
        """`MULTI_LANE_WRITE_TOOLS` 写错名字 = 工具面摘不掉（且没有人会报错）。"""
        from mcp_server.server import mcp

        registered = set(mcp._tool_manager._tools)
        missing = sorted(MULTI_LANE_WRITE_TOOLS - registered)
        assert not missing, f"写类工具名不在 MCP 注册表里（摘除会静默失效）: {missing}"
        assert "propose_write_patch" in registered


class TestApprovalBackstop:
    """审批层：多栏时写类工具直接拒写，**不弹审批卡**（dsh / openai-agents 的兜底）。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_multi_lane_write_tool_is_refused_without_approval_card(self) -> None:
        from apps.agent.services.approval import request_approval

        mark_multi_lane_session("s-multi")
        try:
            approved, approval_id, reason = await request_approval(
                tool_name="mcp__fachuan__rewrite_folder_file",
                tool_args={"subpath": "1-合同/a.docx"},
                user_id=None,
                session_id="s-multi",
            )
        finally:
            clear_multi_lane_session("s-multi")

        assert approved is False
        assert approval_id == ""
        # 拒绝原因必须可执行：告诉模型该改用哪个工具，而不是只说"不行"
        assert "propose_write_patch" in reason
        # 不弹卡 = 一条 AgentApproval 都不该落
        assert await AgentApproval.objects.acount() == 0

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_multi_lane_read_tool_is_not_refused(self) -> None:
        from apps.agent.services.approval import request_approval

        mark_multi_lane_session("s-multi")
        try:
            approved, _approval_id, _reason = await request_approval(
                tool_name="mcp__fachuan__list_cases", session_id="s-multi"
            )
        finally:
            clear_multi_lane_session("s-multi")
        assert approved is True  # 低风险读工具照常放行

    @pytest.mark.django_db(transaction=True)
    def test_registering_then_clearing_restores_single_lane(self) -> None:
        mark_multi_lane_session("s-1")
        assert is_multi_lane_session("s-1") is True
        clear_multi_lane_session("s-1")
        assert is_multi_lane_session("s-1") is False
        assert multi_lane_write_refusal(session_id="s-1", tool_name="mcp__fachuan__rewrite_folder_file") is None

    @pytest.mark.django_db(transaction=True)
    def test_two_rounds_are_counted_not_boolean(self) -> None:
        """同一会话并发两轮：先收尾的那一轮不能把仍在跑的多栏轮判成单栏。"""
        mark_multi_lane_session("s-2")
        mark_multi_lane_session("s-2")
        clear_multi_lane_session("s-2")
        assert is_multi_lane_session("s-2") is True
        clear_multi_lane_session("s-2")
        assert is_multi_lane_session("s-2") is False

    def test_no_session_is_never_multi_lane(self) -> None:
        assert multi_lane_write_refusal(session_id=None, tool_name="mcp__fachuan__rewrite_folder_file") is None
