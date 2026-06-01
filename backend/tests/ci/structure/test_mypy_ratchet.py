"""Ratchet test for mypy ``ignore_errors = True`` entries.

Counts ``ignore_errors = True`` entries in mypy.ini and ensures the
count never increases beyond the established baseline. As type debt
is resolved and modules are properly typed, this baseline should be
lowered.

See: P1-2 Stabilize mypy checking pipeline
"""

from __future__ import annotations

import re
from pathlib import Path

# ── Ratchet baseline ──────────────────────────────────────────
# Current count as of 2026-04-20. Only lower this value when
# ignore_errors entries are removed or replaced with precise
# disable_error_code directives.
MYPY_IGNORE_ERRORS_RATCHET = 108

_MYPY_INI = Path(__file__).resolve().parents[3] / "mypy.ini"


def _count_ignore_errors() -> int:
    """Count ``ignore_errors = True`` entries in mypy.ini."""
    if not _MYPY_INI.exists():
        return 0
    text = _MYPY_INI.read_text(encoding="utf-8")
    return len(re.findall(r"ignore_errors\s*=\s*True", text))


def test_mypy_ignore_errors_count_does_not_exceed_ratchet() -> None:
    """The number of ``ignore_errors = True`` entries must not grow beyond the ratchet baseline."""
    current = _count_ignore_errors()
    assert current <= MYPY_IGNORE_ERRORS_RATCHET, (
        f"mypy ignore_errors count {current} exceeds ratchet baseline "
        f"{MYPY_IGNORE_ERRORS_RATCHET}. Fix type debt in the affected "
        f"modules and remove ignore_errors entries, then lower the ratchet value."
    )
