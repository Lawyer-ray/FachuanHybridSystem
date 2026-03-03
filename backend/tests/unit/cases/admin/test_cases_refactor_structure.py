"""
Feature: cases-app-refactor
验证 CaseAdmin MRO、无重复方法、模块级工厂函数已移除、新行为可访问
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Any

from django.test import SimpleTestCase


class TestCaseAdminMRO(SimpleTestCase):
    """需求 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 6.1, 6.2"""

    def test_case_admin_mro(self) -> None:
        """验证 CaseAdmin.__mro__ 包含三个 mixin"""
        from apps.cases.admin.case_admin import CaseAdmin
        from apps.cases.admin.mixins import CaseAdminActionsMixin, CaseAdminSaveMixin, CaseAdminViewsMixin

        mro_names = [cls.__name__ for cls in CaseAdmin.__mro__]
        self.assertIn("CaseAdminActionsMixin", mro_names)
        self.assertIn("CaseAdminSaveMixin", mro_names)
        self.assertIn("CaseAdminViewsMixin", mro_names)

    def test_case_admin_no_duplicate_methods(self) -> None:
        """验证重复方法不在 CaseAdmin.__dict__"""
        from apps.cases.admin.case_admin import CaseAdmin

        for method in (
            "response_change",
            "create_feishu_chat_for_selected_cases",
            "save_formset",
        ):
            self.assertNotIn(
                method,
                CaseAdmin.__dict__,
                msg=f"CaseAdmin.__dict__ 不应直接定义 {method}（应由 mixin 提供）",
            )

    def test_case_admin_no_module_level_factories(self) -> None:
        """验证 case_admin 模块无模块级工厂函数"""
        import apps.cases.admin.case_admin as case_admin_module

        self.assertFalse(
            hasattr(case_admin_module, "_get_case_chat_service"),
            "case_admin 模块不应有模块级 _get_case_chat_service",
        )
        self.assertFalse(
            hasattr(case_admin_module, "_get_case_admin_service"),
            "case_admin 模块不应有模块级 _get_case_admin_service",
        )

    def test_case_admin_inherited_save_behaviors(self) -> None:
        """验证 save_model、delete_model、delete_queryset 可通过继承访问"""
        from apps.cases.admin.case_admin import CaseAdmin

        for method in ("save_model", "delete_model", "delete_queryset"):
            self.assertTrue(
                hasattr(CaseAdmin, method),
                msg=f"CaseAdmin 应通过继承获得 {method}",
            )


class TestDeadCodeRemoved(SimpleTestCase):
    """需求 2.1, 2.2, 2.3, 2.4"""

    def test_dead_code_files_removed(self) -> None:
        """验证死代码文件已删除"""
        admin_dir = Path(__file__).parent.parent.parent.parent.parent / "apps" / "cases" / "admin"
        self.assertFalse(
            (admin_dir / "case_base_admin.py").exists(),
            "case_base_admin.py 应已删除",
        )
        self.assertFalse(
            (admin_dir / "case_inlines_admin.py").exists(),
            "case_inlines_admin.py 应已删除",
        )

    def test_cases_admin_import_no_error(self) -> None:
        """验证 import apps.cases.admin 不抛异常"""
        try:
            importlib.import_module("apps.cases.admin")
        except Exception as exc:
            self.fail(f"import apps.cases.admin 抛出异常: {exc}")


class TestAPIFactoryFunctions(SimpleTestCase):
    """需求 4.1, 4.2, 4.3"""

    def test_api_factory_functions_exist(self) -> None:
        """验证 case_api 模块有三个工厂函数"""
        import apps.cases.api.case_api as case_api_module

        for fn_name in (
            "_get_case_service",
            "_get_case_query_facade",
            "_get_case_mutation_facade",
        ):
            self.assertTrue(
                hasattr(case_api_module, fn_name),
                msg=f"case_api 模块应有 {fn_name}",
            )

    def test_api_facade_delegates_to_service(self) -> None:
        """验证 facade 函数体内部委托 _get_case_service"""
        import apps.cases.api.case_api as case_api_module

        for fn_name in ("_get_case_query_facade", "_get_case_mutation_facade"):
            fn = getattr(case_api_module, fn_name)
            source = inspect.getsource(fn)
            self.assertIn(
                "_get_case_service",
                source,
                msg=f"{fn_name} 函数体应调用 _get_case_service",
            )


class TestConstantsAndBaseModule(SimpleTestCase):
    """需求 5.2, 7.1, 7.2, 7.3, 7.4, 7.5"""

    def test_caselog_service_no_duplicate_constants(self) -> None:
        """验证 CaseLogService 类中无 ALLOWED_EXTENSIONS、MAX_FILE_SIZE 属性"""
        from apps.cases.services.caselog_service import CaseLogService

        self.assertNotIn(
            "ALLOWED_EXTENSIONS",
            CaseLogService.__dict__,
            "CaseLogService 不应有 ALLOWED_EXTENSIONS 类属性（应从 utils.py 导入）",
        )
        self.assertNotIn(
            "MAX_FILE_SIZE",
            CaseLogService.__dict__,
            "CaseLogService 不应有 MAX_FILE_SIZE 类属性（应从 utils.py 导入）",
        )

    def test_admin_base_py_exists(self) -> None:
        """验证 admin/base.py 文件存在"""
        base_py = Path(__file__).parent.parent.parent.parent.parent / "apps" / "cases" / "admin" / "base.py"
        self.assertTrue(base_py.exists(), "admin/base.py 应存在")

    def test_admin_files_import_from_base(self) -> None:
        """验证各 admin 文件从 base.py 导入"""
        admin_dir = Path(__file__).parent.parent.parent.parent.parent / "apps" / "cases" / "admin"
        files = [
            "case_admin.py",
            "case_chat_admin.py",
            "case_document_template_inline_admin.py",
            "caselog_admin.py",
        ]
        for filename in files:
            source = (admin_dir / filename).read_text(encoding="utf-8")
            has_import = "from apps.cases.admin.base import" in source or "from .base import" in source
            self.assertTrue(
                has_import,
                msg=f"{filename} 应从 apps.cases.admin.base 或 .base 导入",
            )
