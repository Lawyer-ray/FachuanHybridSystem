"""Test that the four-layer architecture constraints are respected.

Layer rules:
- API layer: factory functions, parameter extraction. NO Model.objects calls.
- Service layer: business logic, transactions, permissions. NO @staticmethod.
- Admin layer: UI configuration, factory functions. NO direct Service instantiation.
- Model layer: field definitions, @property. NO business methods, no custom save().

These are *structural smoke tests* — they catch obvious violations in the
source text. They are not exhaustive (e.g., dynamic attribute access is
not detected), but they establish a ratchet baseline for the most common
anti-patterns.
"""

from __future__ import annotations

import re
from pathlib import Path

_APPS_ROOT = Path(__file__).resolve().parents[3] / "apps"

# ── Ratchet baselines ─────────────────────────────────────────
# Current counts as of 2026-09-07. These set upper limits on
# violations; the goal is to drive them toward zero.
#
# 注意：CI 仅对 tests/ci/structure/ 做 collect-only（见 backend-ci.yml），
# 棘轮实际生效依赖本地全量 pytest，抬基线时须先跑真实计数。

# API layer calling Model.objects directly
# 2026-10-03：apps/*/api/ 下 .objects. 已全量清零（实测 0），基线 55 → 0，
# 任何回流立即失败。ORM 查询必须下沉到 Service 层。
API_MODEL_OBJECTS_RATCHET = 0

# Service layer using @staticmethod
# 2026-09-07 重校准：d93103c43 设立基线时实际已 251（同 commit 引入的
# automation 60 文件被漏数），后续 finance/client/oa_filing 增长至 254。
# 2026-09-11 抬至 257：document_parsing ParserFactory（create_parser/_resolve_auto_backend/
# _load_backend_class/_instantiate）与 ParseProviderService.get_provider 属纯工厂/工具函数。
# 2026-09-25 抬至 259（实跑计数，非估算）：pdf_splitting segment_detector
# （_normalize_title/_suggest_filename）、pdf_splitting split/service（_extract_layout_title）
# 与 document_parsing textin_backend（_positive_page_number）属纯解析/工具函数，
# 不持有实例或类状态。
# 2026-09-29 抬至 264（实跑计数，非估算）：main 侧 PR #499（document_recognition
# 视觉管线+确定性提取层：vlm_ocr/document_classifier/case_binding/_case_number_mixin
# 等）与 automation/cases 若干纯工具函数带来净增 5，本分支零新增。
# 2026-10-11 两轮下沉：264 → 197（零跨文件引用批），197 → 12（全量纯函数批，186 个）。
# 剩余 12 个为跨类同名（调用方导入易撞名）、与既有 import 同名的薄包装、
# 依赖类常量的真 classmethod 等个案，转换需逐个人工评估（改名或合并去重）。
SERVICE_STATIC_METHOD_RATCHET = 12


def _scan_api_model_objects() -> list[tuple[str, int, str]]:
    """Find Model.objects calls in API layer files."""
    violations: list[tuple[str, int, str]] = []
    pattern = re.compile(r"\.objects\.")

    for app_dir in sorted(_APPS_ROOT.iterdir()):
        if not app_dir.is_dir() or app_dir.name.startswith("_"):
            continue

        api_dir = app_dir / "api"
        if not api_dir.is_dir():
            continue

        for py_file in api_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            text = py_file.read_text(encoding="utf-8", errors="ignore")
            for line_no, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line):
                    violations.append((str(py_file.relative_to(_APPS_ROOT)), line_no, line.strip()))

    return violations


def _scan_service_staticmethod() -> list[tuple[str, int, str]]:
    """Find @staticmethod usage in Service layer files."""
    violations: list[tuple[str, int, str]] = []
    pattern = re.compile(r"@\s*staticmethod")

    for app_dir in sorted(_APPS_ROOT.iterdir()):
        if not app_dir.is_dir() or app_dir.name.startswith("_"):
            continue

        services_dir = app_dir / "services"
        if not services_dir.is_dir():
            continue

        for py_file in services_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            text = py_file.read_text(encoding="utf-8", errors="ignore")
            for line_no, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line):
                    violations.append((str(py_file.relative_to(_APPS_ROOT)), line_no, line.strip()))

    return violations


def test_api_layer_no_model_objects_calls() -> None:
    """API layer must not call Model.objects directly — use Service layer instead."""
    violations = _scan_api_model_objects()
    assert len(violations) <= API_MODEL_OBJECTS_RATCHET, (
        f"API layer contains {len(violations)} Model.objects call(s), "
        f"exceeding ratchet baseline {API_MODEL_OBJECTS_RATCHET}.\n"
        "Move ORM queries to Service layer.\n"
        + "\n".join(f"  {path}:{lineno}: {content}" for path, lineno, content in violations)
    )


def test_service_layer_staticmethod_count_within_ratchet() -> None:
    """Service layer @staticmethod usage must not exceed ratchet baseline."""
    violations = _scan_service_staticmethod()
    assert len(violations) <= SERVICE_STATIC_METHOD_RATCHET, (
        f"Service layer contains {len(violations)} @staticmethod usage(s), "
        f"exceeding ratchet baseline {SERVICE_STATIC_METHOD_RATCHET}.\n"
        "Prefer instance methods with dependency injection.\n"
        + "\n".join(f"  {path}:{lineno}: {content}" for path, lineno, content in violations[:10])
    )


# ── 下沉函数被误当实例方法调用 ───────────────────────────────
def _scan_sunk_function_called_as_method() -> list[tuple[str, int, str]]:
    """检出 ``self._foo(...)`` 但 ``_foo`` 在本包内只是模块级函数（类里已无此方法）。

    v27.4.4「Service 层静态方法棘轮」把大量 @staticmethod 下沉为模块级纯函数
    （如 ``guarantee/base_mixin.py::_random_wait``）。若调用方仍写 ``self._foo(...)``，
    运行时才炸 AttributeError —— 静态方法棘轮只看是否还有 @staticmethod，
    看不到这类断链，曾导致「执行担保」接口两次 500。

    判定规则：包内**没有任何类**定义该名字，但**有**同名模块级函数 → 违规。

    以下两种情况不算违规（都已在实际代码中确认是合法写法）：
    1. 类体内以注解声明的可调用属性，如 ``_response_status: Callable[[Any], int]``；
    2. 类体内把同名模块级函数显式重新绑定为类属性，如
       ``_build_docx_response = staticmethod(_build_docx_response)``。
    同名实例属性（如 ``self._api_error_log``）不在函数集合里，不会误报。
    """
    import ast

    violations: list[tuple[str, int, str]] = []
    if not _APPS_ROOT.is_dir():
        return violations

    package_dirs = {p.parent for p in _APPS_ROOT.rglob("*.py") if "__pycache__" not in str(p)}
    for pkg_dir in sorted(package_dirs):
        py_files = sorted(p for p in pkg_dir.glob("*.py") if p.name != "__init__.py")
        if len(py_files) < 2:  # 单文件包谈不上「下沉到兄弟模块」
            continue

        class_methods: set[str] = set()
        module_funcs: set[str] = set()
        trees: list[tuple[Path, ast.Module]] = []
        for py_file in py_files:
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            trees.append((py_file, tree))
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    module_funcs.add(node.name)
                elif isinstance(node, ast.ClassDef):
                    for member in node.body:
                        if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            class_methods.add(member.name)
                        elif isinstance(member, ast.AnnAssign) and isinstance(member.target, ast.Name):
                            # 单独注解声明的类属性（含 Callable[...] 协议声明）
                            class_methods.add(member.target.id)
                        elif isinstance(member, ast.Assign):
                            # ``_foo = staticmethod(_foo)`` 这类显式重新绑定
                            for tgt in member.targets:
                                if isinstance(tgt, ast.Name):
                                    class_methods.add(tgt.id)

        sunk = module_funcs - class_methods
        if not sunk:
            continue

        for py_file, tree in trees:
            for node in ast.walk(tree):
                if not isinstance(node, ast.Attribute):
                    continue
                value = node.value
                if not (isinstance(value, ast.Name) and value.id == "self"):
                    continue
                if node.attr in sunk:
                    violations.append(
                        (str(py_file.relative_to(_APPS_ROOT)), node.lineno, f"self.{node.attr}（本包内为模块级函数）")
                    )
    return violations


def test_no_sunk_function_called_as_instance_method() -> None:
    """下沉到模块级的纯函数必须直接调用，不能写成 self._foo(...)。"""
    violations = _scan_sunk_function_called_as_method()
    assert not violations, (
        f"发现 {len(violations)} 处把模块级函数当实例方法调用（运行时会 AttributeError）：\n"
        + "\n".join(f"  {path}:{lineno}: {content}" for path, lineno, content in violations[:15])
    )
