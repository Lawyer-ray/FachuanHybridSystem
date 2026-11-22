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
5. **风险等级只认插件声明**：没声明（或声明非法）的工具按高危注册（每次都要审批），
   只有显式声明 ``read`` 的才直接放行；等级经 MCP 注解进入 ``classify_risk``。

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


def _register_into(
    collector: list[str], annotations: dict[str, Any] | None = None
) -> Callable[..., Any]:
    """模拟 ``server._t``：记下注册了谁，以及插件侧给它算出来的注解。"""

    def _register(func: Callable[..., Any], **kwargs: Any) -> Any:
        collector.append(func.__name__)
        if annotations is not None:
            annotations[func.__name__] = kwargs.get("annotations")
        return func

    return _register


def _hints(annotation: Any) -> dict[str, Any]:
    """``ToolAnnotations`` → 审批内核认的注解字典（与 ``approval.annotations`` 同形）。"""
    return {
        "read_only_hint": getattr(annotation, "read_only_hint", None),
        "destructive_hint": getattr(annotation, "destructive_hint", None),
        "open_world_hint": getattr(annotation, "open_world_hint", None),
    }


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


# ── 风险等级 ──────────────────────────────────────────────────────────


def test_risk_aliases_align_with_risk_level() -> None:
    """插件可写的等级最终必须落在审批分级 ``RiskLevel`` 的取值里（两边口径对账）。"""
    from apps.agent.services.approval import RiskLevel

    assert set(plugin_tools.RISK_ALIASES.values()) <= {level.value for level in RiskLevel}
    assert plugin_tools.UNDECLARED_RISK == RiskLevel.HIGH.value


def test_undeclared_tool_registers_as_high_risk(fake_discovery: Callable[..., None]) -> None:
    """名字看着是只读（``search_``），但没声明 → 按高危注册：插件实现主仓看不到。"""
    from apps.agent.services.approval import RiskLevel, classify_risk

    def search_private_cases() -> None: ...

    fake_discovery({"plugins.p.mcp_tools": _fake_module("plugins.p.mcp_tools", MCP_TOOLS=[search_private_cases])})

    got: list[str] = []
    annotations: dict[str, Any] = {}
    assert plugin_tools.register_plugin_tools(_register_into(got, annotations)) == ["search_private_cases"]

    annotation = annotations["search_private_cases"]
    assert annotation is not None and annotation.destructive_hint is True
    assert annotation.read_only_hint is not True
    # 修复前：注解按名字推导成只读 → LOW，直接执行
    assert classify_risk("search_private_cases", annotations=_hints(annotation)) == RiskLevel.HIGH


@pytest.mark.parametrize(
    ("declared", "expected_level"),
    [("read", "low"), ("low", "low"), ("write", "medium"), ("medium", "medium"), ("high", "high")],
)
def test_declared_risk_drives_classification(
    fake_discovery: Callable[..., None], declared: str, expected_level: str
) -> None:
    from apps.agent.services.approval import classify_risk

    def lookup_private_cases() -> None: ...

    module = _fake_module(
        "plugins.p.mcp_tools",
        MCP_TOOLS=[lookup_private_cases],
        MCP_TOOL_RISK={"lookup_private_cases": declared},
    )
    fake_discovery({"plugins.p.mcp_tools": module})

    annotations: dict[str, Any] = {}
    plugin_tools.register_plugin_tools(_register_into([], annotations))

    annotation = annotations["lookup_private_cases"]
    assert classify_risk("lookup_private_cases", annotations=_hints(annotation)).value == expected_level
    # 注解与审批分级一致：只读 ⇔ low；写（非只读）必须显式 destructive=False / True
    assert (annotation.read_only_hint is True) == (expected_level == "low")
    if expected_level != "low":
        assert annotation.destructive_hint is (expected_level == "high")


def test_declared_read_cannot_downgrade_dangerous_name(fake_discovery: Callable[..., None]) -> None:
    """名字判定仍是第二层：声明 ``read`` 也拦不住 ``delete_`` 前缀被判高危。"""
    from apps.agent.services.approval import RiskLevel, classify_risk

    def delete_private_record() -> None: ...

    module = _fake_module(
        "plugins.p.mcp_tools",
        MCP_TOOLS=[delete_private_record],
        MCP_TOOL_RISK={"delete_private_record": "read"},
    )
    fake_discovery({"plugins.p.mcp_tools": module})

    annotations: dict[str, Any] = {}
    plugin_tools.register_plugin_tools(_register_into([], annotations))
    level = classify_risk("delete_private_record", annotations=_hints(annotations["delete_private_record"]))
    assert level in (RiskLevel.HIGH, RiskLevel.CRITICAL)


@pytest.mark.parametrize("bad_table", ["read", ["read"], {"tool": "maybe"}, {"tool": None}])
def test_invalid_risk_declaration_falls_back_to_high(
    fake_discovery: Callable[..., None], bad_table: Any
) -> None:
    def tool() -> None: ...

    module = _fake_module("plugins.p.mcp_tools", MCP_TOOLS=[tool], MCP_TOOL_RISK=bad_table)
    fake_discovery({"plugins.p.mcp_tools": module})

    annotations: dict[str, Any] = {}
    assert plugin_tools.register_plugin_tools(_register_into([], annotations)) == ["tool"]
    assert annotations["tool"].destructive_hint is True


def test_declared_risks_normalizes_case_and_whitespace() -> None:
    module = _fake_module("plugins.p.mcp_tools", MCP_TOOL_RISK={"a": " READ ", "b": "Write", "c": "nope"})
    assert plugin_tools.declared_risks(module) == {"a": "low", "b": "medium"}
