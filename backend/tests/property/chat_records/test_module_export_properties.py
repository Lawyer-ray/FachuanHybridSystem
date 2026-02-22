"""
Property Tests: 模块导出完整性

# Feature: chat-records-quality-uplift

- Property 3: models/__init__.py 不导出下划线符号 (Validates: Requirements 3.1, 3.3)
- Property 5: services/__init__.py 导出完整性 (Validates: Requirements 12.1, 12.2)

确定性测试，无需 hypothesis。
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from types import ModuleType

from apps.chat_records import models


# ---------------------------------------------------------------------------
# Property 3: models/__init__.py 不导出下划线符号
# ---------------------------------------------------------------------------


def test_models_all_has_no_underscore_symbols() -> None:
    """
    # Feature: chat-records-quality-uplift, Property 3: models/__init__.py 不导出下划线符号

    __all__ 列表中的每个符号名都不应以下划线开头。
    **Validates: Requirements 3.1, 3.3**
    """
    all_symbols: list[str] = getattr(models, "__all__", [])
    underscore_symbols = [s for s in all_symbols if s.startswith("_")]
    assert underscore_symbols == [], (
        f"models/__init__.py __all__ 中包含下划线开头的符号: {underscore_symbols}"
    )


# ---------------------------------------------------------------------------
# Feature: chat-records-quality-uplift, Property 5: services/__init__.py 导出完整性
# ---------------------------------------------------------------------------


def _collect_public_classes_from_services() -> dict[str, list[str]]:
    """扫描 services/ 目录，返回 {module_name: [公开类名, ...]} 映射。"""
    services_dir = (
        Path(__file__).resolve().parents[3]
        / "apps"
        / "chat_records"
        / "services"
    )
    result: dict[str, list[str]] = {}
    for py_file in sorted(services_dir.glob("*.py")):
        if py_file.name.startswith("_") or py_file.name == "__init__.py":
            continue
        module_name = py_file.stem
        fq_module = f"apps.chat_records.services.{module_name}"
        mod: ModuleType = importlib.import_module(fq_module)
        public_classes: list[str] = [
            name
            for name, obj in inspect.getmembers(mod, inspect.isclass)
            if not name.startswith("_") and obj.__module__ == fq_module
        ]
        if public_classes:
            result[module_name] = public_classes
    return result


def test_services_all_exports_every_public_class() -> None:
    """
    # Feature: chat-records-quality-uplift, Property 5: services/__init__.py 导出完整性

    services/__init__.py 的 __all__ 应包含所有子模块中定义的公开类。
    **Validates: Requirements 12.1, 12.2**
    """
    from apps.chat_records import services

    all_symbols: list[str] = getattr(services, "__all__", [])
    all_set: set[str] = set(all_symbols)

    missing: list[str] = []
    for module_name, classes in _collect_public_classes_from_services().items():
        for cls_name in classes:
            if cls_name not in all_set:
                missing.append(f"{module_name}.{cls_name}")

    assert missing == [], (
        f"services/__init__.py __all__ 缺少以下公开类: {missing}"
    )
