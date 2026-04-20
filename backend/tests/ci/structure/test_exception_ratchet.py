"""Ratchet test for broad ``except Exception`` usage.

Counts ``except Exception`` occurrences across the codebase and ensures
the count never increases beyond the established baseline. As specific
exception types are introduced (BrowserAutomationError, ImapConnectionError,
etc.), this baseline should be lowered.

See: P2-1 Reduce broad exception handling
"""

from __future__ import annotations

import re
from pathlib import Path

# ── Ratchet baseline ──────────────────────────────────────────
# Current count as of 2026-04-20. Only lower this value when
# except Exception is replaced with more specific exception types.
EXCEPT_EXCEPTION_RATCHET = 1454

_APPS_ROOT = Path(__file__).resolve().parents[3] / "apps"


def _count_except_exception() -> int:
    """Count all ``except Exception`` occurrences under apps/."""
    count = 0
    pattern = re.compile(r"except\s+Exception\b")
    for py_file in _APPS_ROOT.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        text = py_file.read_text(encoding="utf-8", errors="ignore")
        count += len(pattern.findall(text))
    return count


def test_except_exception_count_does_not_exceed_ratchet() -> None:
    """The number of ``except Exception`` must not grow beyond the ratchet baseline."""
    current = _count_except_exception()
    assert current <= EXCEPT_EXCEPTION_RATCHET, (
        f"except Exception count {current} exceeds ratchet baseline "
        f"{EXCEPT_EXCEPTION_RATCHET}. Replace with specific exception "
        f"types, then lower the ratchet value."
    )
