"""REST 参数级契约：工具转发的参数必须在 OpenAPI 声明内。

路径级契约（``test_rest_path_contract.py``）只保证「路径存在」;本测试补
参数级——2026-10-25 审计发现 4 处「参数从未生效」的工具（list_lawyers 的
team_id、list_payments 的 payment_type、calculate_interest 的
rate_addition/rate_multiplier、ensure_guarantee_quote 的 amount）,共同症状:
ninja/pydantic **静默忽略**未声明参数,模型以为自己在过滤/控制,实际拿到
未过滤/默认值的结果——比报错更糟（答案静默错误）。

## 已知局限（只做增量守护,不求完备）

- 变量透传做**同函数内**静态绑定（``json=payload`` 时收 ``payload = {...}``
  字面量键与 ``payload["k"] =`` 赋值）;跨函数/别名传递不检查。
- f-string 路径（含路径参数）跳过——路径参数天然在 OpenAPI path 段声明。
- 裸 payload.get 收参的端点（无 schema 声明）会全部误报,进 allowlist 并
  注明原因;新端点应声明 schema,不再新增 allowlist 条目。
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

_MCP_ROOT = Path(__file__).resolve().parents[4] / "mcp_server"

#: 裸 payload.get 收参的端点——OpenAPI 无参数声明,但实现读取这些键。
#: 新代码**不要**往这里加：给端点声明 schema 才是正道。
RAW_PAYLOAD_ALLOWLIST: dict[str, set[str]] = {
    "/image-rotation/extract-pdf-fast": {"data", "filename"},
    "/image-rotation/detect-orientation": {"images"},
    "/image-rotation/suggest-rename": {"items"},
    "/image-rotation/detect-page-orientation": {"data"},
    "/image-rotation/export-pdf": {"pages", "paper_size"},
    "/image-rotation/export": {"images", "paper_size", "rename_map"},
    # OA 客户导入:无 schema 声明,实现从 request.body 裸读 headless/limit
    "/client-import": {"headless", "limit"},
    # 批量创建(案件/客户导入):无 schema,实现从 request.body 裸读 cases/customers
    "/api/v1/case-import/{session_id}/batch-create": {"cases"},
    "/api/v1/client-import/{session_id}/batch-create": {"customers"},
    # 占位符预览:GET keys 过滤,实现从 request.GET 裸读
    "/api/v1/documents/placeholders/preview/{contract_id}": {"keys"},
}

_VERBS = {"get": "get", "post": "post", "put": "put", "delete": "delete", "patch": "patch", "upload": "post", "download": "post"}


def _openapi_spec() -> Any:
    """生成 OpenAPI schema（纯内存,不碰库;含 lazy 文案,不 JSON 往返）。"""
    from apiSystem.api import api

    return api.get_openapi_schema()


def _declared_params(spec: Any, api_path: str, verb: str) -> set[str] | None:
    """端点声明的参数名集合;None = 端点不存在（路径契约测试的职责）。

    requestBody 支持 $ref 与**内联** object schema 两种——``/contracts/contracts``
    这类「payload + payments 双 body 参数」端点由 ninja 生成内联 schema,只认
    $ref 会把它们全误报成假参数。
    """
    op = spec.get("paths", {}).get(api_path, {}).get(verb)
    if op is None:
        return None
    declared = {p["name"] for p in op.get("parameters", []) if p.get("in") == "query"}
    schema = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})
    if "$ref" in schema:
        node: Any = spec
        for part in schema["$ref"].split("/")[1:]:
            node = node[part]
        schema = node
    if isinstance(schema.get("properties"), dict):
        declared.update(schema["properties"].keys())
    elif isinstance(schema.get("anyOf"), list) or isinstance(schema.get("oneOf"), list):
        # Optional body 参数(payload: X | None = None)会被 ninja 包成 anyOf[X, null]
        for sub in schema.get("anyOf", []) + schema.get("oneOf", []):
            if "$ref" in sub:
                node: Any = spec
                for part in sub["$ref"].split("/")[1:]:
                    node = node[part]
                declared.update((node.get("properties") or {}).keys())
            elif isinstance(sub.get("properties"), dict):
                declared.update(sub["properties"].keys())
    return declared


def _match_fstring_path(spec: Any, fstring: ast.JoinedStr) -> str | None:
    """f-string 路径解析成 OpenAPI 模板路径;唯一匹配才返回。

    f"/cases/grants/{grant_id}" → "/api/v1/cases/grants/{grant_id}"。
    模板名不必一致（工具侧变量名 vs OpenAPI 参数名）,按段数与字面段
    全等匹配;多义/零匹配返回 None（跳过,宁漏勿误报）。
    """
    segs: list[str] = ["api", "v1"]  # 工具路径不带 /api/v1 前缀,补齐后再逐段比
    for part in fstring.values:
        if isinstance(part, ast.Constant):
            segs.extend(str(part.value).split("/"))
        else:
            segs.append("\x00")
    segs = [s for s in segs if s]
    matches: list[str] = []
    for path in spec.get("paths", {}):
        p_segs = [s for s in path.split("/") if s]
        if len(p_segs) != len(segs):
            continue
        ok = True
        for tool_seg, api_seg in zip(segs, p_segs):
            api_is_tpl = api_seg.startswith("{") and api_seg.endswith("}")
            if tool_seg == "\x00":
                if not api_is_tpl:
                    ok = False
                    break
            elif tool_seg != api_seg:
                ok = False
                break
        if ok:
            matches.append(path)
    return matches[0] if len(matches) == 1 else None


def _forwarded_keys(fn: ast.FunctionDef | ast.AsyncFunctionDef, call: ast.Call) -> set[str]:
    """收集该调用直接/间接转发的字面量键。

    覆盖三种形态：
    1. ``params={...}`` / ``json={...}`` 字面量键；
    2. ``json=payload`` 变量引用：收 ``payload = {...}`` 字面量键；
    3. ``payload["k"] = v`` 下标赋值（任意变量名,只要该变量被本调用当
       json=/params= 用）——2026-10-25 二轮审计的实锤:update_grant 的
       ``permission_level`` 六个月没人发现,就是因为初版只认 ``params[...]``
       赋值,漏了 ``payload[...]``。
    """
    keys: set[str] = set()
    bound_names: set[str] = set()
    for kw in call.keywords:
        if kw.arg in ("params", "json"):
            if isinstance(kw.value, ast.Dict):
                keys.update(k.value for k in kw.value.keys if isinstance(k, ast.Constant))
            elif isinstance(kw.value, ast.Name):
                bound_names.add(kw.value.id)
    if not bound_names:
        return keys
    for stmt in ast.walk(fn):
        if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Dict):
            # payload = {...} 字面量整体绑定
            for t in stmt.targets:
                if isinstance(t, ast.Name) and t.id in bound_names:
                    keys.update(k.value for k in stmt.value.keys if isinstance(k, ast.Constant))
        if (
            isinstance(stmt, ast.Assign)
            and isinstance(stmt.targets[0], ast.Subscript)
            and isinstance(stmt.targets[0].value, ast.Name)
            and stmt.targets[0].value.id in bound_names
            and isinstance(stmt.targets[0].slice, ast.Constant)
        ):
            keys.add(stmt.targets[0].slice.value)
    return keys


def _violations(spec: Any) -> list[tuple[str, str, str, str]]:
    out: list[tuple[str, str, str, str]] = []
    for py in sorted((_MCP_ROOT / "tools").rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(fn):
                if not (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "client"
                ):
                    continue
                verb = node.func.attr
                if verb not in _VERBS or not node.args:
                    continue
                raw_path = node.args[0]
                if isinstance(raw_path, ast.JoinedStr):
                    # f-string 路径:body 参数照样要核——update_grant 的
                    # permission_level 假参数正是靠 f-string 盲区藏身的。
                    matched = _match_fstring_path(spec, raw_path)
                    if matched is None:
                        continue
                    declared = _declared_params(spec, matched, _VERBS[verb])
                    if declared is None:
                        continue
                    unknown = _forwarded_keys(fn, node) - declared - RAW_PAYLOAD_ALLOWLIST.get(matched, set())
                    if unknown:
                        out.append((py.name, fn.name, matched, ",".join(sorted(unknown))))
                    continue
                if not (isinstance(raw_path, ast.Constant) and isinstance(raw_path.value, str)):
                    continue
                api_path = "/api/v1" + raw_path.value
                declared = _declared_params(spec, api_path, _VERBS[verb])
                if declared is None:
                    continue
                unknown = _forwarded_keys(fn, node) - declared - RAW_PAYLOAD_ALLOWLIST.get(raw_path.value, set())
                if unknown:
                    out.append((py.name, fn.name, raw_path.value, ",".join(sorted(unknown))))
    return out


@pytest.mark.django_db(transaction=False)
def test_forwarded_params_are_declared() -> None:
    """工具转发的参数必须被端点声明（或进 allowlist 并注明原因）。"""
    violations = _violations(_openapi_spec())
    assert not violations, (
        "以下工具转发了端点未声明的参数（ninja 静默忽略 = 模型拿到静默错误的结果）:\n"
        + "\n".join(f"  {f}::{fn} -> {path} 未声明: {keys}" for f, fn, path, keys in violations)
    )


def test_allowlist_paths_still_undeclared() -> None:
    """allowlist 条目必须仍然「端点无声明」——端点补了 schema 就该从 allowlist 删。"""
    spec = {
        "/image-rotation/extract-pdf-fast": "post",
        "/image-rotation/detect-orientation": "post",
        "/image-rotation/suggest-rename": "post",
        "/image-rotation/detect-page-orientation": "post",
        "/image-rotation/export-pdf": "post",
        "/image-rotation/export": "post",
        "/client-import": "post",
        "/api/v1/case-import/{session_id}/batch-create": "post",
        "/api/v1/client-import/{session_id}/batch-create": "post",
        "/api/v1/documents/placeholders/preview/{contract_id}": "get",
    }
    full = _openapi_spec()
    for path, verb in spec.items():
        declared = _declared_params(full, "/api/v1" + path, verb)
        if declared is None:
            continue
        leak = RAW_PAYLOAD_ALLOWLIST[path] & declared
        assert not leak, f"{path} 已声明 {leak},应从 RAW_PAYLOAD_ALLOWLIST 移除"
