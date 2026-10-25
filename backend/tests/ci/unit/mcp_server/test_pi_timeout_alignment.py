"""双端超时漂移门禁:pi 侧 mcp.json timeout 必须大于工具面最大 client 超时。

背景(2026-10-25 三十七轮审计):慢链路工具(LLM 生成/威科/企业数据
provider 链)client 侧统一 ``timeout=180``,其前提是 pi 侧 mcp.json 的
``timeout: 200`` 比它大——pi 每请求超时会先掐断,client 侧的 180 全部
作废(工具白跑,pi 报给模型的只是超时)。这个双端关系此前只活在
shared_mcp.py 的注释里:谁加一个 ``timeout=240`` 的工具,pi 的 200 会
无声地先杀掉它,且没有任何测试亮红灯。

本门禁机械钉死:①扫出 tools/ 下全部显式 client 超时取最大值;
②shared_mcp.py 里每个 mcp server 配置的 ``"timeout": N`` 字面量都必须
严格大于该最大值。任一端漂移(工具加码/pi 减码)即失败。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[4]
_TOOLS_DIR = _BACKEND / "mcp_server" / "tools"
_SHARED_MCP_PY = _BACKEND / "apps" / "agent" / "pi" / "shared_mcp.py"

#: 扫描器自证下界:当前工具面已有 26+ 处显式超时(LLM 12/企业 10/慢端点 4),
#: 数量骤降说明扫描器或工具面被改坏,而不是真的没人需要超时。
_MIN_TIMEOUT_CALLS = 20


def _max_tool_client_timeout() -> tuple[float, int]:
    """扫 tools/ 下全部 client.<method>(..., timeout=N) 的字面量,返回(最大值,处数)。"""
    values: list[float] = []
    for py in sorted(_TOOLS_DIR.rglob("*.py")):
        if py.name == "__init__.py":
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if not (isinstance(node.func.value, ast.Name) and node.func.value.id == "client"):
                continue
            for kw in node.keywords:
                if kw.arg != "timeout":
                    continue
                v = getattr(kw.value, "value", None)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    values.append(float(v))
    return (max(values) if values else 0.0), len(values)


def test_pi_mcp_timeout_exceeds_every_tool_client_timeout() -> None:
    max_tool_timeout, count = _max_tool_client_timeout()
    assert count >= _MIN_TIMEOUT_CALLS, (
        f"显式 client 超时只剩 {count} 处(<{_MIN_TIMEOUT_CALLS})——扫描器坏了,还是工具面被改坏?"
    )
    source = _SHARED_MCP_PY.read_text(encoding="utf-8")
    pi_timeouts = [float(m) for m in re.findall(r'"timeout":\s*([0-9]+(?:\.[0-9]+)?)', source)]
    assert pi_timeouts, "shared_mcp.py 里没找到 mcp server 配置的 timeout 字面量(写法变了?)"
    for i, pi_t in enumerate(pi_timeouts, 1):
        assert pi_t > max_tool_timeout, (
            f"pi 侧 timeout={pi_t}(第 {i} 处) ≤ 工具面最大 client 超时 {max_tool_timeout:g}s"
            f"——pi 会先掐断,client 的超时配置全部作废;把 shared_mcp.py 的 timeout 抬到 "
            f">{max_tool_timeout:g}(留传输余量,当前惯例 +20)"
        )


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
