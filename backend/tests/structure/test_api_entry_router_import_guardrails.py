from pathlib import Path


def test_api_entry_imports_app_routers_inside_function():
    root = Path(__file__).resolve().parents[2]
    api_py = root / "apiSystem" / "apiSystem" / "api.py"
    assert api_py.exists()
    content = api_py.read_text(encoding="utf-8")
    lines = content.splitlines()

    def_line = None
    for i, line in enumerate(lines):
        if line.startswith("def _register_app_routers"):
            def_line = i
            break

    assert def_line is not None

    for i, line in enumerate(lines):
        if not line.startswith("from apps."):
            continue
        if ".api" not in line:
            continue
        assert i > def_line
