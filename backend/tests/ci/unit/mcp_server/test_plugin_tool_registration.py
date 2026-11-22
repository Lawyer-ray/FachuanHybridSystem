"""``mcp_server.server`` 里插件注册的两处接线：内置名单自记账、插件注解按声明下发。

1. ``_builtin_tool_names`` 不再读 FastMCP 私有的 ``mcp._tool_manager``：SDK 升级改名时
   那条路会静默返回空集合，「插件撞名以内置为准」随之失效（插件可以覆盖 ``delete_case``）。
2. ``_t(func, annotations=...)``：插件按声明的风险等级传注解，``_t`` 必须原样用它，
   而不是按名字重新推导（否则「未声明 = 高危」在注册这一步就被抹掉）。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from mcp.types import ToolAnnotations


def test_builtin_tool_names_does_not_touch_private_tool_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp_server import server

    # 换成一个没有 ``_tool_manager`` 的对象：修复前这里会 AttributeError
    monkeypatch.setattr(server, "mcp", SimpleNamespace())
    names = server._builtin_tool_names()

    assert "delete_case" in names
    assert len(names) >= 400


def test_builtin_tool_names_is_a_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    """返回副本：之后（插件）再经 ``_t`` 注册，先前拿到的名单不能跟着变。"""
    from mcp_server import server

    monkeypatch.setattr(server, "_REGISTERED_TOOL_NAMES", {"list_cases"})
    snapshot = server._builtin_tool_names()
    server._REGISTERED_TOOL_NAMES.add("plugin_tool")
    assert snapshot == {"list_cases"}


class _FakeMcp:
    """只记录 ``mcp.tool(annotations=...)`` 收到的注解，不真注册。"""

    def __init__(self) -> None:
        self.annotations: dict[str, Any] = {}

    def tool(self, *, annotations: Any = None) -> Any:
        def _decorate(func: Any) -> Any:
            self.annotations[func.__name__] = annotations
            return func

        return _decorate


def test_t_uses_given_annotations_for_plugin_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp_server import server

    fake = _FakeMcp()
    monkeypatch.setattr(server, "mcp", fake)
    monkeypatch.setattr(server, "_REGISTERED_TOOL_NAMES", set())

    def search_private_cases() -> dict[str, Any]:
        return {}

    declared = ToolAnnotations(destructive_hint=True)
    server._t(search_private_cases, annotations=declared)

    assert fake.annotations["search_private_cases"] is declared
    assert "search_private_cases" in server._REGISTERED_TOOL_NAMES


def test_t_without_annotations_keeps_name_derivation(monkeypatch: pytest.MonkeyPatch) -> None:
    """内置工具不传注解：仍按 ``_tool_annotations`` 由名字推导（行为不变）。

    ``_tool_annotations`` 用桩顶掉：真实实现会经 ``classify_risk`` 懒加载注解表，
    而那张表从 ``mcp_server.server.mcp`` 读——此刻它是假对象，会把进程级缓存写成空表。
    """
    from mcp_server import server

    fake = _FakeMcp()
    derived = ToolAnnotations(read_only_hint=True)
    monkeypatch.setattr(server, "mcp", fake)
    monkeypatch.setattr(server, "_REGISTERED_TOOL_NAMES", set())
    monkeypatch.setattr(server, "_tool_annotations", lambda name: derived)

    def list_cases() -> dict[str, Any]:
        return {}

    server._t(list_cases)

    assert fake.annotations["list_cases"] is derived
