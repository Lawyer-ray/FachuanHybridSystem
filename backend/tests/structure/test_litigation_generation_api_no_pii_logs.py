import ast
from pathlib import Path


def test_litigation_generation_api_logs_do_not_include_plaintiff_defendant():
    backend_root = Path(__file__).parent.parent.parent
    api_py = backend_root / "apps" / "documents" / "api" / "litigation_generation_api.py"
    tree = ast.parse(api_py.read_text(encoding="utf-8"))

    forbidden = {"plaintiff", "defendant"}
    violations = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if not isinstance(node.func.value, ast.Name):
            continue
        if node.func.value.id != "logger":
            continue
        for kw in node.keywords or []:
            if kw.arg != "extra":
                continue
            if not isinstance(kw.value, ast.Dict):
                continue
            for key in kw.value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str) and key.value in forbidden:
                    violations.append(key.value)

    assert not violations
