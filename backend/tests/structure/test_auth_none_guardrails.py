import ast
from pathlib import Path


def test_auth_none_is_only_used_for_register_endpoint():  # noqa: C901
    backend_root = Path(__file__).parent.parent.parent
    apps_root = backend_root / "apps"

    allowed = {
        (apps_root / "organization" / "api" / "auth_api.py").resolve().as_posix(): {
            "register_view",
            "login_view",
            "logout_view",
        },
        # i18n 语言列表接口无需认证：用户登录前需要获取支持的语言列表
        (apps_root / "core" / "api" / "i18n_api.py").resolve().as_posix(): {
            "list_languages",
        },
    }

    violations: list[str] = []

    for py_file in apps_root.rglob("*.py"):
        if "migrations" in py_file.parts:
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            fn_name = node.name
            for deco in node.decorator_list:
                if not isinstance(deco, ast.Call):
                    continue
                for kw in deco.keywords or []:
                    if kw.arg != "auth":
                        continue
                    if not isinstance(kw.value, ast.Constant) or kw.value.value is not None:
                        continue

                    file_key = py_file.resolve().as_posix()
                    if fn_name in allowed.get(file_key, set()):
                        continue
                    violations.append(f"{py_file}:{fn_name}")

    assert not violations, "Unexpected auth=None usages:\n" + "\n".join(sorted(violations))
