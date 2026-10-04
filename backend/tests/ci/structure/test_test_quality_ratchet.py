"""Ratchet tests for test-quality anti-patterns: zero-assert & pure status-code.

AST-scans every test function under ``tests/ci/`` and fails when the count of
either anti-pattern grows beyond its baseline:

1. **Zero-assertion tests** — the function body contains no ``assert``
   statement, no ``assert*`` method call (unittest ``self.assertEqual`` /
   mock ``assert_called_once_with`` / ``self.assertRaises``), no
   ``raises``/``fail``/``xfail``/``skip``/``exit`` call (``pytest.raises``,
   ``self.fail``) and no ``raise AssertionError``. Functions decorated with
   ``skip``/``xfail`` are exempt.

2. **Pure status-code tests** — exactly one ``assert`` statement, no other
   assertion signal, and the assertion only compares ``.status_code``
   (e.g. ``assert response.status_code == 200``). These verify routing +
   serialization at best and regress silently at worst; strengthen them with
   payload / side-effect assertions instead.

Baselines were measured on 2026-10-03 after the integration-layer cleanup
batches (128 pure status-code tests cleared, see 966c3d67); on 2026-10-04 the
remaining 163 unit-layer pure status-code tests were cleared to 0 as well.
The remaining zero-assert tests are intentional fail-via-exception patterns
(property tests calling ``json.loads`` / "never raises" contracts).
Only lower these baselines; never raise them.
"""

from __future__ import annotations

import ast
from pathlib import Path

# ── Ratchet baselines ──────────────────────────────────────────
# Measured 2026-10-03 (AST scan of all 27468 test functions under tests/ci/).
# Zero-assert: integration 1 (smoke_check contract, fail-via-exception),
# property 4 (hypothesis fail-via-exception), unit 1 (schemas_and_services
# coverage). Pure status-code: unit 163 cleared to 0 on 2026-10-04 (unit-layer
# coverage batches strengthened with payload/DB-state/mock assertions).
# 清理后下调；严禁上调。
ZERO_ASSERTION_RATCHET = 6
PURE_STATUS_CODE_RATCHET = 0

_TESTS_CI_ROOT = Path(__file__).resolve().parents[1]

# pytest.raises / self.fail / pytest.xfail / pytest.skip / pytest.exit
_RAISES_LIKE_NAMES = {"raises", "fail", "xfail", "skip", "exit"}


def _iter_test_functions(tree: ast.Module):
    """Yield ``(func_node, class_name)`` for every ``test_*`` function or method."""

    def _walk(node: ast.AST, class_name: str | None):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if child.name.startswith("test_"):
                    yield child, class_name
            elif isinstance(child, ast.ClassDef):
                yield from _walk(child, child.name)
            else:
                yield from _walk(child, class_name)

    yield from _walk(tree, None)


def _has_skip_or_xfail_decorator(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in func.decorator_list:
        if "skip" in ast.unparse(dec) or "xfail" in ast.unparse(dec):
            return True
    return False


def _is_assertion_call(call: ast.Call) -> bool:
    """``self.assertEqual(...)``, ``mock.assert_called_once(...)``, ``pytest.raises(...)`` etc."""
    func = call.func
    if isinstance(func, ast.Attribute):
        if func.attr.startswith("assert"):
            return True
        return func.attr in _RAISES_LIKE_NAMES
    if isinstance(func, ast.Name):
        return func.id in _RAISES_LIKE_NAMES
    return False


def _raises_assertion_error(node: ast.Raise) -> bool:
    exc = node.exc
    if exc is None:
        return False
    if isinstance(exc, ast.Name):
        return exc.id == "AssertionError"
    if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
        return exc.func.id == "AssertionError"
    return False


def _assertion_signals(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[int, bool, list[ast.Assert]]:
    """Return ``(assert_stmt_count, has_other_signal, assert_nodes)``."""
    assert_nodes: list[ast.Assert] = []
    has_other_signal = False
    for sub in ast.walk(func):
        if isinstance(sub, ast.Assert):
            assert_nodes.append(sub)
        elif (isinstance(sub, ast.Call) and _is_assertion_call(sub)) or (
            isinstance(sub, ast.Raise) and _raises_assertion_error(sub)
        ):
            has_other_signal = True
    return len(assert_nodes), has_other_signal, assert_nodes


def _is_status_code_only(test: ast.expr) -> bool:
    """True when the compared expression only touches ``.status_code``."""

    def _touches_status_code(node: ast.expr) -> bool:
        return isinstance(node, ast.Attribute) and node.attr == "status_code"

    if not isinstance(test, ast.Compare):
        return False
    return _touches_status_code(test.left) or any(_touches_status_code(c) for c in test.comparators)


def _scan_tests_ci() -> tuple[list[str], list[str]]:
    """Scan ``tests/ci/`` and return ``(zero_assert_locations, pure_status_locations)``."""
    zero_assert: list[str] = []
    pure_status: list[str] = []

    for py_file in sorted(_TESTS_CI_ROOT.rglob("*.py")):
        if "__pycache__" in str(py_file) or py_file.name == "conftest.py":
            continue
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for func, class_name in _iter_test_functions(tree):
            if _has_skip_or_xfail_decorator(func):
                continue
            n_asserts, has_other_signal, assert_nodes = _assertion_signals(func)
            qualname = f"{class_name}.{func.name}" if class_name else func.name
            location = f"{py_file.relative_to(_TESTS_CI_ROOT)}:{func.lineno} {qualname}"

            if n_asserts == 0 and not has_other_signal:
                zero_assert.append(location)
            elif n_asserts == 1 and not has_other_signal and _is_status_code_only(assert_nodes[0].test):
                pure_status.append(location)

    return zero_assert, pure_status


def test_no_zero_assertion_tests_beyond_ratchet() -> None:
    """Zero-assertion test functions must not grow beyond the baseline."""
    zero_assert, _ = _scan_tests_ci()
    assert len(zero_assert) <= ZERO_ASSERTION_RATCHET, (
        f"Found {len(zero_assert)} zero-assertion test function(s), exceeding ratchet "
        f"baseline {ZERO_ASSERTION_RATCHET} (allowed residue: fail-via-exception "
        f"property/contract tests). Every test must assert something via assert / "
        f"assert* call / pytest.raises / self.fail / raise AssertionError:\n"
        + "\n".join(f"  {loc}" for loc in zero_assert)
    )


def test_no_pure_status_code_tests_beyond_ratchet() -> None:
    """Tests asserting only ``status_code`` must not grow beyond the baseline."""
    _, pure_status = _scan_tests_ci()
    assert len(pure_status) <= PURE_STATUS_CODE_RATCHET, (
        f"Found {len(pure_status)} pure status-code test function(s), exceeding ratchet "
        f"baseline {PURE_STATUS_CODE_RATCHET}. A lone ``assert resp.status_code == N`` "
        f"verifies neither payload nor side effects — add content/DB-state/mock "
        f"assertions:\n" + "\n".join(f"  {loc}" for loc in pure_status)
    )
