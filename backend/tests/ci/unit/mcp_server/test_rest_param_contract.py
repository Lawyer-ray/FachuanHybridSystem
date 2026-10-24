"""REST 参数级契约：工具转发的参数必须在 OpenAPI 声明内。

路径级契约（``test_rest_path_contract.py``）只保证「路径存在」;本测试补
参数级——2026-10-25 审计发现 4 处「参数从未生效」的工具（list_lawyers 的
team_id、list_payments 的 payment_type、calculate_interest 的
rate_addition/rate_multiplier、ensure_guarantee_quote 的 amount）,共同症状:
ninja/pydantic **静默忽略**未声明参数,模型以为自己在过滤/控制,实际拿到
未过滤/默认值的结果——比报错更糟（答案静默错误）。

## 已知局限（只做增量守护,不求完备）

- 只解析 ``params={...}`` / ``json={...}`` **字面量**键与 ``params["k"]=``
  赋值;``json=payload``（变量）不检查——那需要过程间分析,收益低。
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
}

_VERBS = {"get": "get", "post": "post", "put": "put", "delete": "delete", "patch": "patch", "upload": "post", "download": "post"}


def _openapi_spec() -> Any:
    """生成 OpenAPI schema（纯内存,不碰库;含 lazy 文案,不 JSON 往返）。"""
    from apiSystem.api import api

    return api.get_openapi_schema()


def _declared_params(spec: Any, api_path: str, verb: str) -> set[str] | None:
    """端点声明的参数名集合;None = 端点不存在（路径契约测试的职责）。"""
    op = spec.get("paths", {}).get(api_path, {}).get(verb)
    if op is None:
        return None
    declared = {p["name"] for p in op.get("parameters", []) if p.get("in") == "query"}
    schema = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})
    ref = schema.get("$ref", "")
    if ref:
        node: Any = spec
        for part in ref.split("/")[1:]:
            node = node[part]
        declared.update((node.get("properties") or {}).keys())
    return declared


def _forwarded_keys(fn: ast.FunctionDef | ast.AsyncFunctionDef, call: ast.Call) -> set[str]:
    """收集该调用直接转发的字面量键 + 同函数内 params["k"] 赋值。"""
    keys: set[str] = set()
    for kw in call.keywords:
        if kw.arg in ("params", "json") and isinstance(kw.value, ast.Dict):
            keys.update(k.value for k in kw.value.keys if isinstance(k, ast.Constant))
    for stmt in ast.walk(fn):
        if (
            isinstance(stmt, ast.Assign)
            and isinstance(stmt.targets[0], ast.Subscript)
            and isinstance(stmt.targets[0].value, ast.Name)
            and stmt.targets[0].value.id == "params"
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
                if not (isinstance(raw_path, ast.Constant) and isinstance(raw_path.value, str)) or "{" in raw_path.value:
                    continue
                declared = _declared_params(spec, "/api/v1" + raw_path.value, _VERBS[verb])
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
    }
    full = _openapi_spec()
    for path, verb in spec.items():
        declared = _declared_params(full, "/api/v1" + path, verb)
        if declared is None:
            continue
        leak = RAW_PAYLOAD_ALLOWLIST[path] & declared
        assert not leak, f"{path} 已声明 {leak},应从 RAW_PAYLOAD_ALLOWLIST 移除"
