from pathlib import Path


def test_chatopenai_instantiation_only_in_core_llm():
    root = Path(__file__).resolve().parents[2]
    apps_root = root / "apps"
    allowed_prefix = apps_root / "core" / "llm"

    offenders = []
    for py_file in apps_root.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        if allowed_prefix in py_file.parents:
            continue
        content = py_file.read_text(encoding="utf-8")
        if "ChatOpenAI(" in content:
            offenders.append(py_file)

    assert offenders == [], "ChatOpenAI() must only be instantiated in apps/core/llm: " + ", ".join(
        str(p.relative_to(root)) for p in offenders
    )
