"""
Bug Condition Exploration Test: Reminders Quality Uplift

Property 1: Fault Condition - 架构违规与代码质量问题检测

针对 10 个确定性问题，将属性限定到具体的失败场景。
这些测试在未修复代码上 **预期失败**，失败即证明 bug 存在。
修复后这些测试应全部通过。

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path
from typing import Any

import pytest

# ── 路径常量 ──────────────────────────────────────────────────────────
BACKEND_ROOT: Path = Path(__file__).resolve().parent.parent.parent.parent
REMINDER_SERVICE_PATH: Path = BACKEND_ROOT / "apps" / "reminders" / "services" / "reminder_service.py"
REMINDER_API_PATH: Path = BACKEND_ROOT / "apps" / "reminders" / "api" / "reminder_api.py"
ADAPTER_PATH: Path = BACKEND_ROOT / "apps" / "reminders" / "services" / "reminder_service_adapter.py"
ADMIN_PATH: Path = BACKEND_ROOT / "apps" / "reminders" / "admin" / "reminder_admin.py"
MODELS_PATH: Path = BACKEND_ROOT / "apps" / "reminders" / "models.py"
SCHEMAS_PATH: Path = BACKEND_ROOT / "apps" / "reminders" / "schemas.py"


# ── 辅助函数 ──────────────────────────────────────────────────────────


def _read_source(path: Path) -> str:
    """读取源文件内容。"""
    return path.read_text(encoding="utf-8")


def _parse_ast(path: Path) -> ast.Module:
    """解析源文件 AST。"""
    return ast.parse(_read_source(path), filename=str(path))


def _get_class_node(tree: ast.Module, class_name: str) -> ast.ClassDef | None:
    """从 AST 中获取指定类定义节点。"""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    return None


def _get_function_node(parent: ast.AST, func_name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """从 AST 节点中获取指定函数/方法定义。"""
    for node in ast.walk(parent):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            return node
    return None


# ══════════════════════════════════════════════════════════════════════
# 测试 1: Service 层不应包含跨模块 Model 导入
# Validates: Requirements 1.1
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.property_test
def test_service_no_cross_module_model_imports() -> None:
    """
    **Validates: Requirements 1.1**

    检查 reminder_service.py 源码不包含
    `from apps.cases.models` 和 `from apps.contracts.models` 导入。
    未修复代码会失败。
    """
    source: str = _read_source(REMINDER_SERVICE_PATH)
    violations: list[str] = []

    pattern: re.Pattern[str] = re.compile(r"^\s*from\s+apps\.(cases|contracts)\.models\s+import\b", re.MULTILINE)
    for match in pattern.finditer(source):
        violations.append(match.group(0).strip())

    assert not violations, f"reminder_service.py 包含 {len(violations)} 处跨模块 Model 导入违规:\n" + "\n".join(
        f"  - {v}" for v in violations
    )


# ══════════════════════════════════════════════════════════════════════
# 测试 2: API 层 _get_service() 应通过工厂函数获取服务实例
# Validates: Requirements 1.2
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.property_test
def test_api_get_service_uses_factory() -> None:
    """
    **Validates: Requirements 1.2**

    检查 reminder_api.py 的 _get_service() 通过工厂函数获取服务实例，
    而非直接实例化 ReminderService()。
    未修复代码会失败。
    """
    tree: ast.Module = _parse_ast(REMINDER_API_PATH)
    func_node = _get_function_node(tree, "_get_service")
    assert func_node is not None, "_get_service 函数未找到"

    source_lines: list[str] = _read_source(REMINDER_API_PATH).splitlines()
    func_source: str = "\n".join(source_lines[func_node.lineno - 1 : func_node.end_lineno])

    # 期望: 调用 build_reminder_api_service()
    # 不期望: 直接实例化 _ReminderService() 或 ReminderService()
    has_factory_call: bool = "build_reminder_api_service" in func_source
    has_direct_instantiation: bool = bool(re.search(r"_?ReminderService\s*\(", func_source))

    assert has_factory_call and not has_direct_instantiation, (
        f"_get_service() 应通过工厂函数获取服务实例，而非直接实例化。\n当前实现:\n{func_source}"
    )


# ══════════════════════════════════════════════════════════════════════
# 测试 3: Adapter __init__ 应接受注入参数
# Validates: Requirements 1.3
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.property_test
def test_adapter_init_accepts_injection() -> None:
    """
    **Validates: Requirements 1.3**

    检查 ReminderServiceAdapter.__init__ 接受注入参数而非硬编码实例化。
    未修复代码会失败。
    """
    tree: ast.Module = _parse_ast(ADAPTER_PATH)
    cls_node = _get_class_node(tree, "ReminderServiceAdapter")
    assert cls_node is not None, "ReminderServiceAdapter 类未找到"

    init_node = _get_function_node(cls_node, "__init__")
    assert init_node is not None, "__init__ 方法未找到"

    # 检查 __init__ 参数列表中是否有 service 参数（除 self 外）
    param_names: list[str] = [arg.arg for arg in init_node.args.args if arg.arg != "self"]

    assert "service" in param_names, (
        f"ReminderServiceAdapter.__init__ 应接受 'service' 注入参数。\n当前参数: {param_names}"
    )


# ══════════════════════════════════════════════════════════════════════
# 测试 4: create_contract_reminders_internal 中 field_name 使用 i18n
# Validates: Requirements 1.4
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.property_test
def test_adapter_contract_reminders_uses_normalize_target_id_with_i18n() -> None:
    """
    **Validates: Requirements 1.4**

    检查 create_contract_reminders_internal 使用 normalize_target_id 校验
    contract_id，且 field_name 使用 _() i18n 包装。
    未修复代码会失败（未调用 normalize_target_id，使用内联 `if not contract_id`）。
    """
    tree: ast.Module = _parse_ast(ADAPTER_PATH)
    cls_node = _get_class_node(tree, "ReminderServiceAdapter")
    assert cls_node is not None

    func_node = _get_function_node(cls_node, "create_contract_reminders_internal")
    assert func_node is not None, "create_contract_reminders_internal 方法未找到"

    source_lines: list[str] = _read_source(ADAPTER_PATH).splitlines()
    func_source: str = "\n".join(source_lines[func_node.lineno - 1 : func_node.end_lineno])

    # 期望: 使用 normalize_target_id(..., field_name=_("合同ID"))
    has_normalize_call: bool = "normalize_target_id" in func_source
    has_i18n_field_name: bool = bool(re.search(r'field_name\s*=\s*_\(\s*"合同ID"\s*\)', func_source))

    assert has_normalize_call and has_i18n_field_name, (
        f"create_contract_reminders_internal 应使用 normalize_target_id 校验 "
        f"contract_id，且 field_name 使用 _() i18n 包装。\n"
        f"发现 normalize_target_id: {has_normalize_call}, "
        f"发现 i18n field_name: {has_i18n_field_name}"
    )


# ══════════════════════════════════════════════════════════════════════
# 测试 5: get_existing_due_times 应抛出 ValidationException 而非 assert
# Validates: Requirements 1.5
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.property_test
def test_service_get_existing_due_times_validates_none_input() -> None:
    """
    **Validates: Requirements 1.5**

    当 case_log_id 经 normalize 后为 None 时，get_existing_due_times 应抛出
    ValidationException。
    未修复代码会失败（既无 assert 也无 ValidationException，直接查询）。
    """
    tree: ast.Module = _parse_ast(REMINDER_SERVICE_PATH)
    cls_node = _get_class_node(tree, "ReminderService")
    assert cls_node is not None

    func_node = _get_function_node(cls_node, "get_existing_due_times")
    assert func_node is not None, "get_existing_due_times 方法未找到"

    source_lines: list[str] = _read_source(REMINDER_SERVICE_PATH).splitlines()
    func_source: str = "\n".join(source_lines[func_node.lineno - 1 : func_node.end_lineno])

    # 不期望: assert 语句
    has_assert: bool = any(isinstance(node, ast.Assert) for node in ast.walk(func_node))
    assert not has_assert, "get_existing_due_times 不应使用 assert 做运行时校验"

    # 期望: 对 None 输入 raise ValidationException
    has_validation_raise: bool = "ValidationException" in func_source and "raise" in func_source

    assert has_validation_raise, (
        "get_existing_due_times 应在 case_log_id 为 None 时 raise ValidationException，当前实现缺少此校验"
    )


# ══════════════════════════════════════════════════════════════════════
# 测试 6: Reminder.clean() 应使用 is not None 而非 bool()
# Validates: Requirements 1.6
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.property_test
def test_model_clean_uses_is_not_none() -> None:
    """
    **Validates: Requirements 1.6**

    Reminder.clean() 使用 `is not None` 而非 `bool()` 判断，
    contract_id=0 时行为正确。
    未修复代码会失败。
    """
    tree: ast.Module = _parse_ast(MODELS_PATH)
    cls_node = _get_class_node(tree, "Reminder")
    assert cls_node is not None

    func_node = _get_function_node(cls_node, "clean")
    assert func_node is not None, "clean 方法未找到"

    source_lines: list[str] = _read_source(MODELS_PATH).splitlines()
    func_source: str = "\n".join(source_lines[func_node.lineno - 1 : func_node.end_lineno])

    # 不期望: bool(self.contract_id) 或 bool(self.case_log_id)
    has_bool_call: bool = bool(re.search(r"bool\(self\.(contract_id|case_log_id)\)", func_source))
    # 期望: is not None
    has_is_not_none: bool = "is not None" in func_source

    assert not has_bool_call, f"Reminder.clean() 不应使用 bool() 判断，应使用 is not None。\n当前实现:\n{func_source}"
    assert has_is_not_none, f"Reminder.clean() 应使用 'is not None' 进行绑定互斥校验。\n当前实现:\n{func_source}"


# ══════════════════════════════════════════════════════════════════════
# 测试 7: ReminderAdmin 应包含 readonly_fields
# Validates: Requirements 1.7
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.property_test
def test_admin_has_readonly_fields() -> None:
    """
    **Validates: Requirements 1.7**

    ReminderAdmin 包含 readonly_fields = ("created_at",)。
    未修复代码会失败。
    """
    tree: ast.Module = _parse_ast(ADMIN_PATH)
    cls_node = _get_class_node(tree, "ReminderAdmin")
    assert cls_node is not None, "ReminderAdmin 类未找到"

    # 查找 readonly_fields 赋值
    has_readonly_fields: bool = False
    includes_created_at: bool = False

    for node in ast.walk(cls_node):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            # 获取赋值目标名称
            targets: list[str] = []
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        targets.append(target.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                targets.append(node.target.id)

            if "readonly_fields" in targets:
                has_readonly_fields = True
                # 检查值中是否包含 "created_at"
                source_lines: list[str] = _read_source(ADMIN_PATH).splitlines()
                line_source: str = source_lines[node.lineno - 1]
                if node.end_lineno:
                    line_source = "\n".join(source_lines[node.lineno - 1 : node.end_lineno])
                if "created_at" in line_source:
                    includes_created_at = True

    assert has_readonly_fields, "ReminderAdmin 缺少 readonly_fields 配置"
    assert includes_created_at, "ReminderAdmin.readonly_fields 应包含 'created_at'"


# ══════════════════════════════════════════════════════════════════════
# 测试 8: create_reminder_internal 应对 content 调用 normalize_content
# Validates: Requirements 1.8
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.property_test
def test_adapter_create_reminder_internal_normalizes_content() -> None:
    """
    **Validates: Requirements 1.8**

    create_reminder_internal 对 content 调用 normalize_content。
    未修复代码会失败（直接使用 str(reminder_type_label)）。
    """
    tree: ast.Module = _parse_ast(ADAPTER_PATH)
    cls_node = _get_class_node(tree, "ReminderServiceAdapter")
    assert cls_node is not None

    func_node = _get_function_node(cls_node, "create_reminder_internal")
    assert func_node is not None, "create_reminder_internal 方法未找到"

    source_lines: list[str] = _read_source(ADAPTER_PATH).splitlines()
    func_source: str = "\n".join(source_lines[func_node.lineno - 1 : func_node.end_lineno])

    # 检查 content= 参数是否经过 normalize_content 调用
    # 期望: content=normalize_content(str(reminder_type_label))
    # 不期望: content=str(reminder_type_label) (未经校验)
    has_normalize: bool = bool(re.search(r"content\s*=\s*normalize_content\(", func_source))

    assert has_normalize, (
        "create_reminder_internal 应对 content 调用 normalize_content。\n"
        "当前实现中 content 参数未经 normalize_content 校验。"
    )


# ══════════════════════════════════════════════════════════════════════
# 测试 9: ReminderUpdate 不应包含 validate_binding_exclusivity
# Validates: Requirements 1.9
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.property_test
def test_schema_no_redundant_validator() -> None:
    """
    **Validates: Requirements 1.9**

    ReminderUpdate 不包含 validate_binding_exclusivity 方法。
    未修复代码会失败（存在冗余校验）。
    """
    tree: ast.Module = _parse_ast(SCHEMAS_PATH)
    cls_node = _get_class_node(tree, "ReminderUpdate")
    assert cls_node is not None, "ReminderUpdate 类未找到"

    # 检查是否存在 validate_binding_exclusivity 方法
    has_redundant_validator: bool = _get_function_node(cls_node, "validate_binding_exclusivity") is not None

    assert not has_redundant_validator, (
        "ReminderUpdate 包含冗余的 validate_binding_exclusivity 方法，绑定互斥校验应由 Service 层统一负责"
    )


# ══════════════════════════════════════════════════════════════════════
# 测试 10: normalize_target_id 调用的 field_name 统一使用 i18n
# Validates: Requirements 1.10
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.property_test
def test_all_normalize_target_id_field_names_use_i18n() -> None:
    """
    **Validates: Requirements 1.10**

    所有 normalize_target_id 调用的 field_name 参数统一使用 i18n 包装。
    检查 reminder_service.py 和 reminder_service_adapter.py 中的所有调用。
    未修复代码会失败。
    """
    files_to_check: list[Path] = [REMINDER_SERVICE_PATH, ADAPTER_PATH]
    violations: list[str] = []

    # 匹配 field_name="xxx" (硬编码，未用 _() 包装)
    hardcoded_pattern: re.Pattern[str] = re.compile(r'normalize_target_id\([^)]*field_name\s*=\s*"[^"]*"')
    # 匹配 field_name=_("xxx") (正确的 i18n 包装)
    i18n_pattern: re.Pattern[str] = re.compile(r'normalize_target_id\([^)]*field_name\s*=\s*_\(\s*"[^"]*"\s*\)')

    for file_path in files_to_check:
        source: str = _read_source(file_path)
        rel_path: str = str(file_path.relative_to(BACKEND_ROOT))

        for line_no, line in enumerate(source.splitlines(), start=1):
            if "normalize_target_id" not in line or "field_name" not in line:
                continue

            # 检查该行是否有硬编码的 field_name
            if hardcoded_pattern.search(line) and not i18n_pattern.search(line):
                violations.append(f"  - {rel_path}:{line_no} {line.strip()}")

    assert not violations, (
        f"发现 {len(violations)} 处 normalize_target_id 的 field_name 未使用 i18n 包装:\n" + "\n".join(violations)
    )
