"""
business_logic_extractor 单元测试

测试 BusinessLogicExtractor 从 save() 方法分析结果中
提取业务逻辑、生成 Service 方法模板和清理后的 save()/clean() 方法。
"""

from __future__ import annotations

import textwrap

import pytest

from .business_logic_extractor import (
    BusinessLogicExtractor,
    ExtractedServiceMethod,
    SaveMethodRefactoring,
    _derive_method_name_from_description,
    _rewrite_self_to_param,
    _to_snake_case,
    format_service_method_template,
)
from .save_method_analyzer import (
    BLOCK_BUSINESS_LOGIC,
    BLOCK_DATA_VALIDATION,
    BLOCK_FIELD_ASSIGNMENT,
    BLOCK_SUPER_CALL,
    SaveMethodAnalysis,
    SaveMethodAnalyzer,
)


@pytest.fixture
def analyzer() -> SaveMethodAnalyzer:
    return SaveMethodAnalyzer()


@pytest.fixture
def extractor() -> BusinessLogicExtractor:
    return BusinessLogicExtractor()


# ── 辅助函数测试 ────────────────────────────────────────────


class TestToSnakeCase:
    """测试 CamelCase → snake_case 转换"""

    def test_simple(self) -> None:
        assert _to_snake_case("Contract") == "contract"

    def test_multi_word(self) -> None:
        assert _to_snake_case("ContractFinanceLog") == "contract_finance_log"

    def test_abbreviation(self) -> None:
        assert _to_snake_case("HTTPResponse") == "http_response"

    def test_single_char(self) -> None:
        assert _to_snake_case("A") == "a"


class TestDeriveMethodName:
    """测试从描述推导方法名"""

    def test_orm_create(self) -> None:
        desc = "调用其他Model: ContractFinanceLog.objects.create()"
        name = _derive_method_name_from_description(desc, "Contract")
        assert name == "create_contract_finance_log"

    def test_orm_filter(self) -> None:
        desc = "调用其他Model: Order.objects.filter()"
        name = _derive_method_name_from_description(desc, "Invoice")
        assert name == "query_order"

    def test_external_service_notify(self) -> None:
        desc = "外部服务调用: notify()"
        name = _derive_method_name_from_description(desc, "Order")
        assert name == "notify_order_event"

    def test_service_instantiation(self) -> None:
        desc = "实例化服务: NotificationService()"
        name = _derive_method_name_from_description(desc, "Invoice")
        assert name == "call_notification_service"

    def test_conditional_business_logic(self) -> None:
        desc = "条件分支中的业务逻辑: 调用其他Model: FinanceLog.objects.create()"
        name = _derive_method_name_from_description(desc, "Contract")
        assert name == "create_finance_log"

    def test_complex_calculation(self) -> None:
        desc = "复杂计算逻辑（4个算术运算）"
        name = _derive_method_name_from_description(desc, "Invoice")
        assert name == "calculate_invoice_fields"

    def test_fallback(self) -> None:
        desc = "未知的业务逻辑模式"
        name = _derive_method_name_from_description(desc, "Contract")
        assert name == "handle_contract_business_logic"


class TestRewriteSelfToParam:
    """测试 self.xxx → param.xxx 替换"""

    def test_simple_replacement(self) -> None:
        code = "self.amount + self.tax"
        result = _rewrite_self_to_param(code, "Invoice")
        assert result == "invoice.amount + invoice.tax"

    def test_no_self(self) -> None:
        code = "SomeModel.objects.create(amount=100)"
        result = _rewrite_self_to_param(code, "Contract")
        assert result == "SomeModel.objects.create(amount=100)"

    def test_mixed(self) -> None:
        code = "Log.objects.create(contract=self, amount=self.fixed_amount)"
        result = _rewrite_self_to_param(code, "Contract")
        assert result == "Log.objects.create(contract=contract, amount=contract.fixed_amount)"


# ── 核心提取逻辑测试 ────────────────────────────────────────


class TestExtractBusinessLogic:
    """测试业务逻辑提取的核心流程"""

    def test_extract_single_business_logic(
        self,
        analyzer: SaveMethodAnalyzer,
        extractor: BusinessLogicExtractor,
    ) -> None:
        """提取单个业务逻辑块"""
        source = textwrap.dedent(
            """\
            from django.db import models

            class Contract(models.Model):
                def save(self, *args, **kwargs):
                    super().save(*args, **kwargs)
                    ContractFinanceLog.objects.create(contract=self, amount=100)
        """
        )
        analyses = analyzer.analyze_source(source)
        assert len(analyses) == 1

        result = extractor.extract(analyses[0])

        assert isinstance(result, SaveMethodRefactoring)
        assert result.model_name == "Contract"
        assert len(result.service_methods) == 1

        method = result.service_methods[0]
        assert "create" in method.method_name
        assert "finance_log" in method.method_name or "contract_finance_log" in method.method_name
        assert len(method.parameters) >= 1
        assert "contract: Contract" in method.parameters[0]
        assert "ContractFinanceLog" in method.body_code

    def test_extract_multiple_business_logic(
        self,
        analyzer: SaveMethodAnalyzer,
        extractor: BusinessLogicExtractor,
    ) -> None:
        """提取多个业务逻辑块"""
        source = textwrap.dedent(
            """\
            from django.db import models

            class Order(models.Model):
                def save(self, *args, **kwargs):
                    super().save(*args, **kwargs)
                    OrderLog.objects.create(order=self, action="saved")
                    self.notify("order_saved")
        """
        )
        analyses = analyzer.analyze_source(source)
        result = extractor.extract(analyses[0])

        assert len(result.service_methods) == 2
        method_names = [m.method_name for m in result.service_methods]
        # 应该有两个不同的方法名
        assert len(set(method_names)) == 2

    def test_no_business_logic_returns_empty_methods(
        self,
        analyzer: SaveMethodAnalyzer,
        extractor: BusinessLogicExtractor,
    ) -> None:
        """无业务逻辑时返回空的 service_methods"""
        source = textwrap.dedent(
            """\
            from django.db import models

            class MyModel(models.Model):
                def save(self, *args, **kwargs):
                    self.name = self.name.strip()
                    super().save(*args, **kwargs)
        """
        )
        analyses = analyzer.analyze_source(source)
        result = extractor.extract(analyses[0])

        assert len(result.service_methods) == 0


class TestCleanedSaveGeneration:
    """测试清理后的 save() 方法生成"""

    def test_cleaned_save_keeps_assignments_and_super(
        self,
        analyzer: SaveMethodAnalyzer,
        extractor: BusinessLogicExtractor,
    ) -> None:
        """清理后的 save() 保留字段赋值和 super 调用"""
        source = textwrap.dedent(
            """\
            from django.db import models

            class Contract(models.Model):
                def save(self, *args, **kwargs):
                    self.status = "pending"
                    super().save(*args, **kwargs)
                    ContractLog.objects.create(contract=self)
        """
        )
        analyses = analyzer.analyze_source(source)
        result = extractor.extract(analyses[0])

        cleaned = result.cleaned_save_code
        assert "def save(self, *args, **kwargs):" in cleaned
        assert 'self.status = "pending"' in cleaned
        assert "super().save(*args, **kwargs)" in cleaned
        # 业务逻辑应被移除
        assert "ContractLog" not in cleaned

    def test_cleaned_save_removes_all_business_logic(
        self,
        analyzer: SaveMethodAnalyzer,
        extractor: BusinessLogicExtractor,
    ) -> None:
        """清理后的 save() 移除所有业务逻辑"""
        source = textwrap.dedent(
            """\
            from django.db import models

            class Order(models.Model):
                def save(self, *args, **kwargs):
                    super().save(*args, **kwargs)
                    OrderLog.objects.create(order=self)
                    self.notify("saved")
        """
        )
        analyses = analyzer.analyze_source(source)
        result = extractor.extract(analyses[0])

        cleaned = result.cleaned_save_code
        assert "OrderLog" not in cleaned
        assert "notify" not in cleaned
        assert "super().save" in cleaned


class TestCleanMethodGeneration:
    """测试 clean() 方法生成"""

    def test_clean_method_from_validation(
        self,
        analyzer: SaveMethodAnalyzer,
        extractor: BusinessLogicExtractor,
    ) -> None:
        """验证逻辑应被提取到 clean() 方法"""
        source = textwrap.dedent(
            """\
            from django.db import models
            from django.core.exceptions import ValidationError

            class Contract(models.Model):
                def save(self, *args, **kwargs):
                    if not self.name:
                        raise ValidationError("name required")
                    super().save(*args, **kwargs)
                    ContractLog.objects.create(contract=self)
        """
        )
        analyses = analyzer.analyze_source(source)
        result = extractor.extract(analyses[0])

        assert result.clean_method_code is not None
        assert "def clean(self):" in result.clean_method_code
        assert "ValidationError" in result.clean_method_code

    def test_no_clean_method_without_validation(
        self,
        analyzer: SaveMethodAnalyzer,
        extractor: BusinessLogicExtractor,
    ) -> None:
        """无验证逻辑时不生成 clean() 方法"""
        source = textwrap.dedent(
            """\
            from django.db import models

            class Contract(models.Model):
                def save(self, *args, **kwargs):
                    super().save(*args, **kwargs)
                    ContractLog.objects.create(contract=self)
        """
        )
        analyses = analyzer.analyze_source(source)
        result = extractor.extract(analyses[0])

        assert result.clean_method_code is None


class TestExtractFromFile:
    """测试批量提取"""

    def test_skips_models_without_business_logic(
        self,
        analyzer: SaveMethodAnalyzer,
        extractor: BusinessLogicExtractor,
    ) -> None:
        """跳过没有业务逻辑的 Model"""
        source = textwrap.dedent(
            """\
            from django.db import models

            class SimpleModel(models.Model):
                def save(self, *args, **kwargs):
                    self.name = self.name.strip()
                    super().save(*args, **kwargs)

            class ComplexModel(models.Model):
                def save(self, *args, **kwargs):
                    super().save(*args, **kwargs)
                    AuditLog.objects.create(model=self)
        """
        )
        analyses = analyzer.analyze_source(source)
        from pathlib import Path

        results = extractor.extract_from_file(Path("<test>"), analyses)

        # 只有 ComplexModel 有业务逻辑
        assert len(results) == 1
        assert results[0].model_name == "ComplexModel"


class TestFormatServiceMethodTemplate:
    """测试 Service 方法模板格式化"""

    def test_basic_formatting(self) -> None:
        method = ExtractedServiceMethod(
            method_name="create_finance_log",
            parameters=["contract: Contract"],
            body_code="FinanceLog.objects.create(contract=contract)",
            description="创建财务记录",
            source_lines=(10, 12),
        )
        result = format_service_method_template(method)

        assert "def create_finance_log(self, contract: Contract) -> None:" in result
        assert '"""创建财务记录"""' in result
        assert "FinanceLog.objects.create(contract=contract)" in result

    def test_custom_indent(self) -> None:
        method = ExtractedServiceMethod(
            method_name="do_something",
            parameters=["obj: MyModel"],
            body_code="pass",
            description="test",
            source_lines=(1, 1),
        )
        result = format_service_method_template(method, indent="  ")
        assert result.startswith("  def do_something")


class TestDuplicateMethodNames:
    """测试方法名去重"""

    def test_duplicate_names_get_suffix(
        self,
        analyzer: SaveMethodAnalyzer,
        extractor: BusinessLogicExtractor,
    ) -> None:
        """相同描述的业务逻辑块应生成不同的方法名"""
        source = textwrap.dedent(
            """\
            from django.db import models

            class Order(models.Model):
                def save(self, *args, **kwargs):
                    super().save(*args, **kwargs)
                    AuditLog.objects.create(order=self, action="a")
                    AuditLog.objects.create(order=self, action="b")
        """
        )
        analyses = analyzer.analyze_source(source)
        result = extractor.extract(analyses[0])

        method_names = [m.method_name for m in result.service_methods]
        # 所有方法名应唯一
        assert len(method_names) == len(set(method_names))
