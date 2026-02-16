import ast
from pathlib import Path


def test_automation_performance_endpoints_require_admin():
    backend_root = Path(__file__).parent.parent.parent
    api_py = backend_root / "apps" / "automation" / "api" / "performance_monitor_api.py"
    tree = ast.parse(api_py.read_text(encoding="utf-8"))

    endpoint_fns: list[ast.FunctionDef] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not node.decorator_list:
            continue
        is_endpoint = False
        for deco in node.decorator_list:
            if not isinstance(deco, ast.Call):
                continue
            if not isinstance(deco.func, ast.Attribute):
                continue
            if not isinstance(deco.func.value, ast.Name):
                continue
            if deco.func.value.id != "router":
                continue
            if deco.func.attr in {"get", "post", "put", "delete", "patch"}:
                is_endpoint = True
                break
        if is_endpoint:
            endpoint_fns.append(node)

    assert endpoint_fns

    for fn in endpoint_fns:
        found = False
        for call in ast.walk(fn):
            if not isinstance(call, ast.Call):
                continue
            if isinstance(call.func, ast.Name) and call.func.id == "ensure_admin_request":
                found = True
                break
        assert found, f"{fn.name} 必须调用 ensure_admin_request()"


def test_document_recognition_upload_validates_uploaded_file():
    backend_root = Path(__file__).parent.parent.parent
    admin_py = (
        backend_root
        / "apps"
        / "automation"
        / "admin"
        / "document_recognition"
        / "document_recognition_admin.py"
    )
    tree = ast.parse(admin_py.read_text(encoding="utf-8"))

    upload_view = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "upload_view":
            upload_view = node
            break
    assert upload_view is not None

    call = None
    for node in ast.walk(upload_view):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if not isinstance(node.func.value, ast.Name):
            continue
        if node.func.value.id == "Validators" and node.func.attr == "validate_uploaded_file":
            call = node
            break
    assert call is not None, "upload_view 必须调用 Validators.validate_uploaded_file()"

    allowed_ext = None
    for kw in call.keywords or []:
        if kw.arg != "allowed_extensions":
            continue
        if isinstance(kw.value, ast.List):
            values: list[str] = []
            for elt in kw.value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    values.append(elt.value)
            allowed_ext = values
    assert allowed_ext is not None
    assert ".pdf" in allowed_ext
    assert ".pd" not in allowed_ext
