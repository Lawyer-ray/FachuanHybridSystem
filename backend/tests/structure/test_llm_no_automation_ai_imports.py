from pathlib import Path


def test_core_llm_does_not_depend_on_automation_ai_module():
    backend_root = Path(__file__).parent.parent.parent
    llm_root = backend_root / "apps" / "core" / "llm"

    violations: list[str] = []

    for py_file in llm_root.rglob("*.py"):
        try:
            text = py_file.read_text(encoding="utf-8")
        except Exception:
            continue
        if "apps.automation.services.ai" in text:
            violations.append(str(py_file))

    assert not violations, "core/llm should not import automation/services/ai:\n" + "\n".join(sorted(violations))
