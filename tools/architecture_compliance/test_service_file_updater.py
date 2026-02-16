"""
ServiceFileUpdater 单元测试

测试 Service 文件更新器的核心功能：
- 移除跨模块 Model 导入
- 添加 ServiceLocator 导入
- 替换 Model.objects.* 调用为 ServiceLocator 调用
- 处理复杂场景（链式调用、类型注解、部分导入移除）
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from .service_file_updater import ServiceFileUpdater
from .service_refactoring_engine import (
    CrossModuleImport,
    FileRefactoringPlan,
    ModelUsage,
    ReplacementSpec,
    ServiceRefactoringEngine,
)


@pytest.fixture
def updater() -> ServiceFileUpdater:
    return ServiceFileUpdater()


@pytest.fixture
def engine() -> ServiceRefactoringEngine:
    return ServiceRefactoringEngine()


@pytest.fixture
def tmp_service_file(tmp_path: Path) -> Path:
    """创建一个临时 Service 文件用于测试"""
    return tmp_path / "test_service.py"


# ── 基本替换测试 ────────────────────────────────────────────


class TestBasicOrmReplacement:
    """测试基本的 Model.objects.* 替换"""

    def test_replace_objects_get(
        self, updater: ServiceFileUpdater, engine: ServiceRefactoringEngine,
        tmp_service_file: Path,
    ) -> None:
        """测试 Model.objects.get() 替换为 ServiceLocator 调用"""
        source = textwrap.dedent("""\
            from apps.cases.models import Case

            class ContractService:
                def link_case(self, contract_id, case_id):
                    case = Case.objects.get(id=case_id)
                    return case
        """)
        tmp_service_file.write_text(source, encoding="utf-8")

        plan = engine.analyze_file(tmp_service_file)
        result = updater.apply_replacements(tmp_service_file, plan)

        assert result.success is True
        updated = tmp_service_file.read_text(encoding="utf-8")

        # 应该移除跨模块导入
        assert "from apps.cases.models import Case" not in updated
        # 应该添加 ServiceLocator 导入
        assert "from apps.core.interfaces import ServiceLocator" in updated
        # 应该替换 ORM 调用
        assert "Case.objects.get" not in updated
        assert "ServiceLocator.get_case_service().get_case_internal(" in updated

    def test_replace_objects_filter(
        self, updater: ServiceFileUpdater, engine: ServiceRefactoringEngine,
        tmp_service_file: Path,
    ) -> None:
        """测试 Model.objects.filter() 替换"""
        source = textwrap.dedent("""\
            from apps.cases.models import Case

            class ContractService:
                def list_cases(self):
                    cases = Case.objects.filter(status='active')
                    return cases
        """)
        tmp_service_file.write_text(source, encoding="utf-8")

        plan = engine.analyze_file(tmp_service_file)
        result = updater.apply_replacements(tmp_service_file, plan)

        assert result.success is True
        updated = tmp_service_file.read_text(encoding="utf-8")
        assert "Case.objects.filter" not in updated
        assert "ServiceLocator.get_case_service().query_cases_internal(" in updated

    def test_replace_objects_create(
        self, updater: ServiceFileUpdater, engine: ServiceRefactoringEngine,
        tmp_service_file: Path,
    ) -> None:
        """测试 Model.objects.create() 替换"""
        source = textwrap.dedent("""\
            from apps.cases.models import CaseLog

            class ContractService:
                def add_log(self, case_id, message):
                    log = CaseLog.objects.create(case_id=case_id, message=message)
                    return log
        """)
        tmp_service_file.write_text(source, encoding="utf-8")

        plan = engine.analyze_file(tmp_service_file)
        result = updater.apply_replacements(tmp_service_file, plan)

        assert result.success is True
        updated = tmp_service_file.read_text(encoding="utf-8")
        assert "CaseLog.objects.create" not in updated
        assert "ServiceLocator.get_case_service().create_case_log_internal(" in updated


# ── 导入处理测试 ────────────────────────────────────────────


class TestImportHandling:
    """测试导入语句的处理"""

    def test_remove_entire_import_line(
        self, updater: ServiceFileUpdater, engine: ServiceRefactoringEngine,
        tmp_service_file: Path,
    ) -> None:
        """测试整行移除跨模块导入"""
        source = textwrap.dedent("""\
            from apps.cases.models import Case

            class MyService:
                def do_something(self):
                    case = Case.objects.get(id=1)
                    return case
        """)
        tmp_service_file.write_text(source, encoding="utf-8")

        plan = engine.analyze_file(tmp_service_file)
        result = updater.apply_replacements(tmp_service_file, plan)

        assert result.success is True
        updated = tmp_service_file.read_text(encoding="utf-8")
        assert "from apps.cases.models import Case" not in updated

    def test_partial_import_removal(
        self, updater: ServiceFileUpdater, engine: ServiceRefactoringEngine,
        tmp_service_file: Path,
    ) -> None:
        """测试部分导入移除（保留无 getter 的 Model）"""
        # UnknownModel 没有在 _MODEL_GETTER_MAP 中，应该保留
        source = textwrap.dedent("""\
            from apps.cases.models import Case, UnknownModel

            class MyService:
                def do_something(self):
                    case = Case.objects.get(id=1)
                    obj = UnknownModel()
                    return case, obj
        """)
        tmp_service_file.write_text(source, encoding="utf-8")

        plan = engine.analyze_file(tmp_service_file)
        result = updater.apply_replacements(tmp_service_file, plan)

        assert result.success is True
        updated = tmp_service_file.read_text(encoding="utf-8")
        # Case 应该被移除，UnknownModel 应该保留
        assert "UnknownModel" in updated
        assert "Case.objects.get" not in updated

    def test_no_duplicate_service_locator_import(
        self, updater: ServiceFileUpdater, engine: ServiceRefactoringEngine,
        tmp_service_file: Path,
    ) -> None:
        """测试不重复添加 ServiceLocator 导入"""
        source = textwrap.dedent("""\
            from apps.core.interfaces import ServiceLocator
            from apps.cases.models import Case

            class MyService:
                def do_something(self):
                    case = Case.objects.get(id=1)
                    return case
        """)
        tmp_service_file.write_text(source, encoding="utf-8")

        plan = engine.analyze_file(tmp_service_file)
        result = updater.apply_replacements(tmp_service_file, plan)

        assert result.success is True
        updated = tmp_service_file.read_text(encoding="utf-8")
        # 应该只有一个 ServiceLocator 导入
        count = updated.count("from apps.core.interfaces import ServiceLocator")
        assert count == 1


# ── 复杂场景测试 ────────────────────────────────────────────


class TestComplexScenarios:
    """测试复杂场景"""

    def test_chained_call_gets_manual_review(
        self, updater: ServiceFileUpdater, engine: ServiceRefactoringEngine,
        tmp_service_file: Path,
    ) -> None:
        """测试链式调用标记为需要人工审查"""
        source = textwrap.dedent("""\
            from apps.cases.models import Case

            class MyService:
                def do_something(self):
                    cases = Case.objects.filter(status='active').order_by('-created')
                    return cases
        """)
        tmp_service_file.write_text(source, encoding="utf-8")

        plan = engine.analyze_file(tmp_service_file)
        result = updater.apply_replacements(tmp_service_file, plan)

        assert result.success is True
        updated = tmp_service_file.read_text(encoding="utf-8")
        # 链式调用应该添加 TODO 注释
        assert "# TODO: 需要人工审查" in updated

    def test_type_annotation_gets_manual_review(
        self, updater: ServiceFileUpdater, engine: ServiceRefactoringEngine,
        tmp_service_file: Path,
    ) -> None:
        """测试类型注解标记为需要人工审查"""
        source = textwrap.dedent("""\
            from apps.cases.models import Case

            class MyService:
                def process_case(self, case: Case) -> None:
                    pass
        """)
        tmp_service_file.write_text(source, encoding="utf-8")

        plan = engine.analyze_file(tmp_service_file)
        result = updater.apply_replacements(tmp_service_file, plan)

        assert result.success is True
        # 类型注解应该在变更列表中标记为需要人工审查
        has_review = any("人工审查" in c for c in result.changes_made)
        assert has_review

    def test_multiple_models_from_same_module(
        self, updater: ServiceFileUpdater, engine: ServiceRefactoringEngine,
        tmp_service_file: Path,
    ) -> None:
        """测试同一模块导入多个 Model"""
        source = textwrap.dedent("""\
            from apps.cases.models import Case, CaseLog

            class MyService:
                def do_something(self, case_id):
                    case = Case.objects.get(id=case_id)
                    CaseLog.objects.create(case_id=case_id, message='test')
                    return case
        """)
        tmp_service_file.write_text(source, encoding="utf-8")

        plan = engine.analyze_file(tmp_service_file)
        result = updater.apply_replacements(tmp_service_file, plan)

        assert result.success is True
        updated = tmp_service_file.read_text(encoding="utf-8")
        assert "Case.objects.get" not in updated
        assert "CaseLog.objects.create" not in updated
        assert "ServiceLocator.get_case_service()" in updated


# ── 边界情况测试 ────────────────────────────────────────────


class TestEdgeCases:
    """测试边界情况"""

    def test_file_not_found(
        self, updater: ServiceFileUpdater,
    ) -> None:
        """测试文件不存在"""
        plan = FileRefactoringPlan(
            file_path="/nonexistent/file.py",
            source_module="test",
        )
        result = updater.apply_replacements(
            Path("/nonexistent/file.py"), plan,
        )
        assert result.success is False
        assert "文件不存在" in (result.error_message or "")

    def test_empty_plan(
        self, updater: ServiceFileUpdater, tmp_service_file: Path,
    ) -> None:
        """测试空的重构计划"""
        source = "# empty file\n"
        tmp_service_file.write_text(source, encoding="utf-8")

        plan = FileRefactoringPlan(
            file_path=str(tmp_service_file),
            source_module="test",
        )
        result = updater.apply_replacements(tmp_service_file, plan)
        assert result.success is True
        assert "无需替换" in result.changes_made[0]

    def test_dry_run_does_not_write(
        self, updater: ServiceFileUpdater, engine: ServiceRefactoringEngine,
        tmp_service_file: Path,
    ) -> None:
        """测试 dry_run 模式不写入文件"""
        source = textwrap.dedent("""\
            from apps.cases.models import Case

            class MyService:
                def do_something(self):
                    case = Case.objects.get(id=1)
                    return case
        """)
        tmp_service_file.write_text(source, encoding="utf-8")

        plan = engine.analyze_file(tmp_service_file)
        result = updater.apply_replacements(
            tmp_service_file, plan, dry_run=True,
        )

        assert result.success is True
        # 文件内容应该没有变化
        assert tmp_service_file.read_text(encoding="utf-8") == source

    def test_syntax_error_in_result_returns_failure(
        self, updater: ServiceFileUpdater, tmp_service_file: Path,
    ) -> None:
        """测试重构后语法错误返回失败"""
        # 构造一个会导致语法错误的场景
        # 使用一个有效的源文件但构造一个会产生坏替换的 plan
        source = textwrap.dedent("""\
            from apps.cases.models import Case

            def broken():
                case = Case.objects.get(id=1
        """)
        tmp_service_file.write_text(source, encoding="utf-8")

        plan = FileRefactoringPlan(
            file_path=str(tmp_service_file),
            source_module="test",
            cross_module_imports=[
                CrossModuleImport(
                    line_number=1,
                    module_path="apps.cases.models",
                    target_module="cases",
                    imported_names=["Case"],
                    import_statement="from apps.cases.models import Case",
                ),
            ],
            models_with_getter=["Case"],
            replacements=[
                ReplacementSpec(
                    model_name="Case",
                    getter_method="get_case_service",
                    service_method="get_case_internal",
                    original_code="Case.objects.get(...)",
                    replacement_code="ServiceLocator.get_case_service().get_case_internal(...)",
                    line_number=4,
                ),
            ],
            needs_service_locator_import=True,
        )

        result = updater.apply_replacements(tmp_service_file, plan)
        # 源文件本身就有语法错误，替换后也会有
        assert result.success is False
        assert "语法错误" in (result.error_message or "")
