"""Ratchet test for _internal() cross-module calls.

Counts _internal() calls across the codebase and ensures the count
never increases beyond the established baseline. As _internal calls
are refactored to public ServiceLocator interfaces, this baseline
should be lowered.

See: P1-3 ServiceLocator + _internal boundary convergence
"""

from __future__ import annotations

import re
from pathlib import Path

# ── Ratchet baseline ──────────────────────────────────────────
# Current count as of 2026-04-20. Only lower this value when
# _internal() calls are successfully eliminated / promoted.
_INTERNAL_CALL_RATCHET = 529

_APPS_ROOT = Path(__file__).resolve().parents[3] / "apps"


def _count_internal_calls() -> int:
    """Count all ``_internal(`` occurrences under apps/."""
    count = 0
    pattern = re.compile(r"_internal\(")
    for py_file in _APPS_ROOT.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        text = py_file.read_text(encoding="utf-8", errors="ignore")
        count += len(pattern.findall(text))
    return count


def test_internal_call_count_does_not_exceed_ratchet() -> None:
    """The number of _internal() calls must not grow beyond the ratchet baseline."""
    current = _count_internal_calls()
    assert current <= _INTERNAL_CALL_RATCHET, (
        f"_internal() call count {current} exceeds ratchet baseline "
        f"{_INTERNAL_CALL_RATCHET}. Promote _internal calls to public "
        f"ServiceLocator interfaces, then lower the ratchet value."
    )
