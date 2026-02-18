"""
Property-Based Tests for Cross-Module Import Validation

Feature: service-layer-decoupling, Property 1: 服务层无跨模块 Model 导入
Feature: service-layer-decoupling, Property 5: 依赖注入构造函数签名
Validates: Requirements 1.3, 5.1, 6.1, 6.2, 6.3, 6.4
"""

import ast
import re
from pathlib import Path
from typing import List, Optional, Set, Tuple

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

# 定义需要检查的模块
SERVICE_MODULES = [
    "cases",
    "contracts",
    "client",
    "organization",
    "documents",
    "automation",
    "litigation_ai",
    "reminders",
    "chat_records",
    "core",
]

# 定义每个模块允许导入的 Model 模块
# 每个模块只能导入自己的 models
ALLOWED_MODEL_IMPORTS = {
    "cases": {"cases"},
    "contracts": {"contracts"},
    "client": {"client"},
    "organization": {"organization"},
    "documents": {"documents"},
    "automation": {"automation"},
    "litigation_ai": {"litigation_ai"},
    "reminders": {"reminders"},
    "chat_records": {"chat_records"},
    "core": {"core"},
}

# 定义需要检查依赖注入的服务类
SERVICES_REQUIRING_DI = [
    ("contracts", "ContractService", ["case_service"]),
    ("cases", "CaseService", ["contract_service"]),
]


def get_backend_path() -> Path:
    """获取 backend 目录路径"""
    return Path(__file__).parent.parent.parent


def find_service_files(module_name: str) -> List[Path]:
    """
    查找模块的服务文件

    Args:
        module_name: 模块名称

    Returns:
        服务文件路径列表
    """
    backend_path = get_backend_path()
    services_dir = backend_path / "apps" / module_name / "services"

    if not services_dir.exists():
        return []

    # 查找所有 Python 文件（排除 __pycache__）
    service_files = []
    for py_file in services_dir.rglob("*.py"):
        if "__pycache__" not in str(py_file):
            service_files.append(py_file)

    return service_files


def find_schema_files(module_name: str) -> List[Path]:
    backend_path = get_backend_path()
    schema_file = backend_path / "apps" / module_name / "schemas.py"
    return [schema_file] if schema_file.exists() else []


def extract_cross_module_schema_imports(file_path: Path, current_module: str) -> List[Tuple[str, int, str]]:
    imports: List[Tuple[str, int, str]] = []

    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content)
        lines = content.split("\n")

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                match = re.match(r"apps\.(\w+)\.schemas", node.module)
                if match:
                    imported_module = match.group(1)
                    if imported_module not in (current_module, "core"):
                        imports.append((imported_module, node.lineno, lines[node.lineno - 1].strip()))
    except (SyntaxError, UnicodeDecodeError):
        pass

    return imports


def extract_model_imports(file_path: Path) -> List[Tuple[str, int, str]]:
    """
    从 Python 文件中提取 Model 导入语句

    Args:
        file_path: 文件路径

    Returns:
        (导入的模块名, 行号, 完整导入语句) 列表
    """
    imports = []

    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content)
        lines = content.split("\n")

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and ".models" in node.module:
                    # 提取模块名（如 apps.cases.models -> cases）
                    match = re.match(r"apps\.(\w+)\.models", node.module)
                    if match:
                        module_name = match.group(1)
                        line_content = lines[node.lineno - 1].strip()
                        imports.append((module_name, node.lineno, line_content))
    except (SyntaxError, UnicodeDecodeError) as e:
        pass

    return imports


def extract_schema_imports(file_path: Path) -> List[Tuple[int, str]]:
    imports: List[Tuple[int, str]] = []

    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content)
        lines = content.split("\n")

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and ".schemas" in node.module:
                    imports.append((node.lineno, lines[node.lineno - 1].strip()))
    except (SyntaxError, UnicodeDecodeError):
        pass

    return imports


def extract_service_locator_imports(file_path: Path) -> List[Tuple[int, str]]:
    imports: List[Tuple[int, str]] = []
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content)
        lines = content.split("\n")
        service_locator_modules = {
            "apps.core.interfaces",
            "apps.core.service_locator",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in service_locator_modules:
                for name in node.names:
                    if name.name == "ServiceLocator":
                        imports.append((node.lineno, lines[node.lineno - 1].strip()))
    except (SyntaxError, UnicodeDecodeError):
        pass
    return imports


def extract_internal_method_usages(file_path: Path) -> List[Tuple[int, str, str]]:
    usages: List[Tuple[int, str, str]] = []
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content)
        lines = content.split("\n")

        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr.endswith("_internal"):
                usages.append((node.lineno, node.attr, lines[node.lineno - 1].strip()))
    except (SyntaxError, UnicodeDecodeError):
        pass

    return usages


def check_schema_imports_in_services(module_name: str, file_path: Path) -> List[Tuple[str, int, str]]:
    violations: List[Tuple[str, int, str]] = []
    for line_no, import_stmt in extract_schema_imports(file_path):
        violations.append((str(file_path), line_no, import_stmt))
    return violations


def check_cross_module_imports(module_name: str, file_path: Path) -> List[Tuple[str, int, str, str]]:
    """
    检查文件中的跨模块 Model 导入

    Args:
        module_name: 当前模块名称
        file_path: 文件路径

    Returns:
        (文件路径, 行号, 导入的模块, 导入语句) 列表
    """
    violations = []
    allowed = ALLOWED_MODEL_IMPORTS.get(module_name, {module_name})

    model_imports = extract_model_imports(file_path)

    for imported_module, line_no, import_stmt in model_imports:
        if imported_module not in allowed:
            violations.append((str(file_path), line_no, imported_module, import_stmt))

    return violations


def extract_class_init_params(file_path: Path, class_name: str) -> Optional[List[str]]:
    """
    提取类的 __init__ 方法参数

    Args:
        file_path: 文件路径
        class_name: 类名

    Returns:
        参数名列表，如果类不存在返回 None
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                        # 提取参数名（排除 self）
                        params = []
                        for arg in item.args.args:
                            if arg.arg != "self":
                                params.append(arg.arg)
                        return params
        return None
    except (SyntaxError, UnicodeDecodeError):
        return None


def check_di_constructor_signature(module_name: str, class_name: str, required_params: List[str]) -> Tuple[bool, str]:
    """
    检查服务类的构造函数是否包含必要的依赖注入参数

    Args:
        module_name: 模块名称
        class_name: 类名
        required_params: 必需的参数名列表

    Returns:
        (是否通过, 错误信息)
    """
    backend_path = get_backend_path()
    services_dir = backend_path / "apps" / module_name / "services"

    # 查找包含该类的文件
    for py_file in services_dir.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue

        params = extract_class_init_params(py_file, class_name)
        if params is not None:
            # 检查是否包含所有必需参数
            missing = [p for p in required_params if p not in params]
            if missing:
                return False, f"{class_name} 缺少依赖注入参数: {', '.join(missing)}"
            return True, ""

    return False, f"未找到类 {class_name}"


# ============ Property Tests ============


@pytest.mark.property_test
def test_no_cross_module_model_imports_in_cases():
    """
    Property 1: 服务层无跨模块 Model 导入 - cases 模块

    *For any* 服务层 Python 文件，扫描其 import 语句时，
    不应发现直接导入其他模块 Model 的语句

    **Feature: service-layer-decoupling, Property 1: 服务层无跨模块 Model 导入**
    **Validates: Requirements 6.1**
    """
    module_name = "cases"
    all_violations = []

    for file_path in find_service_files(module_name):
        violations = check_cross_module_imports(module_name, file_path)
        all_violations.extend(violations)

    assert len(all_violations) == 0, f"发现 {module_name}/services 中存在跨模块 Model 导入:\n" + "\n".join(
        f"  {Path(path).name}:{line} - 导入了 {mod}.models: {stmt}" for path, line, mod, stmt in all_violations
    )


@pytest.mark.property_test
@pytest.mark.parametrize("module_name", SERVICE_MODULES)
def test_no_schema_imports_in_services(module_name: str):
    all_violations: List[Tuple[str, int, str]] = []
    for file_path in find_service_files(module_name):
        all_violations.extend(check_schema_imports_in_services(module_name, file_path))

    assert (
        len(all_violations) == 0
    ), f"发现 {module_name}/services 中存在对 schemas 的导入（API 层概念渗透到 service 层）:\n" + "\n".join(
        f"  {Path(path).name}:{line} - {stmt}" for path, line, stmt in all_violations
    )


@pytest.mark.property_test
@pytest.mark.parametrize("module_name", SERVICE_MODULES)
def test_no_cross_module_schema_imports_in_schema_layer(module_name: str):
    all_violations: List[Tuple[str, int, str, str]] = []
    for file_path in find_schema_files(module_name):
        for imported_module, line_no, stmt in extract_cross_module_schema_imports(file_path, module_name):
            all_violations.append((str(file_path), line_no, imported_module, stmt))

    assert (
        len(all_violations) == 0
    ), f"发现 {module_name}/schemas.py 中存在跨模块 schemas 导入（会放大 API Schema 层耦合）:\n" + "\n".join(
        f"  {Path(path).name}:{line} - 导入了 {imported}.schemas: {stmt}"
        for path, line, imported, stmt in all_violations
    )


@pytest.mark.property_test
def test_cases_api_does_not_import_service_locator():
    backend_path = get_backend_path()
    api_dir = backend_path / "apps" / "cases" / "api"

    violations = []
    for file_path in api_dir.glob("*.py"):
        if file_path.name == "__init__.py":
            continue
        for line, stmt in extract_service_locator_imports(file_path):
            violations.append((file_path.name, line, stmt))

    assert (
        len(violations) == 0
    ), "apps/cases/api/*.py 不应直接导入 ServiceLocator，请通过 composition/build_* 或 wiring 统一装配:\n" + "\n".join(
        f"  {name}:{line} - {stmt}" for name, line, stmt in violations
    )


@pytest.mark.property_test
def test_contracts_api_does_not_import_service_locator():
    backend_path = get_backend_path()
    api_dir = backend_path / "apps" / "contracts" / "api"

    violations = []
    for file_path in api_dir.glob("*.py"):
        if file_path.name == "__init__.py":
            continue
        for line, stmt in extract_service_locator_imports(file_path):
            violations.append((file_path.name, line, stmt))

    assert (
        len(violations) == 0
    ), "apps/contracts/api/*.py 不应直接导入 ServiceLocator，请通过 composition/build_* 或 wiring 统一装配:\n" + "\n".join(
        f"  {name}:{line} - {stmt}" for name, line, stmt in violations
    )


@pytest.mark.property_test
def test_documents_api_does_not_import_service_locator():
    backend_path = get_backend_path()
    api_dir = backend_path / "apps" / "documents" / "api"

    violations = []
    for file_path in api_dir.glob("*.py"):
        if file_path.name == "__init__.py":
            continue
        for line, stmt in extract_service_locator_imports(file_path):
            violations.append((file_path.name, line, stmt))

    assert (
        len(violations) == 0
    ), "apps/documents/api/*.py 不应直接导入 ServiceLocator，请通过 composition/build_* 或 wiring 统一装配:\n" + "\n".join(
        f"  {name}:{line} - {stmt}" for name, line, stmt in violations
    )


@pytest.mark.property_test
def test_api_layer_does_not_use_internal_methods():
    backend_path = get_backend_path()
    apps_dir = backend_path / "apps"

    violations: List[Tuple[str, int, str, str]] = []
    for file_path in apps_dir.rglob("api/**/*.py"):
        if file_path.name == "__init__.py":
            continue
        for line_no, attr, stmt in extract_internal_method_usages(file_path):
            violations.append((str(file_path.relative_to(backend_path)), line_no, attr, stmt))

    assert (
        len(violations) == 0
    ), "API 层不应调用 *_internal 方法，请改用 Facade/Service 的 *_ctx 或对外方法:\n" + "\n".join(
        f"  {path}:{line} - {attr} - {stmt}" for path, line, attr, stmt in violations
    )


@pytest.mark.property_test
def test_production_settings_forbid_lan_and_perm_open_access(monkeypatch):
    import runpy

    from cryptography.fernet import Fernet

    backend_path = get_backend_path()
    settings_path = backend_path / "apiSystem" / "apiSystem" / "settings.py"

    monkeypatch.setenv("DJANGO_DEBUG", "False")
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://example.com")
    monkeypatch.setenv("CSRF_TRUSTED_ORIGINS", "https://example.com")

    monkeypatch.setenv("DJANGO_ALLOW_LAN", "true")
    monkeypatch.setenv("DJANGO_LAN_ALLOWED_HOSTS", "192.168.1.2")
    with pytest.raises(RuntimeError):
        runpy.run_path(str(settings_path))

    monkeypatch.setenv("DJANGO_ALLOW_LAN", "")
    monkeypatch.setenv("PERM_OPEN_ACCESS", "true")
    with pytest.raises(RuntimeError):
        runpy.run_path(str(settings_path))


@pytest.mark.property_test
def test_no_cross_module_model_imports_in_contracts():
    """
    Property 1: 服务层无跨模块 Model 导入 - contracts 模块

    *For any* 服务层 Python 文件，扫描其 import 语句时，
    不应发现直接导入其他模块 Model 的语句

    **Feature: service-layer-decoupling, Property 1: 服务层无跨模块 Model 导入**
    **Validates: Requirements 6.2**
    """
    module_name = "contracts"
    all_violations = []

    for file_path in find_service_files(module_name):
        violations = check_cross_module_imports(module_name, file_path)
        all_violations.extend(violations)

    assert len(all_violations) == 0, f"发现 {module_name}/services 中存在跨模块 Model 导入:\n" + "\n".join(
        f"  {Path(path).name}:{line} - 导入了 {mod}.models: {stmt}" for path, line, mod, stmt in all_violations
    )


@pytest.mark.property_test
def test_no_cross_module_model_imports_in_client():
    """
    Property 1: 服务层无跨模块 Model 导入 - client 模块

    *For any* 服务层 Python 文件，扫描其 import 语句时，
    不应发现直接导入其他模块 Model 的语句

    **Feature: service-layer-decoupling, Property 1: 服务层无跨模块 Model 导入**
    **Validates: Requirements 6.3**
    """
    module_name = "client"
    all_violations = []

    for file_path in find_service_files(module_name):
        violations = check_cross_module_imports(module_name, file_path)
        all_violations.extend(violations)

    assert len(all_violations) == 0, f"发现 {module_name}/services 中存在跨模块 Model 导入:\n" + "\n".join(
        f"  {Path(path).name}:{line} - 导入了 {mod}.models: {stmt}" for path, line, mod, stmt in all_violations
    )


@pytest.mark.property_test
def test_no_cross_module_model_imports_in_organization():
    """
    Property 1: 服务层无跨模块 Model 导入 - organization 模块

    *For any* 服务层 Python 文件，扫描其 import 语句时，
    不应发现直接导入其他模块 Model 的语句

    **Feature: service-layer-decoupling, Property 1: 服务层无跨模块 Model 导入**
    **Validates: Requirements 6.4**
    """
    module_name = "organization"
    all_violations = []

    for file_path in find_service_files(module_name):
        violations = check_cross_module_imports(module_name, file_path)
        all_violations.extend(violations)

    assert len(all_violations) == 0, f"发现 {module_name}/services 中存在跨模块 Model 导入:\n" + "\n".join(
        f"  {Path(path).name}:{line} - 导入了 {mod}.models: {stmt}" for path, line, mod, stmt in all_violations
    )


@given(st.sampled_from(SERVICE_MODULES))
@settings(max_examples=100, deadline=None)
@pytest.mark.property_test
def test_no_cross_module_model_imports_property(module_name: str):
    """
    Property 1: 服务层无跨模块 Model 导入 (Property-Based)

    *For any* 服务模块，其 services 目录下的 Python 文件
    不应直接导入其他模块的 Model

    **Feature: service-layer-decoupling, Property 1: 服务层无跨模块 Model 导入**
    **Validates: Requirements 1.3, 6.1, 6.2, 6.3, 6.4**
    """
    service_files = find_service_files(module_name)
    assume(len(service_files) > 0)

    all_violations = []
    for file_path in service_files:
        violations = check_cross_module_imports(module_name, file_path)
        all_violations.extend(violations)

    assert len(all_violations) == 0, f"发现 {module_name}/services 中存在跨模块 Model 导入:\n" + "\n".join(
        f"  {Path(path).name}:{line} - 导入了 {mod}.models" for path, line, mod, stmt in all_violations[:5]
    )


@pytest.mark.property_test
def test_contract_service_has_di_constructor():
    """
    Property 5: 依赖注入构造函数签名 - ContractService

    *For any* 需要跨模块依赖的服务类，其构造函数应包含 Protocol 类型的可选参数

    **Feature: service-layer-decoupling, Property 5: 依赖注入构造函数签名**
    **Validates: Requirements 5.1**
    """
    passed, error = check_di_constructor_signature("contracts", "ContractService", ["case_service"])
    assert passed, error


@pytest.mark.property_test
def test_case_service_has_di_constructor():
    """
    Property 5: 依赖注入构造函数签名 - CaseService

    *For any* 需要跨模块依赖的服务类，其构造函数应包含 Protocol 类型的可选参数

    **Feature: service-layer-decoupling, Property 5: 依赖注入构造函数签名**
    **Validates: Requirements 5.1**
    """
    passed, error = check_di_constructor_signature("cases", "CaseService", ["contract_service"])
    assert passed, error


@given(st.sampled_from(SERVICES_REQUIRING_DI))
@settings(max_examples=100)
@pytest.mark.property_test
def test_di_constructor_signature_property(service_info: Tuple[str, str, List[str]]):
    """
    Property 5: 依赖注入构造函数签名 (Property-Based)

    *For any* 需要跨模块依赖的服务类，其构造函数应包含 Protocol 类型的可选参数

    **Feature: service-layer-decoupling, Property 5: 依赖注入构造函数签名**
    **Validates: Requirements 5.1**
    """
    module_name, class_name, required_params = service_info
    passed, error = check_di_constructor_signature(module_name, class_name, required_params)
    assert passed, error


# ============ Comprehensive Test ============


@pytest.mark.property_test
def test_all_service_modules_no_cross_imports():
    """
    综合测试：所有服务模块无跨模块 Model 导入

    扫描所有服务模块，确保没有跨模块的 Model 导入

    **Feature: service-layer-decoupling, Property 1: 服务层无跨模块 Model 导入**
    **Validates: Requirements 6.1, 6.2, 6.3, 6.4**
    """
    all_violations = []

    for module_name in SERVICE_MODULES:
        for file_path in find_service_files(module_name):
            violations = check_cross_module_imports(module_name, file_path)
            all_violations.extend(violations)

    if all_violations:
        # 按模块分组显示
        by_module = {}
        for path, line, mod, stmt in all_violations:
            # 从路径中提取模块名
            parts = Path(path).parts
            if "apps" in parts:
                idx = parts.index("apps")
                if idx + 1 < len(parts):
                    source_module = parts[idx + 1]
                    if source_module not in by_module:
                        by_module[source_module] = []
                    by_module[source_module].append((path, line, mod, stmt))

        error_msg = "发现跨模块 Model 导入:\n"
        for source_module, violations in by_module.items():
            error_msg += f"\n{source_module}/services:\n"
            for path, line, mod, stmt in violations:
                error_msg += f"  {Path(path).name}:{line} - 导入了 {mod}.models\n"

        assert False, error_msg
