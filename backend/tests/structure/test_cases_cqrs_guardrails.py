import ast
from pathlib import Path


def test_cases_api_uses_query_and_mutation_facades():
    backend_root = Path(__file__).parent.parent.parent
    api_py = backend_root / "apps" / "cases" / "api" / "case_api.py"
    tree = ast.parse(api_py.read_text(encoding="utf-8"))

    fn_by_name = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            fn_by_name[node.name] = node

    for name in ("list_cases", "get_case", "search_cases"):
        fn = fn_by_name.get(name)
        assert fn is not None
        calls = [
            n
            for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_get_case_query_facade"
        ]
        assert calls, f"{name} should call _get_case_query_facade()"

    for name in ("create_case_full", "create_case", "update_case", "delete_case"):
        fn = fn_by_name.get(name)
        assert fn is not None
        calls = [
            n
            for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_get_case_mutation_facade"
        ]
        assert calls, f"{name} should call _get_case_mutation_facade()"
