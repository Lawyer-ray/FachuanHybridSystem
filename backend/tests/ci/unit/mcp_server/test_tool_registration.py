"""工具注册完整性:tools/ 里定义的 public 工具必须全部在 server.py 注册。

## 背景

400 个工具靠 ``mcp.tool()(fn)`` 手工注册,写完工具忘注册没有任何报错——
症状与「改了 mcp_server 没重启共享 MCP」一模一样(模型说没有这个工具),
但根因在代码里,重启也没用。``make mcp-verify`` 只对比「代码注册表 vs
线上」,同样覆盖不到「定义了却没注册」。

## 白名单

内部 helper(被其他模块 import,本就不是工具)必须列在这里;新增 helper
请用 ``_`` 前缀命名,不要进白名单。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_MCP_ROOT = Path(__file__).resolve().parents[4] / "mcp_server"

#: 非工具的 public 函数(内部 helper),每项注明用途
_HELPER_WHITELIST = {
    "available_skill_names",  # core/agent_skills.py: skills 列表去重源
    "content_type_for",  # documents/parsing.py: 按扩展名推 content-type
    "project",  # core/projection.py: 列表投影原语
    "project_list",  # core/projection.py: 列表投影原语
    "project_page",  # core/projection.py: 分页投影原语
}


def _defined_public_functions() -> dict[str, str]:
    """工具定义区的 public 函数: name -> 相对路径。

    扫描 ``mcp_server/tools/``(主工具面)与 ``apps/*/mcp/``(业务模块自带
    工具,如 workflow)。``async def`` 与普通函数一视同仁——async 工具同样
    要注册,漏扫会造成门禁盲区(web_search 就是 async)。
    """
    roots = [_MCP_ROOT / "tools"] + sorted((_MCP_ROOT.parent / "apps").glob("*/mcp"))
    defined: dict[str, str] = {}
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text())
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
                    defined.setdefault(node.name, str(path.relative_to(_MCP_ROOT.parent)))
    return defined


def _registered_names() -> set[str]:
    """server.py 里注册的工具名集合。

    支持两种形态:
    - ``mcp.tool()(fn)`` —— 直接注册
    - ``mcp.tool()(_workflow_tool(fn))`` —— workflow 包装(参数剥离 + 业务
      异常翻译),取内层函数名
    """

    def _target_name(call_arg: ast.AST) -> str | None:
        if isinstance(call_arg, ast.Name):
            return call_arg.id
        if isinstance(call_arg, ast.Call) and isinstance(call_arg.func, ast.Name):
            if call_arg.func.id in {"_mcp_only", "_workflow_tool"} and call_arg.args and isinstance(call_arg.args[0], ast.Name):
                return call_arg.args[0].id
        return None

    def _is_registration_call(node: ast.Call) -> bool:
        # 统一注册口 ``_t(fn)``(2026-10-25 起,带 ToolAnnotations 推导);
        # 兼容识别旧形态 ``mcp.tool()(fn)``,防有人绕过 _t 仍能被对账。
        outer = node.func
        if isinstance(outer, ast.Name) and outer.id == "_t":
            return True
        return (
            isinstance(outer, ast.Call)
            and isinstance(outer.func, ast.Attribute)
            and outer.func.attr == "tool"
            # 精确裸形态 mcp.tool()(fn):_t 定义体内的
            # mcp.tool(annotations=...)(func) 不算注册
            and not outer.args
            and not outer.keywords
        )

    server = ast.parse((_MCP_ROOT / "server.py").read_text())
    registered: set[str] = set()
    for node in ast.walk(server):
        if not (isinstance(node, ast.Call) and node.args):
            continue
        if _is_registration_call(node):
            name = _target_name(node.args[0])
            if name:
                registered.add(name)
    return registered


def test_no_unregistered_tools() -> None:
    defined = _defined_public_functions()
    registered = _registered_names()
    unregistered = sorted(set(defined) - registered - _HELPER_WHITELIST)
    assert not unregistered, (
        f"以下函数在 tools/ 实现完整但从未在 server.py 注册（模型看不到它们）: "
        f"{ {name: defined[name] for name in unregistered} }。"
        "若是有意注册,补进 mcp/server.py;若是内部 helper,加 _ 前缀或补测试白名单。"
    )


def test_registration_count_matches_registry() -> None:
    """注册总数与线上工具面一致,防止注册面意外缩水。"""
    registered = _registered_names()
    assert len(registered) == 415, (
        f"注册工具数 {len(registered)} != 409。新增/删除工具时同步更新该基线数"
        "（2026-10-25: 410→409→415, 删除 auto_namer_process 后新增 6 个记忆工具）"
        "（本测试防的是「注册面静默缩水」,正常增删改数字即可）。"
    )


def test_whitelist_entries_still_exist() -> None:
    """白名单里的名字必须仍存在——防止 helper 改名后白名单变成误放的逃生门。"""
    defined = _defined_public_functions()
    stale = sorted(_HELPER_WHITELIST - set(defined))
    assert not stale, f"白名单中的名字已不存在于 tools/,请移除: {stale}"


@pytest.mark.parametrize("name", sorted(_HELPER_WHITELIST))
def test_whitelisted_helpers_are_used(name: str) -> None:
    """白名单成员必须真的被使用——跨模块引用,或被同模块其他函数调用。

    否则它可能只是个忘注册的工具,白名单成了逃生门。
    """
    defined = _defined_public_functions()
    defining_path = _MCP_ROOT.parent / defined[name]
    tree = ast.parse(defining_path.read_text())

    # (a) 同文件内其他函数调用了它（如 project_list 委托 project）
    used_locally = any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name
        for other in tree.body
        if isinstance(other, (ast.FunctionDef, ast.AsyncFunctionDef)) and other.name != name
        for node in ast.walk(other)
    )
    # (b) 工具定义区其他文件引用了该名字
    roots = [_MCP_ROOT / "tools"] + sorted((_MCP_ROOT.parent / "apps").glob("*/mcp"))
    used_externally = any(
        name in other_path.read_text() and other_path != defining_path
        for root in roots
        for other_path in root.rglob("*.py")
        if "__pycache__" not in other_path.parts
    )
    assert used_locally or used_externally, f"白名单成员 {name} 无任何使用者——它可能是忘注册的工具"
