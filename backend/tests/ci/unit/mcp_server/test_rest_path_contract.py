"""MCP 工具 REST 路径契约测试 —— 工具里写的每一条路径/方法都必须是后端真实端点。

## 与 ``test_output_contract.py`` 的分工

已有测试只取每个**已注册**工具函数源码里的**第一处** ``client.*`` 调用做校验，
因此有三个盲区，本文件补全：

1. **多调用工具的后续调用**（先 GET 再 POST 的编排类工具，第二处起不查）；
2. **未注册的 helper 函数**（被多个工具转调的内部函数，其路径无人校验）；
3. **动态构造的路径**（局部变量 / ``template.format()``，旧测试直接跳过）。

本文件用 AST 对 ``mcp_server/tools/**`` 做**全量**扫描：每一处 ``client.<verb>``
调用都提取「路径模板 + HTTP 方法」，与 Django Ninja 生成的 OpenAPI 精确比对。
零网络、零数据库、零工具调用——写操作/贵操作工具（Playwright、LLM 链）也全覆盖。

## 历史教训

- 路径漂移是静默的：后端路由一改，MCP 层照常注册，模型照常选中，运行时
  才 404——没有 import 错误、没有启动报错。
- 2026-10 实测：393 条可比对路径全绿，但 ``client.download`` 写死 ``.get()``
  不认 ``method="POST"``，9 个文书下载工具（授权/保全/起诉状）一调用就
  TypeError——**意图正确 ≠ client 层能执行**，所以本文件校验「意图」，
  ``test_client.py`` 校验「执行」，两层都要有。

## 动态路径白名单

AST 无法静态求值的路径构造必须显式登记（``_DYNAMIC_ALLOWED``），其真实
目标由 ``test_known_dynamic_targets_exist`` 逐条硬校验。新增动态构造时，
测试会失败并提示：先验证目标端点存在，再登记——让每个「不可静态校验」
都是有意为之。
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[4]
_MCP_TOOLS = _BACKEND / "mcp_server" / "tools"

#: client 上需要校验的 REST 方法（与 FachuanClient 的公开方法一一对应）
_VERBS = frozenset({"get", "post", "put", "patch", "delete", "upload", "download"})

#: OpenAPI path 里的 ``{param}`` 占位符
_PARAM_RE = re.compile(r"\{[^}]*\}")

#: 动态构造、无法静态校验路径的调用点：(文件相对 mcp_server/ 的路径, 表达式片段)。
#: 只核对到「文件 + 表达式前缀」，行号会漂移不进白名单。
_DYNAMIC_ALLOWED = frozenset(
    {
        # owner_kind 三元选择后存入局部变量：真实目标在
        # test_known_dynamic_targets_exist 里以 /cases|/contracts 两分支硬校验
        ("tools/contracts/folder_file.py", "path"),
        # _KINDS 字典模板 + .format()：真实目标同样硬校验
        ("tools/core/tasks.py", "template.format(task_id=task_id)"),
    }
)

#: 下限护栏：提取量或端点数骤降说明 AST 扫描/注册表失效，全绿是假象
_MIN_COMPARABLE_CALLS = 350
_MIN_OPENAPI_PATHS = 400


@dataclass
class RestCall:
    """一处 ``client.<verb>(path)`` 调用的静态信息。"""

    file: str  # 相对 mcp_server/ 的路径
    line: int
    verb: str  # client 方法名大写（GET/POST/.../DOWNLOAD/UPLOAD）
    method: str | None  # 期望的真实 HTTP 方法（None = 未知，跳过方法比对）
    template: str  # 路径模板，占位统一为 {}
    kind: str  # literal | template | dynamic


@dataclass
class Extraction:
    calls: list[RestCall] = field(default_factory=list)

    @property
    def comparable(self) -> list[RestCall]:
        """可静态比对：非动态、非外部 URL。"""
        return [c for c in self.calls if c.kind != "dynamic" and not c.template.startswith(("http://", "https://"))]

    @property
    def dynamic(self) -> list[RestCall]:
        return [c for c in self.calls if c.kind == "dynamic"]


def _module_str_constants(tree: ast.Module) -> dict[str, str]:
    """模块级 ``NAME = "literal"`` 常量表（用于解析 ``client.get(_URL)`` 这类引用）。"""
    table: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    table[target.id] = node.value.value
    return table


def _template_of(node: ast.expr, constants: dict[str, str]) -> tuple[str, str]:
    """把实参 AST 归一为 (kind, template)。f-string 的插值统一成 ``{}``。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return "literal", node.value
    if isinstance(node, ast.Name) and node.id in constants:
        return "literal", constants[node.id]
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            else:
                parts.append("{}")
        return "template", "".join(parts)
    return "dynamic", ast.unparse(node)


def _extract_calls() -> Extraction:
    """AST 全量扫描 tools/**，提取每一处 client.<verb>(path) 调用。"""
    result = Extraction()
    for path in sorted(_MCP_TOOLS.glob("**/*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants = _module_str_constants(tree)
        rel = str(path.relative_to(_BACKEND / "mcp_server"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr not in _VERBS:
                continue
            if not (isinstance(node.func.value, ast.Name) and node.func.value.id == "client"):
                continue
            arg: ast.expr | None = node.args[0] if node.args else None
            if arg is None:
                arg = next((kw.value for kw in node.keywords if kw.arg in ("path", "url")), None)
            if arg is None:
                continue
            kind, template = _template_of(arg, constants)
            method_kw: str | None = None
            for kw in node.keywords:
                if kw.arg == "method" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    method_kw = kw.value.value
                    break
            result.calls.append(RestCall(rel, node.lineno, node.func.attr.upper(), method_kw, template, kind))
    return result


def _canonical(path: str) -> tuple[str, ...]:
    """路径 → 段元组（去 api/v1 前缀，``{param}`` 段统一成 ``{}``）。"""
    segments = [s for s in path.strip("/").split("/") if s]
    if segments[:2] == ["api", "v1"]:
        segments = segments[2:]
    return tuple(_PARAM_RE.sub("{}", s) for s in segments)


def _expected_method(call: RestCall) -> str | None:
    """调用期望的真实 HTTP 方法：method= 显式指定优先，download 缺省 GET，upload=POST。"""
    if call.method:
        return call.method.upper()
    if call.verb == "DOWNLOAD":
        return "GET"
    if call.verb == "UPLOAD":
        return "POST"
    return call.verb


@pytest.fixture(scope="module")
def openapi_index() -> dict[tuple[str, ...], set[str]]:
    """OpenAPI 路径索引：段元组 → 可用方法集合。不打网络。"""
    from apiSystem.api import api

    schema = json.loads(json.dumps(api.get_openapi_schema(), default=str))
    index: dict[tuple[str, ...], set[str]] = {}
    for path, ops in schema.get("paths", {}).items():
        methods = {m.lower() for m in ops if m.lower() in {"get", "post", "put", "patch", "delete"}}
        index.setdefault(_canonical(path), set()).update(methods)
    return index


@pytest.fixture(scope="module")
def extraction() -> Extraction:
    return _extract_calls()


def _mismatches(calls: list[RestCall], index: dict[tuple[str, ...], set[str]]) -> list[str]:
    failures: list[str] = []
    for call in calls:
        key = _canonical(call.template)
        methods = index.get(key)
        if methods is None:
            prefix = "/".join(key[:3])
            hint = sorted({"/".join(k) for k in index if "/".join(k[:3]) == prefix})[:4]
            failures.append(f"{call.file}:{call.line} 路径不存在: {call.template} (verb={call.verb}) 近似端点: {hint}")
            continue
        expected = _expected_method(call)
        if expected and expected.lower() not in methods:
            failures.append(
                f"{call.file}:{call.line} 方法不匹配: {call.template} 期望 {expected}，端点只有 {sorted(methods)}"
            )
    return failures


# 插件提供的端点前缀。`plugins/` 不入库（私有代码/submodule），CI 里装不到，
# 于是 apiSystem 用 try/except ImportError 跳过了这些 router —— 端点不存在是
# **环境差异**而非「工具写错路径」。不排除的话这条测试在 CI 上必然失败。
_PLUGIN_PATH_PREFIXES = (
    "/court-filing",
    "/court-guarantee",
    # 同属 plugins/court_automation，挂在真的 /automation 前缀下
    # （apps/automation/api/__init__.py 里同样 try/except ImportError 条件注册）。
    # 只剔这个具体子路径，不能剔整个 /automation——那是应用自己的路由。
    "/automation/preservation-quotes",
)


def test_all_tool_rest_paths_exist_in_backend(
    extraction: Extraction, openapi_index: dict[tuple[str, ...], set[str]]
) -> None:
    """每一处静态可解析的 client.* 调用，其路径与方法都必须是后端真实端点。"""
    comparable = extraction.comparable
    assert len(comparable) >= _MIN_COMPARABLE_CALLS, (
        f"可比对调用仅 {len(comparable)} 条（护栏 {_MIN_COMPARABLE_CALLS}），疑似 AST 扫描失效"
    )
    # 插件端点：装不上就跳过（本地有插件时照常硬校验）
    plugin_prefixes = tuple(pre.strip("/") for pre in _PLUGIN_PATH_PREFIXES)
    plugin_installed = any(
        any(str(seg).startswith(plugin_prefixes) for seg in path) for path in openapi_index
    )
    if not plugin_installed:
        comparable = [
            c for c in comparable if not str(c.template).startswith(_PLUGIN_PATH_PREFIXES)
        ]
    failures = _mismatches(comparable, openapi_index)
    assert not failures, "MCP 工具引用了后端不存在的端点（运行时静默 404）:\n" + "\n".join(f"  - {f}" for f in failures)


def test_dynamic_paths_are_consciously_allowed(extraction: Extraction) -> None:
    """动态构造的路径必须显式登记——新增动态写法时强迫作者先验证再放行。"""
    actual = {(c.file, c.template) for c in extraction.dynamic}
    assert actual == _DYNAMIC_ALLOWED, (
        "发现未登记的动态路径构造，请确认目标端点存在后将其加入 _DYNAMIC_ALLOWED，"
        f"并在 test_known_dynamic_targets_exist 里硬校验其目标:\n"
        f"  新增: {sorted(actual - _DYNAMIC_ALLOWED)}\n"
        f"  已移除: {sorted(_DYNAMIC_ALLOWED - actual)}"
    )


def test_known_dynamic_targets_exist(openapi_index: dict[tuple[str, ...], set[str]]) -> None:
    """白名单动态调用的真实目标逐条硬校验（防白名单本身烂掉）。"""
    expected: list[tuple[str, str]] = [
        # folder_file.py: owner_kind 两种取值的真实端点
        ("GET", "/cases/{case_id}/folder-entries"),
        ("GET", "/contracts/{contract_id}/folder-entries"),
        # core/tasks.py: _KINDS 四类异步任务的状态端点
        ("GET", "/pdf-splitting/jobs/{task_id}"),
        ("GET", "/oa-archive/session/{task_id}"),
        ("GET", "/oa-stamp/session/{task_id}"),
        ("GET", "/litigation/tasks/{task_id}"),
    ]
    failures = [
        f"{method} {path} 不在后端路由里（动态白名单的目标已漂移）"
        for method, path in expected
        if method.lower() not in openapi_index.get(_canonical(path), set())
    ]
    assert not failures, "\n".join(failures)


def test_openapi_registry_floor(openapi_index: dict[tuple[str, ...], set[str]]) -> None:
    """端点数下限护栏：注册表崩了会让上一条测试以 0 比对全绿。"""
    assert len(openapi_index) >= _MIN_OPENAPI_PATHS, (
        f"OpenAPI 仅 {len(openapi_index)} 条路径（护栏 {_MIN_OPENAPI_PATHS}），疑似路由注册失效"
    )
