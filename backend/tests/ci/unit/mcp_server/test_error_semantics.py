"""错误语义门禁：公共工具函数禁止吞异常伪造「正常结果」。

背景（2026-10-25 第四轮审计）：enterprise_data 的 8 个工具用
``except Exception: return {"success": False, ...}`' 把 ``FachuanApiError``/
``FachuanTransportError``（均为 ``ToolError`` 子类，设计上以 ``isError: true``
呈现给模型）压扁成成功调用 + 空列表——模型会得出「没有配置 provider」
这类假事实结论，且丢掉传输层写好的重试指引。CLAUDE.md「可恢复失败
吞成 debug」的 MCP 侧对应物。

口径：**公共**工具函数（非 ``_`` 前缀 def）里出现 ``except Exception`` /
``except BaseException`` / 裸 ``except`` 即违规——上游失败应让 ToolError
子类自然抛出。私有 helper（批量循环内单条失败归一化、web_search 的
自然语言降级）不受限，但必须在自己的 docstring/注释里写明理由。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parents[4] / "mcp_server" / "tools"

_BROAD_NAMES = {"Exception", "BaseException"}


def _iter_violations() -> list[str]:
    violations: list[str] = []
    for py in sorted(_TOOLS_DIR.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        # 递归携带「最近一层函数名」，except 归属到最近的 def 判断公私
        def walk(node: ast.AST, func: str | None) -> None:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                    walk(child, child.name)
                    continue
                if isinstance(child, ast.ExceptHandler) and func is not None and not func.startswith("_"):
                    bare = child.type is None
                    broad = isinstance(child.type, ast.Name) and child.type.id in _BROAD_NAMES
                    if bare or broad:
                        violations.append(f"{py.relative_to(_TOOLS_DIR)}::{func} (line {child.lineno})")
                        continue  # handler 内部不必再走
                walk(child, func)

        walk(tree, None)
    return violations


def test_public_tool_functions_do_not_swallow_exceptions() -> None:
    violations = _iter_violations()
    assert not violations, (
        "公共工具函数内出现吞异常的 except（应让 FachuanApiError/FachuanTransportError "
        "以 ToolError 穿透，MCP 层呈现 isError: true）：\n  " + "\n  ".join(violations)
    )


def test_gate_actually_scans_files() -> None:
    """防「空转绿灯」：门禁必须真的扫到了相当数量的工具文件与函数。"""
    py_files = list(_TOOLS_DIR.rglob("*.py"))
    assert len(py_files) > 30, f"扫描到的工具文件过少: {len(py_files)}"
    # 至少抽查两个已知公共工具函数确实被 AST 覆盖（本门禁扫到过的目录）
    assert (_TOOLS_DIR / "enterprise_data" / "enterprise_data.py").exists()
    assert (_TOOLS_DIR / "contracts" / "folder_file.py").exists()


def test_private_helper_swallow_still_allowed() -> None:
    """合法形态回归锚点：folder_file 的私有 helper 部分失败聚合不应被误伤。"""
    violations = [v for v in _iter_violations() if "folder_file" in v]
    assert not violations, f"folder_file 误报（私有 helper 应豁免）: {violations}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
