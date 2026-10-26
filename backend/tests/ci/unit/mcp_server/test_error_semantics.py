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


# ---------------------------------------------------------------------------
# 吞异常扫描——``except Exception`` 内 ``return`` 必须逐处登记理由。
# 历史教训:enterprise_data 曾 8 处 ``except Exception`` 后返回伪正常结果,
# 模型据此得出假事实结论(2026-10-25 早前审计修复)。本门禁防回退:
# 新增的「吞异常再 return」必须在豁免表里写明为什么这里吞是对的。
# ---------------------------------------------------------------------------

#: except-Exception 内 return 的豁免(文件名:函数名 → 理由)。
#: 锚定函数名而非行号——行号锚在本仓一天内漂移三次(签名加 Annotated 即漂),
#: 函数名锚对上方改动免疫;同函数多处吞异常时后缀 #2。
_SWALLOW_ALLOWLIST: dict[str, str] = {
    "workflow_tools.py:_resolve_mcp_access": "Bearer 身份重建失败回退匿名——有意降级,warning 已留痕",
    "folder_file.py:_load_folder_content": "批量部分失败聚合:文件级错误进 notices+条目 error 字段,其余附件照常返回",
    "folder_file.py:_render_folder_pages": "页图渲染腿断了只降级 notices(文件本体已取到),报错反会让模型说「文件不存在」",
    "agent_attachments.py:_load_content": "批量部分失败聚合(同 folder_file:_load_folder_content)",
    "agent_attachments.py:_render_pages": "页图渲染降级(同 folder_file:_render_folder_pages)",
    "fetch_url.py:_soup": "解析器回退:BeautifulSoup 失败换兼容模式,不是业务失败",
}


def _swallow_keys() -> dict[str, int]:
    """全扫描:except-Exception 内 return 的位置,键=文件:函数名,值=出现次数。"""
    keys: dict[str, int] = {}
    for f in _SCOPE:
        tree = ast.parse(f.read_text())

        def visit(node: ast.AST, fn_name: str) -> None:
            for child in ast.iter_child_nodes(node):
                child_fn = fn_name
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    child_fn = child.name
                if isinstance(child, ast.Try):
                    for h in child.handlers:
                        bare = h.type is None or (isinstance(h.type, ast.Name) and h.type.id == "Exception")
                        if not bare:
                            continue
                        if any(isinstance(sub, ast.Return) and sub.value is not None for sub in ast.walk(h)):
                            key = f"{f.name}:{fn_name or '<module>'}"
                            keys[key] = keys.get(key, 0) + 1
                visit(child, child_fn)

        visit(tree, "")
    return keys


def _find_swallowed_exceptions() -> list[str]:
    findings: list[str] = []
    for key, count in _swallow_keys().items():
        registered = 1 if key in _SWALLOW_ALLOWLIST else _SWALLOW_ALLOWLIST.get(f"{key}#2", 0)
        for i in range(1, count + 1):
            candidate = key if i == 1 else f"{key}#{i}"
            if candidate not in _SWALLOW_ALLOWLIST and registered == 0:
                findings.append(candidate)
    return findings


def test_no_new_swallowed_exceptions():
    findings = _find_swallowed_exceptions()
    assert not findings, (
        "except Exception 内 return(吞异常伪正常)——enterprise_data 8 处旧案的教训;"
        "要吞必须在 _SWALLOW_ALLOWLIST 登记理由,否则应抛 FachuanApiError:\n  - "
        + "\n  - ".join(findings)
    )


def test_swallow_allowlist_has_no_stale_entries():
    """豁免表条目必须仍然命中真实代码(函数改名/删除后及时清理)。"""
    live = set(_swallow_keys())
    stale = sorted(k.split("#")[0] for k in _SWALLOW_ALLOWLIST if k.split("#")[0] not in live)
    assert not stale, f"吞异常豁免表已失配(函数改名或代码已删),请重对: {stale}"
