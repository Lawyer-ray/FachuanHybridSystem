"""Structure guard：综合链路里「失败不阻断」的宽口径 except 必须先放行取消。

``except BaseException`` / 裸 ``except`` 会接住 ``asyncio.CancelledError``。综合链路
（前置评审、引用核验、写转录、任务监督）多处用它做"这一步失败也别拖垮整份结论"的
降级——一旦没先放行取消，用户点了取消、后台照样跑完、照样花钱（2026-11-22 评审 🔴4）。

规则：同一个 ``try`` 里，宽口径 handler 之前必须有一个 handler 接住 ``CancelledError``
（写 ``except MUST_PROPAGATE: raise``，或显式列出 ``asyncio.CancelledError``）。
``except Exception`` 不在检查范围：它本来就接不住 ``CancelledError``。
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[3]

#: 受检文件：综合结论的 API 与 services/synthesis 整个包。
_CHECKED_FILES = sorted(
    [
        _BACKEND_ROOT / "apps" / "agent" / "api" / "synthesis_api.py",
        *(_BACKEND_ROOT / "apps" / "agent" / "services" / "synthesis").glob("*.py"),
    ]
)

#: 视为"已放行取消"的 handler 类型名。
_CANCEL_NAMES = {"MUST_PROPAGATE", "CancelledError"}


def _type_names(node: ast.expr | None) -> set[str]:
    """handler 类型表达式里出现的名字（``asyncio.CancelledError`` 取 ``CancelledError``）。"""
    if node is None:
        return set()
    if isinstance(node, ast.Tuple):
        names: set[str] = set()
        for element in node.elts:
            names |= _type_names(element)
        return names
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, ast.Attribute):
        return {node.attr}
    return set()


def _is_broad(handler: ast.ExceptHandler) -> bool:
    return handler.type is None or "BaseException" in _type_names(handler.type)


def _violations() -> list[str]:
    found: list[str] = []
    for path in _CHECKED_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            cancel_released = False
            for handler in node.handlers:
                if _type_names(handler.type) & _CANCEL_NAMES:
                    cancel_released = True
                    continue
                if _is_broad(handler) and not cancel_released:
                    found.append(f"{path.relative_to(_BACKEND_ROOT)}:{handler.lineno}")
    return found


def test_checked_files_exist() -> None:
    """受检范围不能悄悄变空（文件改名 / 挪目录时这里先失败）。"""
    names = {path.name for path in _CHECKED_FILES}
    assert {"synthesis_api.py", "pipeline.py", "jobs.py", "verify.py"} <= names


def test_must_propagate_includes_cancellation() -> None:
    from apps.agent.services.synthesis.control_flow import MUST_PROPAGATE

    assert asyncio.CancelledError in MUST_PROPAGATE
    assert {KeyboardInterrupt, SystemExit, GeneratorExit} <= set(MUST_PROPAGATE)


def test_broad_handlers_release_cancellation_first() -> None:
    violations = _violations()
    assert not violations, (
        "以下宽口径 except 之前没有放行 asyncio.CancelledError（先写 `except MUST_PROPAGATE: raise`）：\n"
        + "\n".join(f"  {item}" for item in violations)
    )
