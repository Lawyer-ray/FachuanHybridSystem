"""
属性测试：导入路径向后兼容

# Feature: cases-quality-uplift, Property 2: 导入路径向后兼容

遍历 models/__init__.py 的 __all__ 中所有符号，
验证 from apps.cases.models import <symbol> 与从子模块导入返回相同对象。
"""

from __future__ import annotations

import importlib
import types
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# 导入 models 包，获取 __all__
import apps.cases.models as models_pkg

ALL_SYMBOLS: list[str] = list(models_pkg.__all__)

# 子模块名称列表（models/ 下的 .py 文件，排除 __init__）
_SUBMODULE_NAMES: list[str] = [
    "apps.cases.models.case",
    "apps.cases.models.chat",
    "apps.cases.models.log",
    "apps.cases.models.material",
    "apps.cases.models.party",
    "apps.cases.models.template_binding",
]

# 从 core.enums 重导出的符号（这些不在 models/ 子模块中）
_CORE_ENUM_SYMBOLS: set[str] = {
    "CaseStage",
    "CaseStatus",
    "CaseType",
    "LegalStatus",
    "SimpleCaseType",
}


def _find_symbol_in_submodules(name: str) -> Any:
    """在子模块中查找符号，返回找到的对象。"""
    if name in _CORE_ENUM_SYMBOLS:
        mod: types.ModuleType = importlib.import_module("apps.core.enums")
        return getattr(mod, name)

    for submod_name in _SUBMODULE_NAMES:
        mod = importlib.import_module(submod_name)
        if hasattr(mod, name):
            return getattr(mod, name)

    raise AttributeError(f"符号 {name!r} 在所有子模块中均未找到")


# ---------------------------------------------------------------------------
# Property 2: 导入路径向后兼容（Hypothesis 属性测试）
# Feature: cases-quality-uplift, Property 2: 导入路径向后兼容
# ---------------------------------------------------------------------------


@given(symbol_name=st.sampled_from(ALL_SYMBOLS))
@settings(max_examples=max(100, len(ALL_SYMBOLS) * 5))
def test_property_import_compat(symbol_name: str) -> None:
    """
    **Validates: Requirements 1.4**

    对于 models/__init__.py 的 __all__ 中任意符号，
    通过 apps.cases.models 导入的对象应与从对应子模块导入的对象是同一个。
    """
    # 从包级别导入
    pkg_obj: Any = getattr(models_pkg, symbol_name)

    # 从子模块导入
    submod_obj: Any = _find_symbol_in_submodules(symbol_name)

    assert pkg_obj is submod_obj, (
        f"符号 {symbol_name!r} 不一致:\n"
        f"  apps.cases.models.{symbol_name} -> {pkg_obj!r} (id={id(pkg_obj)})\n"
        f"  子模块导入 -> {submod_obj!r} (id={id(submod_obj)})"
    )


# ---------------------------------------------------------------------------
# 参数化测试：确保 __all__ 中每个符号都能从包级别导入
# Feature: cases-quality-uplift, Property 2: 导入路径向后兼容
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("symbol_name", ALL_SYMBOLS, ids=lambda s: s)
def test_all_symbols_importable_from_package(symbol_name: str) -> None:
    """
    **Validates: Requirements 1.4**

    验证 __all__ 中每个符号都能从 apps.cases.models 成功导入。
    """
    assert hasattr(models_pkg, symbol_name), (
        f"apps.cases.models 缺少 __all__ 中声明的符号: {symbol_name!r}"
    )
