import ast
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"))


def _find_class(tree: ast.AST, class_name: str) -> ast.ClassDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    raise AssertionError(f"missing class: {class_name}")


def _find_method(class_node: ast.ClassDef, method_name: str) -> ast.FunctionDef:
    for node in class_node.body:
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            return node
    raise AssertionError(f"missing method: {class_node.name}.{method_name}")


def test_business_exception_to_dict_has_unified_contract():
    root = _project_root()
    path = root / "apps" / "core" / "exceptions" / "base.py"
    tree = _parse(path)

    cls = _find_class(tree, "BusinessException")
    method = _find_method(cls, "to_dict")

    return_nodes = [n for n in ast.walk(method) if isinstance(n, ast.Return)]
    assert return_nodes, "missing return in BusinessException.to_dict"

    dict_returns = [n.value for n in return_nodes if isinstance(n.value, ast.Dict)]
    assert dict_returns, "BusinessException.to_dict should return a dict literal"

    returned = dict_returns[0]
    keys = []
    for key_node in returned.keys:
        if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
            keys.append(key_node.value)

    expected_keys = {"success", "code", "message", "error", "errors"}
    assert expected_keys.issubset(set(keys)), f"BusinessException.to_dict missing keys: {expected_keys - set(keys)}"

    success_index = None
    for i, key_node in enumerate(returned.keys):
        if isinstance(key_node, ast.Constant) and key_node.value == "success":
            success_index = i
            break
    assert success_index is not None, "BusinessException.to_dict must include success"
    assert isinstance(returned.values[success_index], ast.Constant) and returned.values[success_index].value is False


def test_llm_handler_registration_does_not_swallow_unexpected_exceptions():
    root = _project_root()
    path = root / "apps" / "core" / "exceptions" / "handlers.py"
    tree = _parse(path)

    register_fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "register_exception_handlers":
            register_fn = node
            break
    assert register_fn is not None, "missing function: register_exception_handlers"

    llm_try = None
    for node in ast.walk(register_fn):
        if not isinstance(node, ast.Try):
            continue
        import_nodes = [n for n in node.body if isinstance(n, ast.ImportFrom)]
        if any(n.module == "apps.core.llm.exceptions" for n in import_nodes if n.module):
            llm_try = node
            break
    assert llm_try is not None, "missing try block importing apps.core.llm.exceptions"

    handler_types = []
    for h in llm_try.handlers:
        if h.type is None:
            handler_types.append(None)
        elif isinstance(h.type, ast.Name):
            handler_types.append(h.type.id)
        else:
            handler_types.append(type(h.type).__name__)

    assert "ImportError" in handler_types, f"LLM handler try must catch ImportError, got: {handler_types}"
    assert "Exception" in handler_types, f"LLM handler try must catch Exception, got: {handler_types}"

    exception_handler = None
    for h in llm_try.handlers:
        if isinstance(h.type, ast.Name) and h.type.id == "Exception":
            exception_handler = h
            break
    assert exception_handler is not None

    has_logger_exception = False
    for n in ast.walk(exception_handler):
        if not isinstance(n, ast.Call):
            continue
        func = n.func
        if isinstance(func, ast.Attribute) and func.attr == "exception" and isinstance(func.value, ast.Name):
            if func.value.id == "logger":
                has_logger_exception = True
                break
    assert has_logger_exception, "LLM handler Exception branch must call logger.exception"
