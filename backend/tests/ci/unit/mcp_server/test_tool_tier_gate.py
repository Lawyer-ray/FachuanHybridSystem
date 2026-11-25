"""服务端工具面裁剪（``X-Fachuan-Tool-Tier``）的契约门禁。

## 为什么要有这道门禁

dsh 后端无法自己分层，只能靠服务端按请求头裁剪 ``tools/list``。这条链路有三类
静默失效，全部只能靠测试发现：

1. **改错对象**：中间件拿到的是 ``_serialize`` 之后的 wire dict。写
   ``result.tools = [...]``（pydantic 对象属性）**不报错但无效**——模型照样收
   434 个工具，账单照样 10.2 万 token，没有任何日志。
2. **破坏性工具被裁掉**：``lite`` 层靠 ``DIRECT_TOOLS`` + ``DIRECT_PATTERNS``
   命中。新增的 ``delete_xxx`` 一旦漏进长尾，模型在 ``lite`` 下就看不见"这个
   AI 有删除能力"——这是产品可见性红线，不是性能取舍。
3. **fail-closed**：拼错一个头值就返回空工具集，模型会说"我做不到"。

所以这里用**真实 ``MCPServer`` 实例**、走**完整中间件链**（``ServerRunner``
同款的 ``call_next`` 组合方式），断言的是最终 wire dict，而不是内部函数。
"""

from __future__ import annotations

import asyncio
import fnmatch
from collections.abc import Callable, Mapping
from typing import Any

import pytest

from mcp_server.tool_tier_gate import (
    TIER_FULL,
    TIER_LITE,
    TOOL_TIER_HEADER,
    ToolTierGateMiddleware,
    install_tool_tier_gate,
    is_direct_tool,
    requested_tier,
)
from mcp_server.tool_tiers import DIRECT_PATTERNS, DIRECT_TOOLS


class _Headers(Mapping[str, str]):
    """Starlette ``Headers`` 的最小替身：键小写化、取值大小写不敏感。"""

    def __init__(self, values: Mapping[str, str]) -> None:
        self._values = {key.lower(): value for key, value in values.items()}

    def __getitem__(self, key: str) -> str:
        return self._values[key.lower()]

    def __iter__(self) -> Any:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)


class _Request:
    """``ctx.request`` 的最小替身（真实形态是 Starlette ``Request``）。"""

    def __init__(self, headers: Mapping[str, str] | None) -> None:
        self.headers = None if headers is None else _Headers(headers)


class _Ctx:
    """``ServerRequestContext`` 的最小替身：中间件只读 ``method`` / ``request``。"""

    def __init__(self, method: str, headers: Mapping[str, str] | None = None) -> None:
        self.method = method
        self.request = None if headers is None else _Request(headers)


_CAPTURED: list[dict[str, Any]] = []


def _capture_tool_payloads() -> list[dict[str, Any]]:
    """真实 ``MCPServer`` 的 ``tools/list`` 结果（pydantic 模型 → wire dict），缓存一份。

    走 ``model_dump`` 是因为中间件实际看到的就是这个形态——用 dict 形状才能
    复现“赋值到 pydantic 属性无效”那个坑。434 个工具的 schema 串行化不便宜，
    缓存住让每个用例只付一次。
    """
    if _CAPTURED:
        return _CAPTURED[0]
    raise AssertionError(
        "_CAPTURED 未填充——应在模块加载时调 _prime_capture()，"
        "不要在事件循环里 asyncio.run（那会抛 'cannot be called from a running event loop'）"
    )


def _prime_capture() -> None:
    """模块加载时（同步上下文）捕获一次工具 payload。

    **不能 lazy capture**：``_run_chain`` 是 async，若在它内部调
    ``asyncio.run(mcp.list_tools())`` 会撞上「事件循环已在运行」。
    放在模块顶层最省事——pytest 的 collection 阶段是同步的，那时跑安全。
    434 个工具的序列化要几秒，所以只付一次（``_CAPTURED`` 缓存）。
    """
    if _CAPTURED:
        return
    from mcp_server.server import mcp

    tools = asyncio.run(mcp.list_tools())
    _CAPTURED.append(
        [
            {
                "name": tool.name,
                "description": tool.description or "",
                # 输出 schema 里含运行时类对象，``model_dump`` 会抛
                # ``Unable to serialize unknown type``（实测）——直接取 schema 字段。
                "inputSchema": tool.input_schema,
            }
            for tool in tools
        ]
    )


_prime_capture()


async def _run_chain(method: str, headers: Mapping[str, str] | None) -> dict[str, Any]:
    """跑一遍中间件链，返回 ``tools/list`` 的 wire dict。

    ``call_next`` 直接返回 handler 的序列化结果（与 ``ServerRunner._inner`` 一致：
    它在链内已 ``_serialize``）。用独立的 ``MCPServer`` 实例做被测服务器，
    避免污染全局 ``mcp`` 的中间件链。

    只组合**本模块挂上去的**中间件：链头那两道是 SDK 内置件（OpenTelemetry、
    ``RequestStateBoundary``），它们要消费完整的 ``ServerRequestContext``，
    而裁剪逻辑只依赖 ``method`` / ``request.headers`` —— 用最小替身即可，
    否则测试要伪造整个会话才能跑一次头解析。
    """
    from mcp.server.mcpserver import MCPServer

    from mcp_server.server import mcp as real_mcp

    server = MCPServer("裁剪测试", tools=real_mcp._tool_manager.list_tools())
    appended = install_tool_tier_gate(server)
    assert appended is True, "测试装置应能挂上中间件"
    gate = [item for item in server.middleware if isinstance(item, ToolTierGateMiddleware)]
    assert len(gate) == 1, f"应恰好挂上一道裁剪中间件，实得 {len(gate)}"

    # 先在链外把 payload 取好：``mcp.list_tools()`` 是协程，而链运行期间事件循环
    # 已被占着，不能再嵌套 ``asyncio.run``。
    payloads = _capture_tool_payloads()

    async def _inner(_ctx: Any) -> dict[str, Any]:
        return {"tools": payloads}

    result = await gate[0](_Ctx(method, headers), _inner)
    assert isinstance(result, dict), f"tools/list 结果应是 wire dict，实得 {type(result).__name__}"
    return result


def _names(result: Mapping[str, Any]) -> set[str]:
    return {str(tool["name"]) for tool in result["tools"]}


def _direct_names(all_names: set[str]) -> set[str]:
    return {name for name in all_names if is_direct_tool(name)}


class TestRequestedTier:
    """头解析：不带头 / 已知值 / 未知值三条分支。"""

    def test_missing_header_is_full(self) -> None:
        """不带头 → 全量。这是老客户端的兼容底线，动了就是全网回归。"""
        assert requested_tier(None) == TIER_FULL
        assert requested_tier(_Headers({})) == TIER_FULL

    def test_blank_header_is_full(self) -> None:
        """空串等价于不带头（有的客户端会把未设置的头写成空值）。"""
        assert requested_tier(_Headers({TOOL_TIER_HEADER: "   "})) == TIER_FULL

    @pytest.mark.parametrize("value", ["lite", "LITE", " Lite "])
    def test_lite_is_case_and_space_insensitive(self, value: str) -> None:
        assert requested_tier(_Headers({TOOL_TIER_HEADER: value})) == TIER_LITE

    def test_full_value_is_full(self) -> None:
        assert requested_tier(_Headers({TOOL_TIER_HEADER: "full"})) == TIER_FULL

    def test_unknown_value_falls_back_to_full(self, caplog: pytest.LogCaptureFixture) -> None:
        """未知值回退全量 + WARNING —— **不能** fail-closed 成空工具集。"""
        with caplog.at_level("WARNING", logger="mcp_server.tool_tier_gate"):
            tier = requested_tier(_Headers({TOOL_TIER_HEADER: "xyz"}))
        assert tier == TIER_FULL
        assert any("xyz" in record.getMessage() for record in caplog.records), (
            "未知头值必须留下 WARNING，否则线上拼错头无从排查"
        )


class TestToolsListFiltering:
    """走真实中间件链，断言最终 wire dict。"""

    def test_no_header_returns_all_tools(self) -> None:
        result = asyncio.run(_run_chain("tools/list", None))
        all_names = {str(tool["name"]) for tool in _capture_tool_payloads()}
        assert _names(result) == all_names, "不带头时必须全量返回（老客户端零影响）"

    def test_full_header_returns_all_tools(self) -> None:
        result = asyncio.run(_run_chain("tools/list", {TOOL_TIER_HEADER: "full"}))
        all_names = {str(tool["name"]) for tool in _capture_tool_payloads()}
        assert _names(result) == all_names

    def test_lite_header_returns_only_direct_tools(self) -> None:
        result = asyncio.run(_run_chain("tools/list", {TOOL_TIER_HEADER: "lite"}))
        all_names = {str(tool["name"]) for tool in _capture_tool_payloads()}
        assert _names(result) == _direct_names(all_names), "lite 必须精确等于直连层"

    def test_lite_is_strictly_smaller(self) -> None:
        """裁剪必须真的省下来——相等或更大说明过滤没生效（踩过 pydantic 赋值那个坑）。"""
        full = _names(asyncio.run(_run_chain("tools/list", None)))
        lite = _names(asyncio.run(_run_chain("tools/list", {TOOL_TIER_HEADER: "lite"})))
        assert lite < full, f"lite({len(lite)}) 不是 full({len(full)}) 的真子集"

    def test_lite_keeps_tool_envelope_fields(self) -> None:
        """只剪 ``tools``，其余 wire 字段（如 ``resultType``/``_meta``）必须留着。"""
        result = asyncio.run(_run_chain("tools/list", {TOOL_TIER_HEADER: "lite"}))
        assert set(result) == {"tools"}, f"意外的 wire 字段变化: {sorted(result)}"
        assert result["tools"], "lite 层不能为空"
        assert all("inputSchema" in tool for tool in result["tools"]), "工具条目结构必须完整"

    def test_unknown_header_returns_all_tools(self) -> None:
        result = asyncio.run(_run_chain("tools/list", {TOOL_TIER_HEADER: "xyz"}))
        all_names = {str(tool["name"]) for tool in _capture_tool_payloads()}
        assert _names(result) == all_names, "未知口径必须回退全量，不能返回空工具集"

    def test_other_methods_are_untouched(self) -> None:
        """非 ``tools/list`` 方法（这里用 ``tools/call`` 走同一条链）不受影响。"""
        result = asyncio.run(_run_chain("tools/call", {TOOL_TIER_HEADER: "lite"}))
        all_names = {str(tool["name"]) for tool in _capture_tool_payloads()}
        assert _names(result) == all_names


class TestLiteKeepsDestructiveTools:
    """安全断言：``lite`` 必须包含全部直连清单与全部破坏性工具。"""

    def test_lite_contains_every_direct_tool(self) -> None:
        result = asyncio.run(_run_chain("tools/list", {TOOL_TIER_HEADER: "lite"}))
        lite = _names(result)
        missing = sorted(DIRECT_TOOLS - lite)
        assert not missing, f"直连清单里的工具被裁掉了: {missing}"

    def test_lite_contains_every_pattern_match(self) -> None:
        """任何 ``delete_*`` / ``remove_*`` 命中项都必须在 ``lite`` 里。

        防「新增一个 ``delete_xxx`` 之后 lite 看不见删除能力」——清单用模式而
        不是枚举就是为了自动覆盖新工具，这道断言把这个自动性钉死。
        """
        result = asyncio.run(_run_chain("tools/list", {TOOL_TIER_HEADER: "lite"}))
        lite = _names(result)
        all_names = {str(tool["name"]) for tool in _capture_tool_payloads()}
        matched = {name for name in all_names if any(fnmatch.fnmatchcase(name, p) for p in DIRECT_PATTERNS)}
        assert matched, "注册表里没有任何模式命中项，断言失去意义"
        missing = sorted(matched - lite)
        assert not missing, f"破坏性工具被裁出 lite 层（律师将看不到 AI 的删除能力）: {missing}"


class TestGateSwitch:
    """``FACHUAN_MCP_TOOL_TIER_GATE`` 一键回滚。"""

    def test_enabled_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from mcp_server.tool_tier_gate import gate_enabled

        monkeypatch.delenv("FACHUAN_MCP_TOOL_TIER_GATE", raising=False)
        assert gate_enabled() is True

    def test_off_switch_passes_full_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """关掉开关后，即使带 ``lite`` 也必须拿到全量（出问题时不改代码就回滚）。"""
        monkeypatch.setenv("FACHUAN_MCP_TOOL_TIER_GATE", "off")
        result = asyncio.run(_run_chain("tools/list", {TOOL_TIER_HEADER: "lite"}))
        all_names = {str(tool["name"]) for tool in _capture_tool_payloads()}
        assert _names(result) == all_names

    def test_invalid_value_falls_back_to_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from mcp_server.tool_tier_gate import gate_enabled

        monkeypatch.setenv("FACHUAN_MCP_TOOL_TIER_GATE", "maybe")
        assert gate_enabled() is True


class TestIdempotentInstall:
    """共享进程里重复挂载不能把中间件挂两遍。"""

    def test_second_install_is_noop(self) -> None:
        from mcp.server.mcpserver import MCPServer

        server = MCPServer("幂等测试")
        before = len(server.middleware)
        assert install_tool_tier_gate(server) is True
        assert install_tool_tier_gate(server) is False
        assert len(server.middleware) == before + 1

    def test_installed_middleware_is_the_shared_singleton(self) -> None:
        from mcp.server.mcpserver import MCPServer

        server = MCPServer("单例测试")
        install_tool_tier_gate(server)
        assert sum(isinstance(item, ToolTierGateMiddleware) for item in server.middleware) == 1
