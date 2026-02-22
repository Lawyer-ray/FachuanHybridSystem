"""
回归测试：CaseAdminSaveMixin 行为验证

需求: 1.7
"""

from __future__ import annotations

import django
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
django.setup()


def test_save_mixin_has_save_model() -> None:
    """验证 CaseAdminSaveMixin 有 save_model 方法。"""
    from apps.cases.admin.mixins import CaseAdminSaveMixin

    assert hasattr(CaseAdminSaveMixin, "save_model"), "CaseAdminSaveMixin 缺少 save_model 方法"
    assert callable(CaseAdminSaveMixin.save_model), "save_model 不可调用"


def test_save_mixin_has_delete_methods() -> None:
    """验证 CaseAdminSaveMixin 有 delete_model 和 delete_queryset 方法。"""
    from apps.cases.admin.mixins import CaseAdminSaveMixin

    assert hasattr(CaseAdminSaveMixin, "delete_model"), "CaseAdminSaveMixin 缺少 delete_model 方法"
    assert callable(CaseAdminSaveMixin.delete_model), "delete_model 不可调用"

    assert hasattr(CaseAdminSaveMixin, "delete_queryset"), "CaseAdminSaveMixin 缺少 delete_queryset 方法"
    assert callable(CaseAdminSaveMixin.delete_queryset), "delete_queryset 不可调用"


def test_case_admin_inherits_save_behaviors() -> None:
    """验证 CaseAdmin 通过 MRO 可访问 save_model/delete_model/delete_queryset，且来自 CaseAdminSaveMixin。"""
    from apps.cases.admin.case_admin import CaseAdmin
    from apps.cases.admin.mixins import CaseAdminSaveMixin

    mro = CaseAdmin.__mro__

    # CaseAdminSaveMixin 在 MRO 中
    assert CaseAdminSaveMixin in mro, f"CaseAdminSaveMixin 不在 CaseAdmin MRO 中: {mro}"

    # 三个方法均可通过继承访问
    for method_name in ("save_model", "delete_model", "delete_queryset"):
        assert hasattr(CaseAdmin, method_name), f"CaseAdmin 无法访问 {method_name}"

        # 方法来源于 CaseAdminSaveMixin（在 MRO 中先于其他定义）
        for cls in mro:
            if method_name in cls.__dict__:
                assert cls is CaseAdminSaveMixin, f"{method_name} 来自 {cls}，期望来自 CaseAdminSaveMixin"
                break
