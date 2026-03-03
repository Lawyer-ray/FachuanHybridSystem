"""
Bug Condition Exploration Tests - Organization 模块代码质量违规检测

这些测试编码的是"期望行为"（修复后的正确状态）。
在未修复代码上运行时，测试会 FAIL，证明 bug 存在。
修复完成后，测试会 PASS，确认 bug 已修复。

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8**
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Sequence

from hypothesis import given, settings
from hypothesis import strategies as st

# backend/ 根目录
BACKEND_DIR: Path = Path(__file__).resolve().parent.parent.parent.parent

# organization 模块目录
ORG_DIR: Path = BACKEND_DIR / "apps" / "organization"

# ---------- 常量 ----------

# Test 7: 需要检查 logger f-string 的服务文件
LOGGER_FSTRING_FILES: list[str] = [
    "services/lawfirm_service.py",
    "services/team_service.py",
    "services/lawyer/mutation.py",
]

# Test 8: 需要检查 errors dict i18n 的服务文件
ERRORS_I18N_FILES: list[str] = [
    "services/lawfirm_service.py",
    "services/team_service.py",
    "services/lawyer/mutation.py",
]


# ---------- 辅助函数 ----------


def _read_source(rel_path: str) -> str:
    """读取 organization 模块下的源文件内容。"""
    return (ORG_DIR / rel_path).read_text(encoding="utf-8")


def _find_logger_fstring_calls(source: str) -> list[str]:
    """
    在源码中查找使用 f-string 的 logger 调用。

    匹配模式: logger.warning(f"..."), logger.error(f"..."), logger.info(f"...") 等
    """
    hits: list[str] = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # 匹配 logger.xxx(...) 调用
        if not (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)):
            continue
        if func.value.id != "logger":
            continue
        # 检查第一个参数是否为 JoinedStr (f-string)
        if node.args and isinstance(node.args[0], ast.JoinedStr):
            line_no = node.lineno
            hits.append(f'L{line_no}: logger.{func.attr}(f"...")')
    return hits


def _find_errors_dict_without_i18n(source: str) -> list[str]:
    """
    查找 errors={...} 字典中值为硬编码字符串（未用 _() 包装）的情况。

    检测模式: errors={"key": "硬编码字符串"} 或 errors={"key": f"..."}
    期望模式: errors={"key": str(_("字符串"))}
    """
    hits: list[str] = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.keyword):
            continue
        if node.arg != "errors":
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        for val in node.value.values:
            # 硬编码字符串 → 违规
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                hits.append(f'L{val.lineno}: "{val.value}"')
            # f-string → 也是违规（未用 _() 包装）
            elif isinstance(val, ast.JoinedStr):
                hits.append(f'L{val.lineno}: f"..."')
    return hits


def _find_permission_denied_without_i18n(source: str) -> list[str]:
    """
    查找 PermissionDenied(...) 调用中参数为硬编码字符串（未用 _() 包装）的情况。
    """
    hits: list[str] = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # 匹配 PermissionDenied(...) 或 raise PermissionDenied(...)
        func = node.func
        if isinstance(func, ast.Name) and func.id == "PermissionDenied":
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    hits.append(f'L{arg.lineno}: "{arg.value}"')
    return hits


# ---------------------------------------------------------------------------
# Test 1: models.py 遗留文件不应存在
# ---------------------------------------------------------------------------
def test_legacy_models_py_not_exists() -> None:
    """
    期望行为：organization/models.py 遗留文件不应存在，
    仅保留 models/ 目录作为唯一模型定义来源。
    未修复时 FAIL（文件存在），修复后 PASS。

    **Validates: Requirements 1.1**
    """
    legacy_file = ORG_DIR / "models.py"
    models_dir = ORG_DIR / "models"

    assert not legacy_file.exists(), (
        f"BUG 1.1: 遗留 models.py 与 models/ 目录共存。\n"
        f"  models.py 存在: {legacy_file.exists()}\n"
        f"  models/ 目录存在: {models_dir.exists()}\n"
        f"  应删除 models.py，仅保留 models/ 目录"
    )


# ---------------------------------------------------------------------------
# Test 2: lawyer_service.py 旧版服务不应存在
# ---------------------------------------------------------------------------
def test_legacy_lawyer_service_not_exists() -> None:
    """
    期望行为：services/lawyer_service.py 旧版单体服务不应存在，
    仅保留 services/lawyer/ 拆分版本。
    未修复时 FAIL（文件存在），修复后 PASS。

    **Validates: Requirements 1.2**
    """
    legacy_file = ORG_DIR / "services" / "lawyer_service.py"
    new_dir = ORG_DIR / "services" / "lawyer"

    assert not legacy_file.exists(), (
        f"BUG 1.2: 旧版 lawyer_service.py 与 services/lawyer/ 目录共存。\n"
        f"  lawyer_service.py 存在: {legacy_file.exists()}\n"
        f"  services/lawyer/ 目录存在: {new_dir.exists()}\n"
        f"  应删除 lawyer_service.py，仅保留 services/lawyer/ 目录"
    )


# ---------------------------------------------------------------------------
# Test 3: Admin 层不应直接调用 queryset.update()
# ---------------------------------------------------------------------------
def test_admin_no_queryset_update() -> None:
    """
    期望行为：accountcredential_admin.py 的 mark_as_preferred / unmark_as_preferred
    不应直接调用 queryset.update()，应委托给 Service 层。
    未修复时 FAIL（包含 queryset.update()），修复后 PASS。

    **Validates: Requirements 1.3**
    """
    source = _read_source("admin/accountcredential_admin.py")
    tree = ast.parse(source)

    methods_with_update: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name not in ("mark_as_preferred", "unmark_as_preferred"):
            continue
        method_src = ast.get_source_segment(source, node)
        if method_src and "queryset.update(" in method_src:
            methods_with_update.append(node.name)

    assert not methods_with_update, (
        f"BUG 1.3: Admin 层直接调用 queryset.update()，违反四层架构。\n"
        f"  违规方法: {methods_with_update}\n"
        f"  应委托给 AccountCredentialService 的批量更新方法"
    )


# ---------------------------------------------------------------------------
# Test 4: PermissionDenied 消息必须使用 gettext_lazy/_() 包装
# ---------------------------------------------------------------------------
def test_access_policy_i18n() -> None:
    """
    期望行为：organization_access_policy.py 中所有 PermissionDenied(...)
    的错误消息应使用 _() 或 gettext_lazy() 包装。
    未修复时 FAIL（硬编码中文字符串），修复后 PASS。

    **Validates: Requirements 1.4**
    """
    source = _read_source("services/organization_access_policy.py")
    hardcoded = _find_permission_denied_without_i18n(source)

    assert not hardcoded, (
        "BUG 1.4: organization_access_policy.py 中 PermissionDenied 使用硬编码字符串，"
        "未用 _() 包装，不支持 i18n。\n"
        "  违规位置:\n    " + "\n    ".join(hardcoded)
    )


@given(dummy=st.integers(min_value=0, max_value=0))
@settings(max_examples=1)
def test_property_access_policy_all_permission_denied_i18n(dummy: int) -> None:
    """
    属性测试：organization_access_policy.py 中所有 PermissionDenied 调用
    的参数均应使用 _() 包装。

    **Validates: Requirements 1.4**
    """
    source = _read_source("services/organization_access_policy.py")
    hardcoded = _find_permission_denied_without_i18n(source)
    assert not hardcoded, f"BUG 1.4: 发现 {len(hardcoded)} 处硬编码 PermissionDenied 消息:\n    " + "\n    ".join(
        hardcoded
    )


# ---------------------------------------------------------------------------
# Test 5: views.py 不应直接调用 Model.objects
# ---------------------------------------------------------------------------
def test_views_no_model_objects() -> None:
    """
    期望行为：views.py 不应直接调用 Lawyer.objects 或其他 Model.objects，
    应委托给 Service 层。
    未修复时 FAIL（包含 Lawyer.objects），修复后 PASS。

    **Validates: Requirements 1.5**
    """
    source = _read_source("views.py")

    # 匹配 Xxx.objects 模式（大写开头的类名 + .objects）
    pattern = re.compile(r"\b[A-Z]\w+\.objects\b")
    matches: list[str] = []
    for i, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("from ") or stripped.startswith("import "):
            continue
        found = pattern.findall(line)
        for m in found:
            matches.append(f"L{i}: {m}")

    assert not matches, (
        "BUG 1.5: views.py 直接调用 Model.objects，违反视图层架构规范。\n"
        "  违规位置:\n    " + "\n    ".join(matches) + "\n"
        "  应委托给 AuthService"
    )


# ---------------------------------------------------------------------------
# Test 6: account_credential_admin_service.py 不应直接使用 AccountCredential.objects
# ---------------------------------------------------------------------------
def test_admin_service_no_direct_model_objects() -> None:
    """
    期望行为：account_credential_admin_service.py 不应直接使用
    AccountCredential.objects，应通过 AccountCredentialService 访问数据。
    未修复时 FAIL（包含 AccountCredential.objects），修复后 PASS。

    **Validates: Requirements 1.6**
    """
    source = _read_source("services/account_credential_admin_service.py")

    matches: list[str] = []
    for i, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("from ") or stripped.startswith("import "):
            continue
        if "AccountCredential.objects" in line:
            matches.append(f"L{i}: {stripped}")

    assert not matches, (
        "BUG 1.6: account_credential_admin_service.py 直接使用 AccountCredential.objects。\n"
        "  违规位置:\n    " + "\n    ".join(matches) + "\n"
        "  应通过 AccountCredentialService 查询"
    )


# ---------------------------------------------------------------------------
# Test 7: Service 层 logger 不应使用 f-string
# ---------------------------------------------------------------------------
def test_service_logger_no_fstring() -> None:
    """
    期望行为：服务层的 logger 调用不应使用 f-string 插值，
    应使用惰性格式化（logger.warning("... %s ...", var)）。
    未修复时 FAIL（使用 f-string），修复后 PASS。

    **Validates: Requirements 1.7**
    """
    all_hits: dict[str, list[str]] = {}
    for rel_path in LOGGER_FSTRING_FILES:
        source = _read_source(rel_path)
        hits = _find_logger_fstring_calls(source)
        if hits:
            all_hits[rel_path] = hits

    assert not all_hits, "BUG 1.7: 服务层 logger 使用 f-string 插值，应使用惰性格式化。\n" + "\n".join(
        f"  {path}:\n    " + "\n    ".join(lines) for path, lines in all_hits.items()
    )


@given(file_index=st.integers(min_value=0, max_value=len(LOGGER_FSTRING_FILES) - 1))
@settings(max_examples=3)
def test_property_logger_no_fstring(file_index: int) -> None:
    """
    属性测试：对于任意选取的服务文件，logger 调用均不应使用 f-string。

    **Validates: Requirements 1.7**
    """
    rel_path = LOGGER_FSTRING_FILES[file_index]
    source = _read_source(rel_path)
    hits = _find_logger_fstring_calls(source)
    assert not hits, f"BUG 1.7: {rel_path} 中 logger 使用 f-string:\n    " + "\n    ".join(hits)


# ---------------------------------------------------------------------------
# Test 8: errors dict 值必须使用 _() 包装
# ---------------------------------------------------------------------------
def test_errors_dict_i18n() -> None:
    """
    期望行为：服务层 ValidationException 的 errors 字典中，
    所有用户可见字符串应使用 _() 包装，支持 i18n。
    未修复时 FAIL（硬编码字符串），修复后 PASS。

    **Validates: Requirements 1.8**
    """
    all_hits: dict[str, list[str]] = {}
    for rel_path in ERRORS_I18N_FILES:
        source = _read_source(rel_path)
        hits = _find_errors_dict_without_i18n(source)
        if hits:
            all_hits[rel_path] = hits

    assert not all_hits, "BUG 1.8: errors 字典中存在硬编码字符串，未用 _() 包装。\n" + "\n".join(
        f"  {path}:\n    " + "\n    ".join(lines) for path, lines in all_hits.items()
    )


@given(file_index=st.integers(min_value=0, max_value=len(ERRORS_I18N_FILES) - 1))
@settings(max_examples=3)
def test_property_errors_dict_i18n(file_index: int) -> None:
    """
    属性测试：对于任意选取的服务文件，errors 字典值均应使用 _() 包装。

    **Validates: Requirements 1.8**
    """
    rel_path = ERRORS_I18N_FILES[file_index]
    source = _read_source(rel_path)
    hits = _find_errors_dict_without_i18n(source)
    assert not hits, f"BUG 1.8: {rel_path} 中 errors 字典存在硬编码字符串:\n    " + "\n    ".join(hits)
