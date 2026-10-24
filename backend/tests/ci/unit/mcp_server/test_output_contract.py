"""MCP 工具输出契约测试 —— 用后端真实 OpenAPI 响应结构校验每个工具。

## 为什么需要这个测试

MCP 框架（``mcp.server.mcpserver``）会按工具函数的**返回类型注解**自动生成
``output_schema``，并在 ``convert_result`` 时用 pydantic 校验真实返回值。
声明与实现不符时，工具**在模型侧永远不可用**：

    def list_case_logs(case_id) -> dict[str, Any]:
        return client.get("/cases/logs", ...)   # 后端实际返回 list[CaseLogOut]

    → ValidationError: Input should be a valid dictionary

这类问题在手工测试里极难发现（要刚好调到那个工具、还要刚好有数据），
而原有的 ``test_server_registration.py`` 只做正则匹配，不导入工具、不比对
后端契约，因此**全绿但工具全废**。

本测试从 Django Ninja 生成的 OpenAPI 里取出每个端点真实的 200 响应结构，
合成一个最小合法实例，灌进 ``fn_metadata.convert_result``，断言不抛异常。
它同时守护两件事：

1. 工具的返回类型注解与后端真实返回一致；
2. 工具实际请求的 REST 路径/方法确实是后端存在的端点。

## 依赖边界

``mcp_server.tools`` 走 REST（httpx）而非 ORM，但 ``server.py`` 的导入链会
触发部分 Django 应用初始化，因此这里需要 ``django.setup()``。测试不打网络、
不碰数据库。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

_BACKEND = Path(__file__).resolve().parents[4]
_MCP_DIR = _BACKEND / "mcp_server"

#: 后端必填，但工具签名未暴露、只能靠 ``**kwargs`` / ``payload`` 透传的工具。
#: 这些工具的返回契约仍然要测，只是不参与「必填参数覆盖」断言。
_BODY_PASSTHROUGH_ATTRS = frozenset({"payload", "data", "body"})

#: 自己消费后端返回、重新组装输出结构的工具。
#:
#: 它们的返回类型与后端端点无关，不能按「原样透传」的口径断言。登记在此
#: 的工具**必须真的加工数据**（排序/筛选/字段挑选），否则就应该直接透传。
_SELF_ASSEMBLED_OUTPUT = frozenset(
    {
        # 按时间窗口筛选 + 排序 + 字段精简，返回自己的 {total, items, ...}
        "list_upcoming_deadlines",
        "list_reminders_by_target",
        # 把 pending 任务列表包进统一状态视图
        "list_pending_court_document_tasks",
        # 归一化六个子系统的状态字段
        "get_async_task_status",
        # 本地生成，不打 REST
        "get_server_time",
    }
)


def _iter_tool_functions() -> list[tuple[str, str, str]]:
    """AST 扫描 ``mcp_server/tools/**``，产出 (函数名, 文件, 源码段)。"""
    import ast

    found: list[tuple[str, str, str]] = []
    for path in sorted(_MCP_DIR.glob("tools/**/*.py")):
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:  # pragma: no cover - 语法错误由 ruff 兜底
            continue
        for node in tree.body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                segment = ast.get_source_segment(source, node) or ""
                found.append((node.name, str(path), segment))
    return found


def _rest_call_of(segment: str) -> tuple[str, str] | None:
    """从函数源码里取出第一处 ``client.<method>("<path>")``。

    需要处理三种写法：
    - ``client.get("/x")`` / ``client.post("/x", ...)`` ——直接方法名；
    - ``client.download("/x", method="POST")`` ——下载工具可指定真实 HTTP 方法；
    - ``client.upload("/x", ...)`` ——multipart，对应 POST。
    """
    match = re.search(r"client\.(get|post|put|patch|delete|upload|download)\s*\(", segment)
    if match is None:
        return None

    called = match.group(1).upper()
    # 只在本调用实参范围内查找路径与 method 关键字，避免串到后续调用
    tail = segment[match.end() :]
    window = tail[:400]
    path_match = re.search(r"""['"](/[^'"]*)['"]""", window)
    if path_match is None:
        return None
    path = path_match.group(1)

    if called == "DOWNLOAD":
        # client.download(..., method="POST") 时真实方法是 POST，缺省 GET
        method_match = re.search(r"""method\s*=\s*['"](\w+)['"]""", window)
        return (method_match.group(1).upper() if method_match else "GET"), path
    if called == "UPLOAD":
        return "POST", path
    return called, path


def _resolve_schema(schema: dict[str, Any], components: dict[str, Any], depth: int = 0) -> dict[str, Any]:
    """展开 ``$ref`` / ``allOf``，最多递归 ``depth`` 层。"""
    if depth > 4 or not isinstance(schema, dict):
        return {}
    if "$ref" in schema:
        name = str(schema["$ref"]).split("/")[-1]
        return _resolve_schema(components.get(name, {}), components, depth + 1)
    if "allOf" in schema:
        merged: dict[str, Any] = {}
        for arm in schema["allOf"]:
            merged.update(_resolve_schema(arm, components, depth + 1))
        return merged
    return schema


def _synthesize(schema: dict[str, Any], components: dict[str, Any], depth: int = 0) -> Any:
    """按 JSON Schema 造一个最小合法实例（只求类型正确，不求语义）。"""
    if depth > 4:
        return None
    resolved = _resolve_schema(schema, components)
    if not resolved:
        return None

    declared = resolved.get("type")
    if declared == "array":
        item = _synthesize(resolved.get("items") or {}, components, depth + 1)
        return [item] if item is not None else []
    if declared == "object" or "properties" in resolved:
        return {
            key: _synthesize(value, components, depth + 1)
            for key, value in list((resolved.get("properties") or {}).items())[:12]
        }
    if declared == "string":
        fmt = resolved.get("format")
        return "2026-01-01" if fmt == "date" else "x"
    if declared == "integer":
        return 1
    if declared == "number":
        return 1.0
    if declared == "boolean":
        return False
    return None


@pytest.fixture(scope="module")
def openapi() -> dict[str, Any]:
    """从 Django Ninja 取真实 OpenAPI（不打网络）。"""
    from apiSystem.api import api

    schema = api.get_openapi_schema()
    # Ninja 的 schema 里可能残留 lazy proxy，先过一遍 JSON
    return json.loads(json.dumps(schema, default=str))


@pytest.fixture(scope="module")
def registered_tools() -> dict[str, Any]:
    """导入真实 MCP server 的注册表。"""
    from mcp_server.server import mcp

    return dict(mcp._tool_manager._tools)


#: 后端可能挂在不同前缀下的路由（插件路由不带 ``/automation`` 等 app 前缀）。
#: 比较前把路径归一化为「参数占位 + 完整段序列」，避免 ``/case-import`` 误配
#: ``/api/v1/oa-filing/case-import`` 这类段数不足的前缀歧义。
_PARAM_RE = re.compile(r"\{[^}]*\}")


def _canonical(path: str) -> tuple[str, ...]:
    """把路径归一化为段元组（参数段统一成 ``{}``），用于精确结构比对。

    去掉可选的 ``api/v1`` 前缀，使工具里写的 ``/casts/...`` 与 OpenAPI 的
    ``/api/v1/cases/...`` 能对齐。
    """
    segments = [segment for segment in path.strip("/").split("/") if segment]
    if segments[:2] == ["api", "v1"]:
        segments = segments[2:]
    return tuple(_PARAM_RE.sub("{}", segment) for segment in segments)


def _endpoint_for(openapi: dict[str, Any], path: str, method: str) -> dict[str, Any] | None:
    """按段结构匹配 OpenAPI 路径，返回该 method 的 operation。"""
    target = _canonical(path)
    for key in openapi["paths"]:
        if _canonical(key) == target:
            return openapi["paths"][key].get(method.lower())
    return None


def _success_schema(operation: dict[str, Any]) -> dict[str, Any] | None:
    responses = operation.get("responses") or {}
    success = responses.get("200") or responses.get("201")
    if not success:
        return None
    return (success.get("content") or {}).get("application/json", {}).get("schema")


# ---------------------------------------------------------------------------
# 契约测试
# ---------------------------------------------------------------------------


def test_output_contract_matches_backend(openapi: dict[str, Any], registered_tools: dict[str, Any]) -> None:
    """每个工具的返回类型注解必须能容纳后端真实返回。

    这是本文件的核心：把「声明 list 实际返回 dict」这类导致工具永久失败的
    契约漂移挡在 CI 里。
    """
    components = openapi.get("components", {}).get("schemas", {})
    sources = {name: segment for name, _file, segment in _iter_tool_functions()}

    failures: list[str] = []
    checked = 0

    for name, tool in sorted(registered_tools.items()):
        segment = sources.get(name)
        if segment is None:
            continue
        if name in _SELF_ASSEMBLED_OUTPUT:
            continue
        call = _rest_call_of(segment)
        if call is None:
            continue
        method, path = call

        operation = _endpoint_for(openapi, path, method)
        if operation is None:
            failures.append(f"{name}: 后端不存在端点 {method} {path}")
            continue

        schema = _success_schema(operation)
        if schema is None:
            # 无 JSON 响应（如 FileResponse 二进制下载）——单独由
            # test_binary_download_tools_use_download 守护
            continue

        payload = _synthesize(schema, components)
        if payload is None:
            continue

        # 信封化工具(源码含 list_result( 标记):SDK 会把裸 list 逐项拆成
        # 独立 TextContent、空列表变成零内容块,故统一包 {total, items}。
        # 这里把后端响应同样包一层再校验,items 形状仍受契约约束。
        if "list_result(" in segment:
            payload = {"total": len(payload) if isinstance(payload, list) else 1, "items": payload}

        checked += 1
        try:
            tool.fn_metadata.convert_result(payload)
        except Exception as exc:
            first_line = str(exc).splitlines()[0]
            failures.append(f"{name}: 声明 {_return_annotation(tool)} 装不下后端响应 → {first_line}")

    assert checked > 100, f"契约检查覆盖过少（{checked}），疑似工具扫描失效"
    assert not failures, "MCP 工具输出契约与后端不一致（会导致工具永远不可用）:\n" + "\n".join(
        f"  - {item}" for item in failures
    )


def _return_annotation(tool: Any) -> str:
    import inspect

    annotation = inspect.signature(tool.fn).return_annotation
    return str(annotation).replace("typing.", "")


def test_binary_download_tools_use_download(registered_tools: dict[str, Any]) -> None:
    """返回二进制的下载工具必须走 ``client.download``。

    ``client.get`` 会调用 ``resp.json()``，对 ZIP/PDF 响应直接抛异常——
    这是 ``download_sms_documents`` 曾经永久失败的原因。
    """
    offenders: list[str] = []
    for name, _file, segment in _iter_tool_functions():
        if not name.startswith("download_"):
            continue
        if name not in registered_tools:
            continue
        if "client.download(" in segment:
            continue
        # 少数下载工具转调业务服务后返回结构化结果（非直接文件流），放行
        if "client.get(" not in segment and "client.post(" not in segment:
            continue
        offenders.append(name)

    assert not offenders, "以下 download_* 工具用 client.get/post 请求二进制端点，会因 resp.json() 崩溃：" + ", ".join(
        sorted(offenders)
    )


#: 发了 REST 请求但 _rest_call_of 静态识别不了的合法形态(动态分发/多端点
#: 聚合)。新增豁免必须写明原因——它们**不受路径/参数契约保护**,改其请求
#: 构造时须人工对照 OpenAPI。
_DYNAMIC_CALL_ALLOWLIST = {
    # 按 kind 从 _KINDS 模板表动态取路径(template.format),静态匹配器看不到
    "get_async_task_status",
    # 目录树聚合(多端点+本地组装),返回 list[TextContent] 多块设计
    "list_folder_files",
}


def test_requesting_tools_are_contract_visible(registered_tools: dict[str, Any]) -> None:
    """发 REST 请求的工具必须能被 _rest_call_of 识别——否则路径/参数/
    输出三张契约全部对它失明,契约漂移无人报错(2026-10-25 审计十一轮)。

    409 工具实测:未识别的 8 个里 6 个是纯本地/外部工具(不发 REST),
    2 个走登记豁免。本门禁把「新增发请求工具但模式没被识别」变成红灯。
    """
    sources = {name: segment for name, _file, segment in _iter_tool_functions()}
    offenders: list[str] = []
    for name, tool in sorted(registered_tools.items()):
        segment = sources.get(name)
        if segment is None or name in _DYNAMIC_CALL_ALLOWLIST:
            continue
        makes_request = any(
            f"client.{method}(" in segment
            for method in ("get", "post", "put", "patch", "delete", "upload", "download", "request")
        )
        if makes_request and _rest_call_of(segment) is None:
            offenders.append(name)

    assert not offenders, (
        "以下工具发 REST 请求但 _rest_call_of 识别不了(三张契约全部失明),"
        "若是动态分发/聚合形态请登记 _DYNAMIC_CALL_ALLOWLIST 并写明原因: "
        + ", ".join(offenders)
    )


def test_required_params_are_exposed(openapi: dict[str, Any], registered_tools: dict[str, Any]) -> None:
    """后端必填的 query/path/body 字段必须在工具签名里可传。

    早期有 12 个工具的参数名或结构跟后端对不上（``bind_materials`` 传
    ``material_ids`` 而后端要 ``items``；``create_grant`` 传 ``lawyer_id``
    而后端要 ``grantee_id``），这些工具有签名、能被模型选中，但每次调用都被
    422 拒绝——比「工具不存在」更难排查。
    """
    import inspect

    components = openapi.get("components", {}).get("schemas", {})
    sources = {name: segment for name, _file, segment in _iter_tool_functions()}

    #: 允许通过 ``**kwargs`` / 结构化 dict 参数透传 body 的工具写法。
    _PASSTHROUGH_NAMES = frozenset({"payload", "data", "body", "contract_data", "payment_data", "agreement_data"})

    failures: list[str] = []
    checked = 0

    for name, tool in sorted(registered_tools.items()):
        segment = sources.get(name)
        if segment is None:
            continue
        call = _rest_call_of(segment)
        if call is None:
            continue
        method, path = call

        operation = _endpoint_for(openapi, path, method)
        if operation is None:
            continue  # 端点缺失由上面的契约测试报告

        params = inspect.signature(tool.fn).parameters
        has_var_kwargs = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())
        accepted = {key for key, value in params.items() if value.kind is not inspect.Parameter.VAR_KEYWORD}
        has_passthrough = bool(accepted & _PASSTHROUGH_NAMES)

        required_query = [
            param["name"]
            for param in operation.get("parameters") or []
            if param.get("required") and param.get("in") in {"query", "path"}
        ]
        body_schema = (
            (operation.get("requestBody") or {}).get("content", {}).get("application/json", {}).get("schema", {})
        )
        required_body: list[str] = []
        # Ninja 有时把 `payload: SomeSchema` 包成 {payload: ref}，也有直接内联的
        if "$ref" in body_schema:
            required_body = list(components.get(str(body_schema["$ref"]).split("/")[-1], {}).get("required") or [])
        elif body_schema.get("required"):
            required_body = list(body_schema["required"])

        missing_query = [item for item in required_query if item not in accepted and not has_var_kwargs]
        # body 必填字段允许两种暴露方式：同名参数，或源码里写死了该 JSON key
        # （如 `target_item_code` 参数 → json={"target_code": target_item_code}）
        missing_body: list[str] = []
        if not (has_passthrough or has_var_kwargs):
            for item in required_body:
                if item in accepted:
                    continue
                if f'"{item}"' in segment or f"'{item}'" in segment:
                    continue
                missing_body.append(item)

        if not missing_query and not missing_body:
            checked += 1
            continue
        failures.append(f"{name}: {method} {path} 缺 query={missing_query} body={missing_body}")

    assert checked > 100, f"必填参数检查覆盖过少（{checked}）"
    assert not failures, "工具签名未暴露后端必填参数（调用必然 422）:\n" + "\n".join(f"  - {item}" for item in failures)
