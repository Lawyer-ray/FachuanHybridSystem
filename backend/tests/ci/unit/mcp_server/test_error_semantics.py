"""错误语义门禁——工具不得用单键 ``{"error": ...}`` dict 假装成功(2026-10-25 二十轮)。

## 背景

MCP 规范(2025-11-25 Tools):API 失败/业务逻辑错误必须走 ``isError: true``
(即抛 ToolError 子类),文案直达模型。本仓库曾有 17 处 workflow 工具把
「运行不存在/状态不对/Temporal 失败/仅管理员/校验失败」当成**成功结果**
返回 ``{"error": ...}``——SDK 把它包成成功内容块,客户端(pi 等)按
isError 做的失败处理全部失效,模型看到的是「成功里的 error 字段」。

已修:apps/workflow/mcp/workflow_tools.py 17 处全部改抛 FachuanApiError;
REST 包装层(workflow_api)相应改为捕获翻译回 HttpError(400)。

## 门禁

单键 ``{"error": ...}`` return 一律禁止(whole 工具面)。多键 dict 里的
error 字段是**批量部分失败**聚合形态(如 read_folder_files 单个附件失败
仍返回其他附件,error 仅是条目字段之一)——合法,不拦。
"""

from __future__ import annotations

import ast
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[4]
_SCOPE = sorted(
    list((_BACKEND / "mcp_server" / "tools").rglob("*.py")) + list((_BACKEND / "apps" / "workflow" / "mcp").glob("*.py"))
)


def _find_single_key_error_returns() -> list[str]:
    findings: list[str] = []
    for f in _SCOPE:
        tree = ast.parse(f.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
                keys = {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
                if keys == {"error"}:
                    findings.append(f"{f.relative_to(_BACKEND)}:{node.lineno}")
    return findings


def test_tool_files_found():
    assert len(_SCOPE) > 30, "扫描文件过少,疑似 glob 失效(防假绿)"


def test_no_single_key_error_dict_returns():
    findings = _find_single_key_error_returns()
    assert not findings, (
        "工具失败必须抛 FachuanApiError(isError 语义),不得 return 单键 {\"error\": ...} 假装成功:\n  - "
        + "\n  - ".join(findings)
    )
