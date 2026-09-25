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

Performance note (2026-09-25)
----------------------------
守卫在 ~2260 个文件上原本耗时 33s+，已逼近 ``pytest-timeout`` 的 30s
预算并开始间歇性超时（本地两次 CI 一次过、一次挂）。profiling 显示两处
热点，均已修掉：

1. **每个 import 都重扫整棵树**（占 50s / 93s）：原 ``_in_type_checking``
   对每个 ``ImportFrom`` 节点都 ``ast.walk`` 整棵树，还要对每个 ``If``
   节点 ``ast.dump`` 一次测试表达式。改为 ``_iter_target_imports`` 的
   **单趟遍历**，遍历时携带 "是否在 TYPE_CHECKING 块内" 标记。
2. **``find_spec`` 重复解析同一模块**（占 25s+）：同一 ``apps.*`` 模块在
   全仓库被成百上千处导入，而 ``find_spec`` 会真正 import 父包、执行
   ``__init__``。改为先去重收集模块名、只解析一次（实测 distinct 解析
   仅 5.8s），结果按模块名 memoize。

修复后本用例从 33.7s 降到 10.3s。守卫语义未变：已通过「新旧实现在真实
代码树上逐条比对一致」「注入坏 import（含函数体懒导入）仍能被抓」
两项验证。
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
    """plugins 子模块是否可用（已初始化并有实际内容）。

    ``plugins`` 是 git 子模块，CI 的 ``actions/checkout`` 没有开
    ``submodules: true``（本地 ``scripts/ci-local.sh`` 也不初始化），
    所以 CI 环境里 ``backend/plugins`` 要么不存在、要么是**空目录**。

    两种情况下 ``find_spec("plugins")`` 都不好使：
    - 目录不存在 → spec 为 None
    - **空目录** → Python 3.12 会给出 namespace package spec，
      ``loader`` 是 ``NamespaceLoader``（**不是 None**），光看
      ``spec is not None`` 或 ``loader is not None`` 都会误判成可用

    而空目录下的 ``from plugins.xxx import`` 依然 ModuleNotFoundError。
    这是环境差异，不是代码缺陷，故此时跳过对 ``plugins.*`` 导入的检查。

    判据：spec 存在、loader 不是 NamespaceLoader，且包目录里确有
    ``__init__.py``（真正的包才有）。
    """
    try:
        spec = importlib.util.find_spec("plugins")
    except (ImportError, AttributeError, ValueError):
        return False
    if spec is None or spec.loader is None:
        return False
    if type(spec.loader).__name__ == "NamespaceLoader":
        return False
    # 真正的包必然有 __init__.py
    locations = spec.submodule_search_locations
    return bool(locations) and any((Path(loc) / "__init__.py").exists() for loc in locations or [])


def _is_type_checking_test(node: ast.AST) -> bool:
    """判断 ``if X:`` 的条件是否是 ``TYPE_CHECKING``。

    原来用 ``ast.dump(parent.test)`` 找 "TYPE_CHECKING" 子串，每个 If 节点都要
    序列化一遍整棵测试表达式子树；改成只认三种真实写法（``TYPE_CHECKING``、
    ``typing.TYPE_CHECKING``、``T.TYPE_CHECKING``），省掉那趟序列化。
    """
    if isinstance(node, ast.Name):
        return node.id == "TYPE_CHECKING"
    if isinstance(node, ast.Attribute):
        return node.attr == "TYPE_CHECKING"
    if isinstance(node, ast.Call):
        return _is_type_checking_test(node.func)
    return False


def _iter_target_imports(tree: ast.AST) -> list[ast.ImportFrom]:
    """单次遍历取「需要检查的绝对 apps.* / plugins.* 导入」，跳过 TYPE_CHECKING 块。

    这是守卫性能的核心：**只走一趟 AST**。原来对每个 import 节点都调一次
    ``_in_type_checking``，而它内部又把整棵树走一遍再 ``ast.dump`` 每个 If——
    于是每棵文件的成本是 O(imports × nodes)。实测这一项在原实现里占了
    50s / 93s，是超时的第一主因。
    """
    found: list[ast.ImportFrom] = []
    todo: list[tuple[ast.AST, bool]] = [(tree, False)]
    while todo:
        node, type_checking = todo.pop()
        if not type_checking and isinstance(node, ast.If) and _is_type_checking_test(node.test):
            # 整个 if 块（含 elif/else 子树）都是仅类型注解，不入栈检查
            type_checking = True
        if not type_checking and isinstance(node, ast.ImportFrom):
            module = node.module
            # 只看绝对导入；相对导入的 module 不是可解析路径
            if module and module.startswith(_SCAN_ROOTS):
                found.append(node)
        for child in ast.iter_child_nodes(node):
            todo.append((child, type_checking))
    return found


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


# 按模块名 memoize find_spec 结果：全仓库 ~2260 个文件里同一个 apps.* 模块被
# 成百上千处重复导入，而 find_spec 对「父包不存在」的路径会逐级重走 import
# machinery，实测去重前后差 4 倍以上（这是超时的第二主因）。
_MODULE_EXISTS_CACHE: dict[str, bool] = {}


def _module_exists(module: str) -> bool:
    """问解释器这模块是否真的存在。find_spec 可能抛异常（坏父包），一律算不存在。"""
    cached = _MODULE_EXISTS_CACHE.get(module)
    if cached is None:
        try:
            cached = importlib.util.find_spec(module) is not None
        except (ImportError, AttributeError, ValueError):
            cached = False
        _MODULE_EXISTS_CACHE[module] = cached
    return cached


def _collect_unresolvable() -> list[tuple[str, int, str]]:
    """返回 (相对路径, 行号, 模块名) 列表：绝对导入但模块不存在的。

    分两步：先扫 AST 收集**候选导入**与「去重后的模块名集合」，
    再只对这些去重模块做一次 ``find_spec``。AST 是纯内存操作、
    可重复走；``find_spec`` 会真正触发 import machinery（import 父包、
    读 ``__init__``），必须把重复调用降到最低。
    """
    importlib.invalidate_caches()
    _MODULE_EXISTS_CACHE.clear()
    check_plugins = _plugins_available()

    # (相对路径, 行号, 模块名) 与去重模块集合
    candidates: list[tuple[str, int, str]] = []
    modules: set[str] = set()
    for py in _iter_python_files():
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        for node in _iter_target_imports(tree):
            module = node.module
            assert module is not None  # _iter_target_imports 已过滤空 module
            # plugins 子模块未初始化（如 CI）时，plugins.* 一律不可解析，属环境差异
            # 覆盖 "plugins" 与 "plugins.xxx" 两种写法
            if not check_plugins and (module == "plugins" or module.startswith("plugins.")):
                continue
            candidates.append((str(py.relative_to(_BACKEND_ROOT)), node.lineno, module))
            modules.add(module)

    for module in modules:
        _module_exists(module)

    return sorted((rel, lineno, module) for rel, lineno, module in candidates if not _module_exists(module))


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
    caught = [node.module for node in _iter_target_imports(tree) if node.module and not _module_exists(node.module)]

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
