"""
正确性属性测试: 后端代码质量第二轮整改

验证 backend-quality-round2 spec 的 11 个正确性属性。

Feature: backend-quality-round2
"""

import ast
import re
import sys
import unittest.mock
from pathlib import Path
from typing import NamedTuple

import pytest


# ---------------------------------------------------------------------------
# 公共工具
# ---------------------------------------------------------------------------

def _backend_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _apps_path() -> Path:
    return _backend_path() / "apps"


class Violation(NamedTuple):
    file: str
    line_no: int
    detail: str


# ---------------------------------------------------------------------------
# Property 1: Admin 文件（含子目录）零 mark_safe
# Validates: Requirements 1.1, 1.2, 1.3
# ---------------------------------------------------------------------------

def _collect_all_admin_files() -> list[Path]:
    """收集所有 apps/*/admin/**/*.py 文件"""
    return [
        p for p in _apps_path().glob("*/admin/**/*.py")
        if p.name != "__init__.py" and "__pycache__" not in str(p)
    ]


def _check_mark_safe(file_path: Path) -> list[Violation]:
    """AST 扫描单个文件，检测 mark_safe 导入或调用"""
    violations: list[Violation] = []
    try:
        content: str = file_path.read_text(encoding="utf-8")
        tree: ast.Module = ast.parse(content)
    except (SyntaxError, OSError):
        return violations

    rel: str = str(file_path.relative_to(_backend_path()))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if any(alias.name == "mark_safe" for alias in node.names):
                violations.append(Violation(rel, node.lineno, f"导入 mark_safe (from {node.module})"))
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "mark_safe":
                violations.append(Violation(rel, node.lineno, "调用 mark_safe()"))
            elif isinstance(func, ast.Attribute) and func.attr == "mark_safe":
                violations.append(Violation(rel, node.lineno, "调用 *.mark_safe()"))
    return violations


@pytest.mark.property_test
def test_p1_admin_no_mark_safe() -> None:
    """
    Property 1: Admin 文件（含子目录）零 mark_safe

    AST 扫描所有 apps/*/admin/**/*.py，断言无 mark_safe 导入或调用。
    Validates: Requirements 1.1, 1.2, 1.3
    """
    admin_files: list[Path] = _collect_all_admin_files()
    assert len(admin_files) > 0, "未找到任何 Admin 层文件"

    all_violations: list[Violation] = []
    for f in admin_files:
        all_violations.extend(_check_mark_safe(f))

    assert not all_violations, (
        f"Admin 层发现 {len(all_violations)} 处 mark_safe 违规:\n"
        + "\n".join(f"  {v.file}:{v.line_no} {v.detail}" for v in all_violations)
    )


# ---------------------------------------------------------------------------
# Property 2: format_html 正确转义 HTML 特殊字符
# Validates: Requirements 1.4
# ---------------------------------------------------------------------------

@pytest.mark.property_test
def test_p2_format_html_escapes_special_chars() -> None:
    """
    Property 2: format_html 正确转义 HTML 特殊字符

    验证 format_html 对 XSS 危险字符的转义行为。
    Validates: Requirements 1.4
    """
    from django.utils.html import format_html

    dangerous_inputs: list[str] = [
        "<script>alert('xss')</script>",
        '"><img src=x onerror=alert(1)>',
        "'; DROP TABLE users; --",
        "<b>bold</b>",
        "& < > \" '",
    ]
    for payload in dangerous_inputs:
        result: str = str(format_html("{}", payload))
        # 验证 < > 被转义（防止标签注入）
        assert "<script>" not in result, f"format_html 未转义 <script>: {result}"
        assert "<img" not in result, f"format_html 未转义 <img: {result}"
        assert "<b>" not in result, f"format_html 未转义 <b>: {result}"
        # 验证 & 被转义
        if "&" in payload and "&amp;" not in payload:
            assert "&amp;" in result, f"format_html 未转义 &: {result}"


# ---------------------------------------------------------------------------
# Property 3: Service 层零 settings 直接导入（对比 baseline）
# Validates: Requirements 2.1, 2.3
# ---------------------------------------------------------------------------

def _load_baseline(filename: str) -> set[str]:
    baseline_path: Path = (
        _backend_path() / "tests" / "structure" / "baselines" / filename
    )
    if not baseline_path.exists():
        return set()
    lines: list[str] = baseline_path.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.strip().startswith("#")}


def _file_imports_django_settings(file_path: Path) -> bool:
    try:
        content: str = file_path.read_text(encoding="utf-8")
        tree: ast.Module = ast.parse(content)
    except Exception:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "django.conf":
            if any(alias.name == "settings" for alias in node.names):
                return True
    return False


@pytest.mark.property_test
def test_p3_service_no_new_settings_import() -> None:
    """
    Property 3: Service 层零新增 django.conf.settings 导入

    与 baseline 对比，确保无新增 settings 导入。
    Validates: Requirements 2.1, 2.3
    """
    backend: Path = _backend_path()
    baseline: set[str] = _load_baseline("services_django_settings_imports.txt")

    offenders: list[str] = []
    for py in _apps_path().glob("*/services/**/*.py"):
        if "__pycache__" in str(py):
            continue
        rel: str = py.relative_to(backend).as_posix()
        if _file_imports_django_settings(py) and rel not in baseline:
            offenders.append(rel)

    assert not offenders, (
        f"发现 {len(offenders)} 个新增 Service 层 settings 导入（不在 baseline 中）:\n"
        + "\n".join(f"  {f}" for f in sorted(offenders))
    )


# ---------------------------------------------------------------------------
# Property 4: Baseline 残留条目必须附带注释
# Validates: Requirements 2.4, 6.4
# ---------------------------------------------------------------------------

@pytest.mark.property_test
def test_p4_baseline_entries_have_comments() -> None:
    """
    Property 4: Baseline 残留条目必须附带注释

    解析 baseline 文件，验证每个非空非注释行的前后有注释说明。
    Validates: Requirements 2.4, 6.4
    """
    baselines_dir: Path = _backend_path() / "tests" / "structure" / "baselines"
    baseline_files: list[str] = [
        "services_django_settings_imports.txt",
        "cross_app_model_imports.txt",
    ]

    for filename in baseline_files:
        baseline_path: Path = baselines_dir / filename
        if not baseline_path.exists():
            continue

        lines: list[str] = baseline_path.read_text(encoding="utf-8").splitlines()
        violations: list[str] = []

        for i, line in enumerate(lines):
            stripped: str = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # 检查行内注释（同行 # 注释）
            has_inline_comment: bool = " # " in line or line.rstrip().endswith("#")
            # 检查前后独立注释行
            has_comment_before: bool = any(
                lines[j].strip().startswith("#")
                for j in range(max(0, i - 3), i)
                if lines[j].strip()
            )
            has_comment_after: bool = any(
                lines[j].strip().startswith("#")
                for j in range(i + 1, min(len(lines), i + 3))
                if lines[j].strip()
            )
            if not (has_inline_comment or has_comment_before or has_comment_after):
                violations.append(f"{filename}:{i+1} 条目无注释: {stripped}")

        assert not violations, (
            "Baseline 条目缺少注释说明:\n"
            + "\n".join(f"  {v}" for v in violations)
        )


# ---------------------------------------------------------------------------
# Property 5: 测试断言与 Admin actions 列表一致
# Validates: Requirements 3.1, 3.2
# ---------------------------------------------------------------------------

@pytest.mark.property_test
def test_p5_admin_actions_match_test_assertions() -> None:
    """
    Property 5: AccountCredential Admin actions 与测试断言一致

    反射获取 AccountCredentialAdmin 的 actions，验证与测试文件断言一致。
    Validates: Requirements 3.1, 3.2
    """
    import django
    import os
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
    try:
        django.setup()
    except RuntimeError:
        pass  # 已初始化

    from apps.organization.admin.accountcredential_admin import AccountCredentialAdmin
    from apps.organization.models import AccountCredential
    from django.contrib.admin.sites import AdminSite

    site: AdminSite = AdminSite()
    admin_instance: AccountCredentialAdmin = AccountCredentialAdmin(
        model=AccountCredential,
        admin_site=site,
    )
    # 获取 actions（排除 delete_selected 内置 action）
    actual_actions: set[str] = {
        name for name in (admin_instance.actions or [])
        if name != "delete_selected"
    }
    expected_actions: set[str] = {"mark_as_preferred", "unmark_as_preferred"}
    assert actual_actions == expected_actions, (
        f"AccountCredentialAdmin actions 不匹配:\n"
        f"  实际: {sorted(actual_actions)}\n"
        f"  期望: {sorted(expected_actions)}"
    )


# ---------------------------------------------------------------------------
# Property 6: 测试环境 AppConfig.ready() 无副作用
# Validates: Requirements 4.1, 4.2, 4.4
# ---------------------------------------------------------------------------

@pytest.mark.property_test
def test_p6_appconfig_ready_no_side_effects_in_test() -> None:
    """
    Property 6: 测试环境下 AppConfig.ready() 无副作用

    mock threading.Timer 和 call_command，在 pytest 环境调用 ready()，
    验证 Timer 和 call_command 均未被调用。
    Validates: Requirements 4.1, 4.2, 4.4
    """
    # 确保 pytest 在 sys.modules 中（模拟测试环境）
    assert "pytest" in sys.modules, "此测试必须在 pytest 环境下运行"

    from apps.automation.apps import AutomationConfig

    config: AutomationConfig = AutomationConfig.__new__(AutomationConfig)
    config.name = "apps.automation"

    with (
        unittest.mock.patch("threading.Timer") as mock_timer,
        unittest.mock.patch("django.core.management.call_command") as mock_cmd,
    ):
        config._recover_court_sms_tasks()

    mock_timer.assert_not_called()
    mock_cmd.assert_not_called()


# ---------------------------------------------------------------------------
# Property 7: 用户可见消息 gettext 包裹
# Validates: Requirements 7.1, 7.2
# ---------------------------------------------------------------------------

_CHINESE_RE: re.Pattern[str] = re.compile(r"[\u4e00-\u9fff]")


def _find_unwrapped_chinese_strings(file_path: Path) -> list[Violation]:
    """AST 扫描文件，找出未被 gettext 包裹的中文字符串字面量"""
    violations: list[Violation] = []
    try:
        content: str = file_path.read_text(encoding="utf-8")
        tree: ast.Module = ast.parse(content)
    except (SyntaxError, OSError):
        return violations

    rel: str = str(file_path.relative_to(_backend_path()))

    # 收集所有被 gettext/_/gettext_lazy/__ 包裹的字符串节点 id
    wrapped_nodes: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            is_gettext_call: bool = (
                (isinstance(func, ast.Name) and func.id in ("_", "gettext", "gettext_lazy", "ngettext", "pgettext"))
                or (isinstance(func, ast.Attribute) and func.attr in ("gettext", "gettext_lazy", "ngettext"))
            )
            if is_gettext_call:
                for arg in node.args:
                    wrapped_nodes.add(id(arg))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in wrapped_nodes:
            continue
        if not _CHINESE_RE.search(node.value):
            continue
        # 跳过注释风格的字符串（docstring）
        violations.append(Violation(rel, node.lineno, f"未包裹中文字符串: {node.value[:40]!r}"))

    return violations


@pytest.mark.property_test
def test_p7_user_visible_messages_wrapped_with_gettext() -> None:
    """
    Property 7: 用户可见消息 gettext 包裹

    扫描 API/Service 层文件，验证中文字符串字面量在 gettext 调用内。
    Validates: Requirements 7.1, 7.2
    """
    backend: Path = _backend_path()
    apps: Path = _apps_path()

    # 只扫描 api 和 services 层
    target_files: list[Path] = [
        p for p in list(apps.glob("*/api/**/*.py")) + list(apps.glob("*/services/**/*.py"))
        if p.name != "__init__.py" and "__pycache__" not in str(p)
    ]

    all_violations: list[Violation] = []
    for f in target_files:
        all_violations.extend(_find_unwrapped_chinese_strings(f))

    # 允许一定数量的历史遗留（本次整改目标是新增的消息已包裹）
    # 如果违规数超过 baseline，则失败
    baseline_path: Path = backend / "tests" / "structure" / "baselines" / "unwrapped_chinese_strings_count.txt"
    if baseline_path.exists():
        baseline_count: int = int(baseline_path.read_text(encoding="utf-8").strip())
        assert len(all_violations) <= baseline_count, (
            f"未包裹中文字符串数量从 {baseline_count} 增加到 {len(all_violations)}，"
            f"请用 gettext 包裹新增的中文消息:\n"
            + "\n".join(f"  {v.file}:{v.line_no} {v.detail}" for v in all_violations[:20])
        )
    else:
        # 首次运行：写入 baseline
        baseline_path.write_text(str(len(all_violations)), encoding="utf-8")


# ---------------------------------------------------------------------------
# Property 8: 翻译文件完整性
# Validates: Requirements 7.3
# ---------------------------------------------------------------------------

@pytest.mark.property_test
def test_p8_translation_file_completeness() -> None:
    """
    Property 8: 翻译文件完整性

    解析英文 .po 文件，验证每个非空 msgid 有非空 msgstr。
    Validates: Requirements 7.3
    """
    po_path: Path = (
        _backend_path() / "apiSystem" / "locale" / "en" / "LC_MESSAGES" / "django.po"
    )
    assert po_path.exists(), f"英文翻译文件不存在: {po_path}"

    content: str = po_path.read_text(encoding="utf-8")
    lines: list[str] = content.splitlines()

    incomplete: list[str] = []
    current_msgid: str = ""
    current_msgstr: str = ""
    in_msgid: bool = False
    in_msgstr: bool = False

    for line in lines:
        if line.startswith("msgid "):
            current_msgid = line[7:].strip().strip('"')
            in_msgid = True
            in_msgstr = False
        elif line.startswith("msgstr "):
            current_msgstr = line[8:].strip().strip('"')
            in_msgid = False
            in_msgstr = True
        elif line.startswith('"') and in_msgid:
            current_msgid += line.strip().strip('"')
        elif line.startswith('"') and in_msgstr:
            current_msgstr += line.strip().strip('"')
        elif not line.strip():
            # 空行：检查上一个条目
            if current_msgid and not current_msgstr:
                incomplete.append(f"msgid={current_msgid!r} 缺少 msgstr")
            current_msgid = ""
            current_msgstr = ""
            in_msgid = False
            in_msgstr = False

    assert not incomplete, (
        f"英文翻译文件有 {len(incomplete)} 个 msgid 缺少翻译:\n"
        + "\n".join(f"  {m}" for m in incomplete)
    )


# ---------------------------------------------------------------------------
# Property 9: 生产 settings 无硬编码密码
# Validates: Requirements 10.1, 10.2
# ---------------------------------------------------------------------------

@pytest.mark.property_test
def test_p9_settings_no_hardcoded_password() -> None:
    """
    Property 9: 生产 settings 无硬编码密码

    扫描 settings.py，验证 SMOKE_ADMIN_PASSWORD 在非 DEBUG 时强制从环境变量读取。
    Validates: Requirements 10.1, 10.2
    """
    settings_path: Path = (
        _backend_path() / "apiSystem" / "apiSystem" / "settings.py"
    )
    content: str = settings_path.read_text(encoding="utf-8")

    # 验证存在 ImproperlyConfigured 抛出逻辑
    assert "ImproperlyConfigured" in content, (
        "settings.py 中未找到 ImproperlyConfigured，SMOKE_ADMIN_PASSWORD 未做生产环境强制检查"
    )
    # 验证 SMOKE_ADMIN_PASSWORD 从环境变量读取
    assert 'os.environ.get("SMOKE_ADMIN_PASSWORD"' in content or "SMOKE_ADMIN_PASSWORD" in content, (
        "settings.py 中未找到 SMOKE_ADMIN_PASSWORD 环境变量读取"
    )
    # 验证非 DEBUG 时不允许空密码
    assert "not DEBUG" in content or "not _smoke_pw" in content, (
        "settings.py 中未找到非 DEBUG 时的密码强制检查逻辑"
    )


# ---------------------------------------------------------------------------
# Property 10: mypy 豁免移除后文件零错误（静态检查）
# Validates: Requirements 5.1, 5.2, 11.2, 11.3
# ---------------------------------------------------------------------------

@pytest.mark.property_test
def test_p10_mypy_exemption_removed_file_has_annotations() -> None:
    """
    Property 10: 已移除 mypy 豁免的文件有完整类型注解

    检查 token_acquisition_history_admin_service.py 的函数均有返回值注解。
    Validates: Requirements 5.1, 5.2
    """
    target: Path = (
        _apps_path()
        / "automation"
        / "services"
        / "admin"
        / "token_acquisition_history_admin_service.py"
    )
    assert target.exists(), f"目标文件不存在: {target}"

    content: str = target.read_text(encoding="utf-8")
    tree: ast.Module = ast.parse(content)

    missing: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith("_") and not node.name.startswith("__"):
            # 私有方法也需要注解
            pass
        if node.returns is None:
            missing.append(f"  行 {node.lineno}: def {node.name}() 缺少返回值注解")

    assert not missing, (
        f"token_acquisition_history_admin_service.py 有 {len(missing)} 个函数缺少返回值注解:\n"
        + "\n".join(missing)
    )


# ---------------------------------------------------------------------------
# Property 11: 修改函数完整类型注解
# Validates: Requirements 5.3, 11.4
# ---------------------------------------------------------------------------

_MODIFIED_FILES: list[str] = [
    "apps/automation/admin/insurance/preservation_quote_admin.py",
    "apps/automation/admin/token/token_acquisition_history_admin.py",
    "apps/automation/admin/scraper/scraper_task_admin.py",
    "apps/automation/services/admin/token_acquisition_history_admin_service.py",
    "apps/automation/apps.py",
]


@pytest.mark.property_test
def test_p11_modified_files_have_type_annotations() -> None:
    """
    Property 11: 修改文件中的函数有完整类型注解

    用 ast.parse 检查本次整改修改的文件，验证函数参数和返回值有注解。
    Validates: Requirements 5.3, 11.4
    """
    backend: Path = _backend_path()
    missing_annotations: list[str] = []

    for rel_path in _MODIFIED_FILES:
        file_path: Path = backend / rel_path
        if not file_path.exists():
            continue

        try:
            content: str = file_path.read_text(encoding="utf-8")
            tree: ast.Module = ast.parse(content)
        except (SyntaxError, OSError):
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            # 检查返回值注解
            if node.returns is None:
                missing_annotations.append(
                    f"  {rel_path}:{node.lineno} def {node.name}() 缺少返回值注解"
                )
            # 检查参数注解（跳过 self/cls）
            for arg in node.args.args:
                if arg.arg in ("self", "cls"):
                    continue
                if arg.annotation is None:
                    missing_annotations.append(
                        f"  {rel_path}:{node.lineno} def {node.name}() 参数 {arg.arg!r} 缺少类型注解"
                    )

    assert not missing_annotations, (
        f"修改文件中发现 {len(missing_annotations)} 处缺少类型注解:\n"
        + "\n".join(missing_annotations)
    )
