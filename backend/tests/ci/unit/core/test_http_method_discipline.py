"""HTTP 方法纪律门禁——GET 处理函数不得做写操作(2026-10-25 晨间审计二十轮)。

## 背景

MCP 审批分级按「工具名 + REST 方法」判定读写:LOW(直接执行+readOnlyHint)
要求 REST 是 GET。若某个 GET 端点在服务层偷偷写库,这条信任链就从根上断掉
——分级、readOnlyHint、留痕策略全部失真。与 ``test_approval_alignment.py``
(工具侧)互为上下游:本门禁守 REST 侧。

2026-10-25 全量扫描(241 个 GET 端点):零真实写操作,仅 4 个字符串方法
假阳性(``startswith``/``removeprefix``)。本门禁防回退。

## 实现说明

- AST 切函数体(正则按行切块曾把装饰器参数当函数体,静默漏扫);
- 内置自证:POST 侧同样规则应命中 30+(写语义正则失效时立刻红灯,
  而不是安静地全绿)。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[4]
_API_GLOB = sorted((_BACKEND / "apps").glob("*/api/*.py"))

#: 服务方法动词——GET 里出现即写嫌疑。
_SVC_WRITE = re.compile(
    r"\w+\.(create|save|update|delete|remove|sync|generate|submit|start|trigger|move|merge"
    r"|complete|cancel|toggle|assign|import|send|record|mark|archive|approve|reorder"
    r"|rename|bind|learn|clear|reset|cleanup)\w*\("
)
#: str 自身的方法撞了动词前缀,显式排除。
_STR_METHODS = ("startswith", "endswith", "removeprefix", "removesuffix", "lstrip", "rstrip", "strip")


def _route_path(node: ast.FunctionDef | ast.AsyncFunctionDef, method: str) -> str | None:
    for d in node.decorator_list:
        if isinstance(d, ast.Call) and getattr(d.func, "attr", "") == method:
            if d.args and isinstance(d.args[0], ast.Constant):
                return str(d.args[0].value)
    return None


def _find_get_writes() -> list[str]:
    findings: list[str] = []
    for f in _API_GLOB:
        src = f.read_text()
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            path = _route_path(node, "get")
            if path is None:
                continue
            body = ast.get_source_segment(src, node) or ""
            for m in _SVC_WRITE.finditer(body):
                if m.group(0).split(".")[1].removesuffix("(").startswith(_STR_METHODS):
                    continue
                findings.append(f"{f.relative_to(_BACKEND)}: GET {path} → {node.name}: {m.group(0)}")
                break
    return findings


def test_no_get_route_writes():
    findings = _find_get_writes()
    assert not findings, (
        "GET 处理函数调用写语义方法(写操作必须换 POST/PUT/PATCH/DELETE,"
        "否则 MCP 只读分级与 readOnlyHint 从根上失真):\n  - " + "\n  - ".join(findings)
    )


def test_scanner_self_check():
    """自证:同一正则在 POST 侧必须命中 30+,否则扫描器坏了(防安静全绿)。"""
    hits = 0
    for f in _API_GLOB:
        src = f.read_text()
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if _route_path(node, "post") is None:
                continue
            body = ast.get_source_segment(src, node) or ""
            if _SVC_WRITE.search(body):
                hits += 1
    assert hits > 30, f"POST 侧写语义命中仅 {hits},扫描器疑似失效"
