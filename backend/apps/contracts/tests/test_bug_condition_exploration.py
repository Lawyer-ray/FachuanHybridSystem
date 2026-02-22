"""
Bug Condition Exploration Tests - Contracts 模块架构违规和 i18n 缺失检测

这些测试编码的是"期望行为"（修复后的正确状态）。
在未修复代码上运行时，测试会 FAIL，证明 bug 存在。
修复完成后，测试会 PASS，确认 bug 已修复。

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10**
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

# 项目根目录（backend/）
BACKEND_DIR: Path = Path(__file__).resolve().parent.parent.parent.parent


# ---------------------------------------------------------------------------
# 检测 1.1: Contract Model 的 primary_lawyer / all_lawyers 属性
#           不应包含 filter() / all() 查询逻辑
# ---------------------------------------------------------------------------
def test_1_1_contract_model_no_query_logic_in_properties() -> None:
    """
    期望行为：Contract Model 的 primary_lawyer / all_lawyers 属性不应包含
    ORM 查询逻辑（filter() / all()），查询应迁移到 Service 层。
    未修复时 FAIL，修复后 PASS。

    **Validates: Requirements 1.1**
    """
    model_file: Path = BACKEND_DIR / "apps" / "contracts" / "models" / "contract.py"
    source: str = model_file.read_text(encoding="utf-8")
    tree: ast.Module = ast.parse(source)

    issues: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != "Contract":
            continue
        for item in node.body:
            if not isinstance(item, ast.FunctionDef):
                continue
            if item.name not in ("primary_lawyer", "all_lawyers"):
                continue
            # 检查是否有 @property 装饰器
            is_property: bool = any(
                (isinstance(d, ast.Name) and d.id == "property")
                or (isinstance(d, ast.Attribute) and d.attr == "property")
                for d in item.decorator_list
            )
            if not is_property:
                continue
            # 检查方法体中是否包含 .filter() 或 .all() 调用
            func_source: str = ast.get_source_segment(source, item) or ""
            if ".filter(" in func_source or ".all()" in func_source:
                issues.append(
                    f"Contract.{item.name} 包含查询逻辑 "
                    f"(.filter()/.all())，违反 Model 层禁止业务方法规范"
                )

    assert not issues, (
        f"BUG 1.1: {'; '.join(issues)}。"
        "应将查询逻辑迁移到 ContractAssignmentQueryService"
    )


# ---------------------------------------------------------------------------
# 检测 1.2: ContractAdminService 不应包含 @staticmethod 装饰器
# ---------------------------------------------------------------------------
def test_1_2_contract_admin_service_no_staticmethod() -> None:
    """
    期望行为：ContractAdminService 不应使用 @staticmethod，
    应改为实例方法或委托给新版 Service。
    未修复时 FAIL，修复后 PASS。

    **Validates: Requirements 1.2**
    """
    service_file: Path = (
        BACKEND_DIR / "apps" / "contracts" / "services" / "contract_admin_service.py"
    )
    source: str = service_file.read_text(encoding="utf-8")
    tree: ast.Module = ast.parse(source)

    static_methods: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != "ContractAdminService":
            continue
        for item in node.body:
            if not isinstance(item, ast.FunctionDef):
                continue
            for dec in item.decorator_list:
                if isinstance(dec, ast.Name) and dec.id == "staticmethod":
                    static_methods.append(item.name)

    assert not static_methods, (
        f"BUG 1.2: ContractAdminService 包含 @staticmethod 方法: "
        f"{', '.join(static_methods)}。Service 层禁止使用 @staticmethod"
    )


# ---------------------------------------------------------------------------
# 检测 1.3: ContractAdminService.duplicate_contract / create_case_from_contract
#           不应直接调用 Model.objects
# ---------------------------------------------------------------------------
def test_1_3_contract_admin_service_no_direct_orm() -> None:
    """
    期望行为：ContractAdminService 的 duplicate_contract 和
    create_case_from_contract 不应直接调用 Model.objects，
    应委托给 ContractAdminMutationService。
    未修复时 FAIL，修复后 PASS。

    **Validates: Requirements 1.3**
    """
    service_file: Path = (
        BACKEND_DIR / "apps" / "contracts" / "services" / "contract_admin_service.py"
    )
    source: str = service_file.read_text(encoding="utf-8")
    tree: ast.Module = ast.parse(source)

    # Model.objects 调用模式
    orm_pattern: re.Pattern[str] = re.compile(
        r"\b(Contract|ContractParty|ContractAssignment|"
        r"SupplementaryAgreement|SupplementaryAgreementParty)\.objects\."
    )

    issues: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != "ContractAdminService":
            continue
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if item.name not in ("duplicate_contract", "create_case_from_contract"):
                continue
            func_source: str = ast.get_source_segment(source, item) or ""
            matches: list[str] = orm_pattern.findall(func_source)
            if matches:
                issues.append(
                    f"{item.name} 直接调用 Model.objects: "
                    f"{', '.join(set(matches))}"
                )

    assert not issues, (
        f"BUG 1.3: {'; '.join(issues)}。"
        "应委托给 ContractAdminMutationService"
    )


# ---------------------------------------------------------------------------
# 检测 1.4: ContractPaymentInline.clean_fs 中不应存在未被 _() 包裹的中文错误消息
# ---------------------------------------------------------------------------
def test_1_4_contract_payment_inline_i18n() -> None:
    """
    期望行为：ContractPaymentInline.clean_fs 中的错误消息应使用 _() 包裹。
    未修复时 FAIL，修复后 PASS。

    **Validates: Requirements 1.4**
    """
    admin_file: Path = (
        BACKEND_DIR / "apps" / "contracts" / "admin" / "contractpayment_admin.py"
    )
    source: str = admin_file.read_text(encoding="utf-8")

    # 查找裸中文字符串 "开票金额不能大于收款金额"（未被 _() 包裹）
    # 如果被 _() 包裹，形式为 _("开票金额不能大于收款金额")
    bare_chinese: re.Pattern[str] = re.compile(
        r'(?<!_\()"开票金额不能大于收款金额"'
    )
    matches: list[str] = bare_chinese.findall(source)

    assert not matches, (
        'BUG 1.4: clean_fs 中 "开票金额不能大于收款金额" 未被 _() 包裹，'
        "缺少 i18n 支持"
    )


# ---------------------------------------------------------------------------
# 检测 1.5: ContractAdminForm.representation_stages 的 label 不应硬编码中文
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("rel_path", [
    "apps/contracts/admin/contract_admin.py",
    "apps/contracts/admin/contract_forms_admin.py",
])
def test_1_5_contract_admin_form_label_i18n(rel_path: str) -> None:
    """
    期望行为：ContractAdminForm 的 representation_stages label
    应使用 _("代理阶段") 而非硬编码中文。
    未修复时 FAIL，修复后 PASS。

    **Validates: Requirements 1.5**
    """
    target_file: Path = BACKEND_DIR / rel_path
    source: str = target_file.read_text(encoding="utf-8")

    # 匹配 label="代理阶段" 但不匹配 label=_("代理阶段")
    bare_label: re.Pattern[str] = re.compile(r'label\s*=\s*"代理阶段"')
    matches: list[str] = bare_label.findall(source)

    assert not matches, (
        f'BUG 1.5: {rel_path} 中 label="代理阶段" 未被 _() 包裹，'
        "缺少 i18n 支持"
    )


# ---------------------------------------------------------------------------
# 检测 1.6: ContractServiceAdapter.get_contract_model_internal
#           不应返回原始 Model 实例
# ---------------------------------------------------------------------------
def test_1_6_adapter_no_raw_model_return() -> None:
    """
    期望行为：ContractServiceAdapter.get_contract_model_internal 应返回
    字典或 DTO 而非原始 Contract Model 实例，或标记为 deprecated。
    未修复时 FAIL，修复后 PASS。

    **Validates: Requirements 1.6**
    """
    adapter_file: Path = (
        BACKEND_DIR / "apps" / "contracts" / "services"
        / "_contract_service_adapter.py"
    )
    source: str = adapter_file.read_text(encoding="utf-8")
    tree: ast.Module = ast.parse(source)

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if node.name != "ContractServiceAdapter":
            continue
        for item in node.body:
            if not isinstance(item, ast.FunctionDef):
                continue
            if item.name != "get_contract_model_internal":
                continue
            func_source: str = ast.get_source_segment(source, item) or ""
            # 检查是否有 deprecated 标记
            has_deprecated: bool = "deprecated" in func_source.lower()
            # 检查是否直接返回 Model 实例（Contract.objects...get）
            returns_model: bool = (
                "Contract.objects" in func_source
                and ".get(" in func_source
                and "deprecated" not in func_source.lower()
            )
            if returns_model and not has_deprecated:
                pytest.fail(
                    "BUG 1.6: get_contract_model_internal 直接返回原始 "
                    "Contract Model 实例，破坏适配器层 DTO 封装边界。"
                    "应标记 deprecated 或重构为返回字典"
                )


# ---------------------------------------------------------------------------
# 检测 1.7: _contract_helpers_mixin.py._validate_fee_mode
#           中不应存在未被 _() 包裹的中文错误消息
# ---------------------------------------------------------------------------
def test_1_7_validate_fee_mode_i18n() -> None:
    """
    期望行为：_validate_fee_mode 中的所有中文错误消息应使用 _() 包裹。
    未修复时 FAIL，修复后 PASS。

    **Validates: Requirements 1.7**
    """
    mixin_file: Path = (
        BACKEND_DIR / "apps" / "contracts" / "services"
        / "_contract_helpers_mixin.py"
    )
    source: str = mixin_file.read_text(encoding="utf-8")
    tree: ast.Module = ast.parse(source)

    # 需要被 _() 包裹的中文消息
    expected_i18n_strings: list[str] = [
        "固定收费需填写金额",
        "半风险需填写前期金额",
        "半风险需填写风险比例",
        "全风险需填写风险比例",
        "自定义收费需填写条款文本",
        "收费模式验证失败",
        "无效的代理阶段",
    ]

    # 提取 _validate_fee_mode 和 _validate_stages 方法源码
    method_sources: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if not isinstance(item, ast.FunctionDef):
                continue
            if item.name in ("_validate_fee_mode", "_validate_stages"):
                seg: str = ast.get_source_segment(source, item) or ""
                method_sources.append(seg)

    combined: str = "\n".join(method_sources)

    bare_strings: list[str] = []
    for s in expected_i18n_strings:
        # 裸字符串: "xxx" 但前面没有 _(
        bare_pattern: re.Pattern[str] = re.compile(
            rf'(?<!_\()"{re.escape(s)}"'
        )
        if bare_pattern.search(combined):
            bare_strings.append(s)

    assert not bare_strings, (
        f"BUG 1.7: _contract_helpers_mixin.py 中以下错误消息未被 _() 包裹: "
        f"{bare_strings}"
    )


# ---------------------------------------------------------------------------
# 检测 1.8: contract_admin.py 不应包含与 action_mixin.py 重复的
#           response_change / response_add 方法
# ---------------------------------------------------------------------------
def test_1_8_contract_admin_no_duplicate_response_methods() -> None:
    """
    期望行为：ContractAdmin 应继承 ContractActionMixin，
    不应自行定义 response_change / response_add 方法。
    未修复时 FAIL，修复后 PASS。

    **Validates: Requirements 1.8**
    """
    admin_file: Path = (
        BACKEND_DIR / "apps" / "contracts" / "admin" / "contract_admin.py"
    )
    source: str = admin_file.read_text(encoding="utf-8")
    tree: ast.Module = ast.parse(source)

    duplicate_methods: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != "ContractAdmin":
            continue
        for item in node.body:
            if not isinstance(item, ast.FunctionDef):
                continue
            if item.name in ("response_change", "response_add"):
                duplicate_methods.append(item.name)

    assert not duplicate_methods, (
        f"BUG 1.8: ContractAdmin 中定义了与 action_mixin.py 重复的方法: "
        f"{', '.join(duplicate_methods)}。"
        "应继承 ContractActionMixin 并删除重复方法"
    )


# ---------------------------------------------------------------------------
# 检测 1.9: SupplementaryAgreementPartyInline.verbose_name 不应硬编码中文
# ---------------------------------------------------------------------------
def test_1_9_supplementary_agreement_party_inline_i18n() -> None:
    """
    期望行为：SupplementaryAgreementPartyInline 的 verbose_name
    应使用 _("当事人") 而非硬编码中文。
    未修复时 FAIL，修复后 PASS。

    **Validates: Requirements 1.9**
    """
    admin_file: Path = (
        BACKEND_DIR / "apps" / "contracts" / "admin"
        / "supplementary_agreement_admin.py"
    )
    source: str = admin_file.read_text(encoding="utf-8")
    tree: ast.Module = ast.parse(source)

    issues: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if node.name != "SupplementaryAgreementPartyInline":
            continue
        for item in node.body:
            if not isinstance(item, ast.Assign):
                continue
            for target in item.targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id not in ("verbose_name", "verbose_name_plural"):
                    continue
                # 如果值是字符串常量（非函数调用），则为硬编码
                if isinstance(item.value, ast.Constant) and isinstance(
                    item.value.value, str
                ):
                    issues.append(
                        f'{target.id} = "{item.value.value}" 未被 _() 包裹'
                    )

    assert not issues, (
        f"BUG 1.9: SupplementaryAgreementPartyInline 中 "
        f"{'; '.join(issues)}，缺少 i18n 支持"
    )


# ---------------------------------------------------------------------------
# 检测 1.10: domain/validators.py 不应抛出 ValueError，应使用 ValidationException
# ---------------------------------------------------------------------------
def test_1_10_domain_validators_no_value_error() -> None:
    """
    期望行为：domain/validators.py 应使用 ValidationException 替代 ValueError。
    未修复时 FAIL，修复后 PASS。

    **Validates: Requirements 1.10**
    """
    validators_file: Path = (
        BACKEND_DIR / "apps" / "contracts" / "domain" / "validators.py"
    )
    source: str = validators_file.read_text(encoding="utf-8")
    tree: ast.Module = ast.parse(source)

    value_error_raises: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise):
            continue
        if node.exc is None:
            continue
        # raise ValueError(...)
        if isinstance(node.exc, ast.Call):
            func: ast.expr = node.exc.func
            if isinstance(func, ast.Name) and func.id == "ValueError":
                value_error_raises.append(node.lineno)

    assert not value_error_raises, (
        f"BUG 1.10: domain/validators.py 在第 {value_error_raises} 行 "
        f"抛出 ValueError 而非 ValidationException"
    )
