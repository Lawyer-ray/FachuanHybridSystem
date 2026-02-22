"""
Bug Condition Exploration Tests - Contracts 严格审计违规检测

这些测试编码的是"期望行为"（修复后的正确状态）。
在未修复代码上运行时，测试会 FAIL，证明 bug 存在。
修复完成后，测试会 PASS，确认 bug 已修复。

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.10, 1.11, 1.12**
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest

# backend/ 根目录
BACKEND_DIR: Final[Path] = Path(__file__).resolve().parent.parent.parent.parent

# ---------------------------------------------------------------------------
# 待扫描文件路径定义
# ---------------------------------------------------------------------------

# Category 1: Service/API 层 — 需要 i18n 包裹的文件
I18N_FILES: Final[list[Path]] = [
    BACKEND_DIR / "apps" / "contracts" / "services" / "contract_payment_service.py",
    BACKEND_DIR / "apps" / "contracts" / "services" / "payment" / "contract_payment_service.py",
    BACKEND_DIR / "apps" / "contracts" / "services" / "supplementary_agreement_service.py",
    BACKEND_DIR / "apps" / "contracts" / "services" / "supplementary" / "supplementary_agreement_service.py",
    BACKEND_DIR / "apps" / "contracts" / "services" / "contract_service" / "_finance.py",
    BACKEND_DIR / "apps" / "contracts" / "services" / "contract_service" / "_crud.py",
    BACKEND_DIR / "apps" / "contracts" / "services" / "payment" / "contract_finance_mutation_service.py",
    BACKEND_DIR / "apps" / "contracts" / "services" / "contract" / "contract_validator.py",
    BACKEND_DIR / "apps" / "contracts" / "services" / "contract" / "contract_workflow_service.py",
    BACKEND_DIR / "apps" / "contracts" / "api" / "folder_binding_api.py",
]

# Category 2 & 4: Admin mixin 文件
ADMIN_MIXIN_FILES: Final[list[Path]] = [
    BACKEND_DIR / "apps" / "contracts" / "admin" / "mixins" / "action_mixin.py",
    BACKEND_DIR / "apps" / "contracts" / "admin" / "mixins" / "save_mixin.py",
    BACKEND_DIR / "apps" / "contracts" / "admin" / "mixins" / "display_mixin.py",
]

# Category 3: Admin 直接实例化 Service 的文件
CONTRACT_ADMIN_FILE: Final[Path] = (
    BACKEND_DIR / "apps" / "contracts" / "admin" / "contract_admin.py"
)

# Category 5: 引用已删除属性的文件
DISPLAY_MIXIN_FILE: Final[Path] = (
    BACKEND_DIR / "apps" / "contracts" / "admin" / "mixins" / "display_mixin.py"
)

# ---------------------------------------------------------------------------
# 正则模式
# ---------------------------------------------------------------------------

# 匹配 raise XxxException("...中文...") 或 raise XxxError("...中文...")
# 但排除已用 _("...") 包裹的情况
_RE_BARE_CHINESE: Final[re.Pattern[str]] = re.compile(
    r'raise\s+\w+(?:Exception|Error|Denied)\(\s*"[^"]*[\u4e00-\u9fff]'
)
# 已用 _() 包裹的合法模式
_RE_WRAPPED_CHINESE: Final[re.Pattern[str]] = re.compile(
    r'raise\s+\w+(?:Exception|Error|Denied)\(\s*_\(\s*"'
)

# 匹配 except Exception
_RE_BARE_EXCEPTION: Final[re.Pattern[str]] = re.compile(
    r'except\s+Exception\b'
)

# 匹配直接实例化 = ContractAssignmentQueryService()
_RE_DIRECT_INSTANTIATION: Final[re.Pattern[str]] = re.compile(
    r'=\s*ContractAssignmentQueryService\(\)'
)

# 匹配 @staticmethod
_RE_STATICMETHOD: Final[re.Pattern[str]] = re.compile(
    r'@staticmethod'
)

# 匹配 .primary_lawyer 属性访问（排除注释行）
_RE_PRIMARY_LAWYER: Final[re.Pattern[str]] = re.compile(
    r'\.primary_lawyer\b'
)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _scan_violations(
    files: list[Path],
    pattern: re.Pattern[str],
    *,
    exclude_pattern: re.Pattern[str] | None = None,
) -> list[str]:
    """扫描文件列表，返回匹配违规模式的行描述列表。"""
    violations: list[str] = []
    for filepath in files:
        if not filepath.exists():
            continue
        lines: list[str] = filepath.read_text(encoding="utf-8").splitlines()
        rel: str = str(filepath.relative_to(BACKEND_DIR))
        for lineno, line in enumerate(lines, start=1):
            stripped: str = line.lstrip()
            # 跳过注释行
            if stripped.startswith("#"):
                continue
            if pattern.search(line):
                # 如果有排除模式且匹配，则跳过
                if exclude_pattern and exclude_pattern.search(line):
                    continue
                violations.append(f"{rel}:{lineno}: {stripped.strip()}")
    return violations


# ---------------------------------------------------------------------------
# Test 1: i18n — 裸中文字符串检测
# ---------------------------------------------------------------------------
def test_no_bare_chinese_strings_in_exceptions() -> None:
    """
    Service/API 层的异常消息必须用 _() 包裹，不允许裸中文字符串。
    未修复时 FAIL（发现 ~30 处裸中文字符串），修复后 PASS。

    **Validates: Requirements 1.1, 1.2**
    """
    violations: list[str] = _scan_violations(
        I18N_FILES,
        _RE_BARE_CHINESE,
        exclude_pattern=_RE_WRAPPED_CHINESE,
    )
    assert not violations, (
        f"发现 {len(violations)} 处未用 _() 包裹的裸中文异常消息:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# Test 2: bare Exception 捕获检测
# ---------------------------------------------------------------------------
def test_no_bare_exception_in_admin_mixins() -> None:
    """
    Admin mixin 文件不允许使用 except Exception，应捕获特定异常类型。
    未修复时 FAIL（发现 ~15 处 bare Exception），修复后 PASS。

    **Validates: Requirements 1.3, 1.4, 1.5**
    """
    violations: list[str] = _scan_violations(
        ADMIN_MIXIN_FILES,
        _RE_BARE_EXCEPTION,
    )
    assert not violations, (
        f"发现 {len(violations)} 处 bare Exception 捕获:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# Test 3: 直接实例化 Service 检测
# ---------------------------------------------------------------------------
def test_no_direct_service_instantiation_in_admin() -> None:
    """
    contract_admin.py 不允许直接实例化 ContractAssignmentQueryService()，
    应通过工厂函数获取。
    未修复时 FAIL（发现 2 处直接实例化），修复后 PASS。

    **Validates: Requirements 1.6**
    """
    violations: list[str] = _scan_violations(
        [CONTRACT_ADMIN_FILE],
        _RE_DIRECT_INSTANTIATION,
    )
    assert not violations, (
        f"发现 {len(violations)} 处直接实例化 ContractAssignmentQueryService:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# Test 4: @staticmethod 检测
# ---------------------------------------------------------------------------
def test_no_staticmethod_in_admin_mixins() -> None:
    """
    Admin mixin 文件不允许使用 @staticmethod 装饰器。
    未修复时 FAIL（发现 1 处 @staticmethod），修复后 PASS。

    **Validates: Requirements 1.12**
    """
    violations: list[str] = _scan_violations(
        ADMIN_MIXIN_FILES,
        _RE_STATICMETHOD,
    )
    assert not violations, (
        f"发现 {len(violations)} 处 @staticmethod:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# Test 5: 已删除属性 .primary_lawyer 引用检测
# ---------------------------------------------------------------------------
def test_no_deleted_primary_lawyer_reference() -> None:
    """
    display_mixin.py 不允许直接访问 .primary_lawyer 属性（已删除）。
    应通过 ContractAssignmentQueryService 查询。
    未修复时 FAIL（发现 3 处引用），修复后 PASS。

    **Validates: Requirements 1.10, 1.11**
    """
    violations: list[str] = _scan_violations(
        [DISPLAY_MIXIN_FILE],
        _RE_PRIMARY_LAWYER,
    )
    assert not violations, (
        f"发现 {len(violations)} 处已删除属性 .primary_lawyer 引用:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )
