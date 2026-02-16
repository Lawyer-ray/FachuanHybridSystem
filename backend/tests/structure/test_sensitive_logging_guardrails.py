import re
from pathlib import Path


_LOGGER_LINE = re.compile(r"\blogger\.\w+\(")
_SENSITIVE_MARKERS = [
    re.compile(r"\bauthorization\b", re.IGNORECASE),
    re.compile(r"\bhttp_authorization\b", re.IGNORECASE),
    re.compile(r"request\.headers", re.IGNORECASE),
    re.compile(r"request\.meta", re.IGNORECASE),
]


def test_no_sensitive_headers_logged_directly():
    backend_root = Path(__file__).parent.parent.parent
    apps_root = backend_root / "apps"

    violations: list[str] = []

    for py_file in apps_root.rglob("*.py"):
        if "migrations" in py_file.parts:
            continue
        try:
            lines = py_file.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue

        for idx, line in enumerate(lines, start=1):
            if not _LOGGER_LINE.search(line):
                continue
            if any(p.search(line) for p in _SENSITIVE_MARKERS):
                violations.append(f"{py_file}:{idx}:{line.strip()}")

    assert not violations, "Sensitive data may be logged:\n" + "\n".join(sorted(violations))
