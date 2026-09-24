"""Structure guard: every absolute ``apps.*`` / ``plugins.*`` import must resolve.

Motivation
----------
2026-09 审查发现 8 处「import 不存在的模块」的运行时炸弹（见 changelog
v27.0.9）。它们全部藏在**函数体内**做懒导入，且调用方带 ``# pragma: no cover``，
于是三道防线全部失效：

1. **ruff 的 F821 不适用**——它只检查「未定义的*名称*」，不解析「*模块*是否存在」
   （实测 ``from apps.core.nonexistent import Foo`` 过 ruff 全绿）；符号被使用时
   ``F401`` 也不适用。
2. **mypy 被 ``--follow-imports=silent`` 抑制**——CI 因此看不到 import 解析失败。
3. **测试反而掩护**——个别测试用 ``sys.modules[<坏路径>] = Mock`` 注入假模块；
   另有测试只构造响应 Schema、从不真正调用 endpoint。

本守卫用 ``importlib.util.find_spec`` 直接问解释器「这模块到底存不存在」，
一次性永久拦住这一类问题。

Deliberate scope decisions (each verified against the real tree)
---------------------------------------------------------------
* 只检查**绝对导入** ``apps.`` / ``plugins.``。相对导入（``from .models import X``）
  的 ``ImportFrom.module`` 只是 ``"models"``，不是可解析的绝对路径，必须排除——
   否则会产生上千个假阳性。
* **排除 ``if TYPE_CHECKING:`` 块内的导入**。这些只服务于类型注解、永不执行，
  仓库中确有历史遗留路径（如 ``apps.users.models``、``apps.automation.services.
  sms.matching.*``，共 7 处）。把它们算进去会让守卫一上线就误报。
* 只断言**模块路径**存在，不断言符号存在。符号是否存在属于 mypy/运行期职责，
  且会被 ``X as Y`` 别名、``__all__`` re-export 等情况误伤（本守卫开发过程中
  就因别名产生过 3 个假阳性）。
* 迁移目录（``migrations/``）不扫描——历史迁移按设计引用当时的模型状态。
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

_MODULE = sys.modules[__name__]

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_SCAN_ROOTS = ("apps", "plugins")

# 这些目录不参与扫描：历史迁移引用创建时的模型快照，不代表当前代码状态
_SKIP_DIR_PARTS = {"__pycache__", "migrations"}


def _plugins_available() -> bool:
    """plugins 子模块是否可用。

    ``plugins`` 是 git 子模块，CI 的 ``actions/checkout`` 没有开
    ``submodules: true``（本地 ``scripts/ci-local.sh`` 也不初始化），
    所以 CI 环境里根本没有 ``backend/plugins`` 目录。此时所有
    ``from plugins.xxx import`` 都不可解析——这是环境差异，不是代码缺陷。
    故 plugins 不可用时跳过对 ``plugins.*`` 导入的检查。
    """
    return importlib.util.find_spec("plugins") is not None


def _in_type_checking(node: ast.AST, tree: ast.AST) -> bool:
    """判断 import 节点是否位于 ``if TYPE_CHECKING:`` 块内。"""
    for parent in ast.walk(tree):
        if not isinstance(parent, ast.If):
            continue
        if "TYPE_CHECKING" not in ast.dump(parent.test):
            continue
        if any(child is node for child in ast.walk(parent)):
            return True
    return False


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for root_name in _SCAN_ROOTS:
        root = _BACKEND_ROOT / root_name
        if not root.is_dir():
            continue
        for py in root.rglob("*.py"):
            if any(part in _SKIP_DIR_PARTS for part in py.parts):
                continue
            files.append(py)
    return files


def _module_exists(module: str) -> bool:
    """问解释器这模块是否真的存在。find_spec 可能抛异常（坏父包），一律算不存在。"""
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, AttributeError, ValueError):
        return False


def _collect_unresolvable() -> list[tuple[str, int, str]]:
    """返回 (相对路径, 行号, 模块名) 列表：绝对导入但模块不存在的。"""
    importlib.invalidate_caches()
    check_plugins = _plugins_available()
    violations: list[tuple[str, int, str]] = []
    for py in _iter_python_files():
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            # 只看绝对导入；相对导入的 module 不是可解析路径
            if not node.module.startswith(_SCAN_ROOTS):
                continue
            # plugins 子模块未初始化（如 CI）时，plugins.* 一律不可解析，属环境差异
            # 覆盖 "plugins" 与 "plugins.xxx" 两种写法
            if not check_plugins and (node.module == "plugins" or node.module.startswith("plugins.")):
                continue
            if _in_type_checking(node, tree):
                continue
            if not _module_exists(node.module):
                rel = py.relative_to(_BACKEND_ROOT)
                violations.append((str(rel), node.lineno, node.module))
    return sorted(violations)


def test_absolute_app_imports_resolve() -> None:
    """所有绝对 ``apps.*`` / ``plugins.*`` 导入的模块必须真实存在。

    拦住「函数体懒导入一个不存在的模块」这类运行时炸弹——它们对
    ruff / mypy / 常规测试均不可见。
    """
    violations = _collect_unresolvable()

    if violations:
        lines = [f"  {path}:{lineno}: from {mod} import ..." for path, lineno, mod in violations]
        msg = (
            f"Found {len(violations)} import(s) of a module that does not exist.\n"
            "这些导入在运行到该行时才会 ModuleNotFoundError。若是模块被移动/改名，\n"
            "请更新 import 路径；若是 TYPE_CHECKING 内的类型注解，请挪进 if TYPE_CHECKING 块。\n" + "\n".join(lines)
        )
        pytest.fail(msg)


def test_guard_actually_detects_broken_import() -> None:
    """自检：守卫必须能识别坏 import，否则它只是空转。

    防止未来有人把检测逻辑改坏（比如误把 TYPE_CHECKING 判断写成永远为真），
    导致守卫变成永远通过的摆设。
    """
    sample = """\
from __future__ import annotations
from typing import TYPE_CHECKING
from apps.core.interfaces import ServiceLocator          # 正确
from apps.definitely_not_a_real_pkg.xxx import Thing      # 坏
if TYPE_CHECKING:
    from apps.also_not_real.type_only import Hint          # 应跳过
"""
    tree = ast.parse(sample)
    caught: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        if not node.module.startswith(_SCAN_ROOTS):
            continue
        if _in_type_checking(node, tree):
            continue
        if not _module_exists(node.module):
            caught.append(node.module)

    assert caught == ["apps.definitely_not_a_real_pkg.xxx"], f"守卫自检失败：应只抓到 1 个坏 import，实得 {caught}"


def test_plugins_import_skipped_when_submodule_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """plugins 子模块未初始化时，不得把 ``plugins.*`` 导入报成违规。

    CI 的 ``actions/checkout`` 没开 ``submodules: true``，CI 环境里没有
    ``backend/plugins`` 目录，所有 ``plugins.*`` 导入都不可解析——这是环境
    差异而非代码缺陷。曾因漏掉这条，守卫在 CI 上报了 47 个假阳性。
    """
    monkeypatch.setattr(_MODULE, "_plugins_available", lambda: False)

    sample = """\
from plugins.court_automation.token_admin import TokenAcquisitionHistoryAdminService
from apps.definitely_not_a_real_pkg.xxx import Thing
"""
    tree = ast.parse(sample)
    caught: list[str] = []
    check_plugins = _plugins_available()
    assert check_plugins is False, "monkeypatch 未生效"
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        if not node.module.startswith(_SCAN_ROOTS):
            continue
        if not check_plugins and node.module.startswith("plugins."):
            continue
        if not _module_exists(node.module):
            caught.append(node.module)

    assert caught == ["apps.definitely_not_a_real_pkg.xxx"], f"plugins 不可用时仍抓到 {caught}"
