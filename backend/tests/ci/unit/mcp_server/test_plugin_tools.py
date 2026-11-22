"""``mcp_server.plugin_tools`` —— 插件自带 MCP 工具的发现与注册。

守的是四件**会静默出错**的事：

1. **有插件就有工具、没插件就没工具**。用户的原话是「如果用户有 plugins 文件夹，
   就应该能用上对应的 MCP 工具，反之就不能用」。这一条错了的表现是
   「插件装了但模型说没这个工具」（缺注册）或「插件没装但工具出现在列表里、
   一调就报错」（假存在）——两者都没有报错，只有律师觉得 AI 变笨。
2. **撞名以内置为准**。内置 409 个工具是审批与审计口径的基准；插件覆盖
   ``delete_case`` 这类名字等于绕开风险分级。
3. **坏插件不拖垮 MCP**。导入失败 / 契约不合法 / 可用性探针抛异常 → 跳过该插件，
   其余工具照常。MCP 起不来等于全所 AI 功能停摆。
4. **总开关能一键关**（回滚用）。

全部离线：不启 MCP、不 import 任何真实插件。
"""

from __future__ import annotations

import sys
import types
from collections.abc import Callable
from typing import Any

import pytest

from mcp_server import plugin_tools


def _fake_module(name: str, **attrs: Any) -> types.ModuleType:
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


def _register_into(collector: list[str]) -> Callable[[Callable[..., Any]], Any]:
    def _register(func: Callable[..., Any]) -> Any:
        collector.append(func.__name__)
        return func

    return _register


@pytest.fixture
def fake_discovery(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """按 ``{模块路径: 模块对象或异常}`` 布置发现结果。"""

    def _setup(mapping: dict[str, Any]) -> None:
        monkeypatch.setattr(plugin_tools, "discover_entry_modules", lambda: sorted(mapping))

        def _import(name: str) -> types.ModuleType:
            value = mapping[name]
            if isinstance(value, BaseException):
                raise value
            return value

        monkeypatch.setattr(plugin_tools.importlib, "import_module", _import)

    return _setup


# ── 开关 ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1", True), ("", True), ("on", True), ("0", False), ("off", False), ("FALSE", False)],
)
def test_enabled_switch(monkeypatch: pytest.MonkeyPatch, raw: str, expected: bool) -> None:
    monkeypatch.setenv(plugin_tools.ENABLED_ENV, raw)
    assert plugin_tools.enabled() is expected


def test_switch_off_registers_nothing(fake_discovery: Callable[..., None], monkeypatch: pytest.MonkeyPatch) -> None:
    def tool() -> None: ...

    fake_discovery({"plugins.x.mcp_tools": _fake_module("plugins.x.mcp_tools", MCP_TOOLS=[tool])})
    monkeypatch.setenv(plugin_tools.ENABLED_ENV, "off")

    got: list[str] = []
    assert plugin_tools.register_plugin_tools(_register_into(got)) == []
    assert got == []


# ── 发现 ──────────────────────────────────────────────────────────────


def test_discover_returns_empty_without_plugins(monkeypatch: pytest.MonkeyPatch) -> None:
    """没有 plugins 包时不能抛（未装插件的部署就是这样）。"""
    monkeypatch.setattr(plugin_tools, "plugins_root", lambda: None)
    assert plugin_tools.discover_entry_modules() == []


def test_discover_only_picks_dirs_with_entry_module(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "with_tools").mkdir()
    (tmp_path / "with_tools" / "mcp_tools.py").write_text("MCP_TOOLS = []")
    (tmp_path / "no_tools").mkdir()
    (tmp_path / "_private").mkdir()
    (tmp_path / "_private" / "mcp_tools.py").write_text("MCP_TOOLS = []")
    monkeypatch.setattr(plugin_tools, "plugins_root", lambda: str(tmp_path))

    found = plugin_tools.discover_entry_modules()
    # 前缀取「root 目录名」（真实部署里就是 ``plugins``），所以这里按 tmp_path 推。
    assert found == [f"{tmp_path.name}.with_tools.mcp_tools"]


# ── 注册 ──────────────────────────────────────────────────────────────


def test_registers_plugin_tools(fake_discovery: Callable[..., None]) -> None:
    def weike_search() -> None: ...

    fake_discovery({"plugins.p.mcp_tools": _fake_module("plugins.p.mcp_tools", MCP_TOOLS=[weike_search])})

    got: list[str] = []
    assert plugin_tools.register_plugin_tools(_register_into(got)) == ["weike_search"]
    assert got == ["weike_search"]


def test_skips_when_name_collides_with_builtin(fake_discovery: Callable[..., None]) -> None:
    def delete_case() -> None: ...

    def safe_read() -> None: ...

    fake_discovery({"plugins.p.mcp_tools": _fake_module("plugins.p.mcp_tools", MCP_TOOLS=[delete_case, safe_read])})

    got: list[str] = []
    registered = plugin_tools.register_plugin_tools(_register_into(got), reserved_names={"delete_case"})
    assert registered == ["safe_read"]
    assert "delete_case" not in got


def test_broken_plugin_does_not_break_registration(fake_discovery: Callable[..., None]) -> None:
    """一个插件 import 炸了，另一个照常注册。"""

    def good_tool() -> None: ...

    fake_discovery(
        {
            "plugins.broken.mcp_tools": ImportError("依赖没装"),
            "plugins.ok.mcp_tools": _fake_module("plugins.ok.mcp_tools", MCP_TOOLS=[good_tool]),
        }
    )

    got: list[str] = []
    assert plugin_tools.register_plugin_tools(_register_into(got)) == ["good_tool"]


def test_unavailable_plugin_is_not_registered(fake_discovery: Callable[..., None]) -> None:
    def tool() -> None: ...

    module = _fake_module("plugins.p.mcp_tools", MCP_TOOLS=[tool], check_available=lambda: False)
    fake_discovery({"plugins.p.mcp_tools": module})

    got: list[str] = []
    assert plugin_tools.register_plugin_tools(_register_into(got)) == []


def test_check_available_raising_counts_as_unavailable(fake_discovery: Callable[..., None]) -> None:
    def tool() -> None: ...

    def boom() -> bool:
        raise RuntimeError("凭据没配")

    module = _fake_module("plugins.p.mcp_tools", MCP_TOOLS=[tool], check_available=boom)
    fake_discovery({"plugins.p.mcp_tools": module})

    got: list[str] = []
    assert plugin_tools.register_plugin_tools(_register_into(got)) == []


def test_rejects_non_list_exports(fake_discovery: Callable[..., None]) -> None:
    fake_discovery({"plugins.p.mcp_tools": _fake_module("plugins.p.mcp_tools", MCP_TOOLS="not-a-list")})
    got: list[str] = []
    assert plugin_tools.register_plugin_tools(_register_into(got)) == []


def test_missing_exports_is_not_an_error(fake_discovery: Callable[..., None]) -> None:
    """插件只提供非工具能力（没有 MCP_TOOLS）是合法状态。"""
    fake_discovery({"plugins.p.mcp_tools": _fake_module("plugins.p.mcp_tools")})
    got: list[str] = []
    assert plugin_tools.register_plugin_tools(_register_into(got)) == []


def test_skips_non_callable_and_private_names(fake_discovery: Callable[..., None]) -> None:
    def _hidden() -> None: ...

    module = _fake_module("plugins.p.mcp_tools", MCP_TOOLS=["string", 42, _hidden])
    fake_discovery({"plugins.p.mcp_tools": module})

    got: list[str] = []
    assert plugin_tools.register_plugin_tools(_register_into(got)) == []


def test_duplicate_name_registered_once(fake_discovery: Callable[..., None]) -> None:
    def twin() -> None: ...

    module = _fake_module("plugins.p.mcp_tools", MCP_TOOLS=[twin, twin])
    fake_discovery({"plugins.p.mcp_tools": module})

    got: list[str] = []
    assert plugin_tools.register_plugin_tools(_register_into(got)) == ["twin"]
    assert got == ["twin"]


def test_sys_modules_is_not_polluted_by_test_modules() -> None:
    """守护用例自身：假模块只存在于 monkeypatch 的作用域内。"""
    assert not any(name.endswith(".mcp_tools") and name in sys.modules for name in ("plugins.p.mcp_tools",))
