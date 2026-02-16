import re
from pathlib import Path


_SK_TOKEN = re.compile(r"\bsk-[a-zA-Z0-9]{16,}\b")


def test_no_sk_tokens_in_backend_non_test_sources():
    backend_root = Path(__file__).parent.parent.parent
    violations: list[str] = []

    for p in backend_root.rglob("*"):
        if not p.is_file():
            continue
        if "venv" in p.parts or ".git" in p.parts or "migrations" in p.parts:
            continue
        if "tests" in p.parts:
            continue
        if p.suffix.lower() not in {".py", ".md", ".yaml", ".yml", ".toml", ".txt", ".env", ".example"}:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if _SK_TOKEN.search(text):
            violations.append(str(p))

    assert not violations, "Found suspicious sk-* tokens in repo:\n" + "\n".join(sorted(violations))
