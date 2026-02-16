"""
save_method_analyzer 单元测试

测试 SaveMethodAnalyzer 对 Django Model save() 方法的分类准确性。
"""
from __future__ import annotations

import textwrap

import pytest

from .save_method_analyzer import (
    BLOCK_BUSINESS_LOGIC,
    BLOCK_DATA_VALIDATION,
    BLOCK_FIELD_ASSIGNMENT,
    BLOCK_SUPER_CALL,
    SaveMethodAnalyzer,
)


@pytest.fixture
def analyzer() -> SaveMethodAnalyzer:
    return SaveMethodAnalyzer()


# ── super().save() 识别 ─────────────────────────────────────


class TestSuperCallDetection:
    """测试 super().save() 调用的识别"""

    def test_simple_super_save(self, analyzer: SaveMethodAnalyzer) -> None:
        source = textwrap.dedent("""\
            from django.db import models

            class MyModel(models.Model):
                def save(self, *args, **kwargs):
                    super().save(*args, **kwargs)
        """)
        results = analyzer.analyze_source(source)
        assert len(results) == 1
        blocks = results[0].blocks
        assert len(blocks) == 1
        assert blocks[0].block_type == BLOCK_SUPER_CALL

    def test_super_with_class_args(self, analyzer: SaveMethodAnalyzer) -> None:
        source = textwrap.dedent("""\
            from django.db import models

            class MyModel(models.Model):
                def save(self, *args, **kwargs):
                    super(MyModel, self).save(*args, **kwargs)
        """)
        results = analyzer.analyze_source(source)
        assert len(results) == 1
        assert results[0].blocks[0].block_type == BLOCK_SUPER_CALL


# ── 业务逻辑识别 ────────────────────────────────────────────


class TestBusinessLogicDetection:
    """测试业务逻辑模式的识别"""

    def test_other_model_objects_create(self, analyzer: SaveMethodAnalyzer) -> None:
        """创建关联对象应被识别为业务逻辑"""
        source = textwrap.dedent("""\
            from django.db import models

            class Contract(models.Model):
                def save(self, *args, **kwargs):
                    super().save(*args, **kwargs)
                    ContractFinanceLog.objects.create(contract=self, amount=100)
        """)
        results = analyzer.analyze_source(source)
        assert len(results) == 1
        analysis = results[0]
        assert analysis.has_business_logic is True
        biz_blocks = [b for b in analysis.blocks if b.block_type == BLOCK_BUSINESS_LOGIC]
        assert len(biz_blocks) == 1
        assert "ContractFinanceLog" in biz_blocks[0].description

    def test_external_service_call(self, analyzer: SaveMethodAnalyzer) -> None:
        """外部服务调用应被识别为业务逻辑"""
        source = textwrap.dedent("""\
            from django.db import models

            class Order(models.Model):
                def save(self, *args, **kwargs):
                    super().save(*args, **kwargs)
                    self.notify("order_created")
        """)
        results = analyzer.analyze_source(source)
        analysis = results[0]
        assert analysis.has_business_logic is True
        biz_blocks = [b for b in analysis.blocks if b.block_type == BLOCK_BUSINESS_LOGIC]
        assert len(biz_blocks) == 1
        assert "notify" in biz_blocks[0].description

    def test_conditional_business_logic(self, analyzer: SaveMethodAnalyzer) -> None:
        """条件分支中的业务逻辑应被识别"""
        source = textwrap.dedent("""\
            from django.db import models

            class Contract(models.Model):
                def save(self, *args, **kwargs):
                    super().save(*args, **kwargs)
                    if self.fixed_amount:
                        ContractFinanceLog.objects.create(
                            contract=self,
                            amount=self.fixed_amount,
                        )
        """)
        results = analyzer.analyze_source(source)
        analysis = results[0]
        assert analysis.has_business_logic is True

    def test_service_instantiation(self, analyzer: SaveMethodAnalyzer) -> None:
        """Service类实例化应被识别为业务逻辑"""
        source = textwrap.dedent("""\
            from django.db import models

            class Invoice(models.Model):
                def save(self, *args, **kwargs):
                    super().save(*args, **kwargs)
                    NotificationService().send(self.id)
        """)
        results = analyzer.analyze_source(source)
        analysis = results[0]
        assert analysis.has_business_logic is True
        biz_blocks = [b for b in analysis.blocks if b.block_type == BLOCK_BUSINESS_LOGIC]
        assert any("NotificationService" in b.description for b in biz_blocks)


# ── 数据验证识别 ────────────────────────────────────────────


class TestDataValidationDetection:
    """测试数据验证模式的识别"""

    def test_raise_validation_error(self, analyzer: SaveMethodAnalyzer) -> None:
        """raise ValidationError 应被识别为数据验证"""
        source = textwrap.dedent("""\
            from django.db import models
            from django.core.exceptions import ValidationError

            class MyModel(models.Model):
                def save(self, *args, **kwargs):
                    if not self.name:
                        raise ValidationError("name is required")
                    super().save(*args, **kwargs)
        """)
        results = analyzer.analyze_source(source)
        analysis = results[0]
        val_blocks = [b for b in analysis.blocks if b.block_type == BLOCK_DATA_VALIDATION]
        assert len(val_blocks) == 1

    def test_clean_call(self, analyzer: SaveMethodAnalyzer) -> None:
        """self.full_clean() 应被识别为数据验证"""
        source = textwrap.dedent("""\
            from django.db import models

            class MyModel(models.Model):
                def save(self, *args, **kwargs):
                    self.full_clean()
                    super().save(*args, **kwargs)
        """)
        results = analyzer.analyze_source(source)
        analysis = results[0]
        val_blocks = [b for b in analysis.blocks if b.block_type == BLOCK_DATA_VALIDATION]
        assert len(val_blocks) == 1
        assert "full_clean" in val_blocks[0].description


# ── 字段赋值识别 ────────────────────────────────────────────


class TestFieldAssignmentDetection:
    """测试简单字段赋值的识别"""

    def test_simple_field_default(self, analyzer: SaveMethodAnalyzer) -> None:
        """self.field = value 应被识别为字段赋值"""
        source = textwrap.dedent("""\
            from django.db import models

            class MyModel(models.Model):
                def save(self, *args, **kwargs):
                    self.status = "active"
                    super().save(*args, **kwargs)
        """)
        results = analyzer.analyze_source(source)
        analysis = results[0]
        assign_blocks = [b for b in analysis.blocks if b.block_type == BLOCK_FIELD_ASSIGNMENT]
        assert len(assign_blocks) == 1
        assert "status" in assign_blocks[0].description

    def test_field_assignment_with_orm_rhs(self, analyzer: SaveMethodAnalyzer) -> None:
        """右侧包含ORM调用的赋值应被识别为业务逻辑"""
        source = textwrap.dedent("""\
            from django.db import models

            class Contract(models.Model):
                def save(self, *args, **kwargs):
                    self.related_count = OtherModel.objects.filter(contract=self).count()
                    super().save(*args, **kwargs)
        """)
        results = analyzer.analyze_source(source)
        analysis = results[0]
        # 右侧有ORM调用，应归为业务逻辑
        biz_blocks = [b for b in analysis.blocks if b.block_type == BLOCK_BUSINESS_LOGIC]
        assert len(biz_blocks) >= 1


# ── 综合场景 ────────────────────────────────────────────────


class TestComprehensiveScenarios:
    """测试包含多种模式的综合场景"""

    def test_mixed_save_method(self, analyzer: SaveMethodAnalyzer) -> None:
        """包含验证、赋值、super调用和业务逻辑的混合save()"""
        source = textwrap.dedent("""\
            from django.db import models
            from django.core.exceptions import ValidationError

            class Contract(models.Model):
                def save(self, *args, **kwargs):
                    if not self.name:
                        raise ValidationError("name required")
                    self.status = "pending"
                    super().save(*args, **kwargs)
                    ContractLog.objects.create(contract=self, action="created")
        """)
        results = analyzer.analyze_source(source)
        analysis = results[0]

        types = [b.block_type for b in analysis.blocks]
        assert BLOCK_DATA_VALIDATION in types
        assert BLOCK_FIELD_ASSIGNMENT in types
        assert BLOCK_SUPER_CALL in types
        assert BLOCK_BUSINESS_LOGIC in types
        assert analysis.has_business_logic is True
        assert len(analysis.business_logic_summary) >= 1
        assert len(analysis.extraction_recommendations) >= 1

    def test_no_business_logic(self, analyzer: SaveMethodAnalyzer) -> None:
        """仅包含验证和super调用的save()不应标记为有业务逻辑"""
        source = textwrap.dedent("""\
            from django.db import models

            class MyModel(models.Model):
                def save(self, *args, **kwargs):
                    self.full_clean()
                    self.name = self.name.strip()
                    super().save(*args, **kwargs)
        """)
        results = analyzer.analyze_source(source)
        analysis = results[0]
        assert analysis.has_business_logic is False

    def test_non_model_class_ignored(self, analyzer: SaveMethodAnalyzer) -> None:
        """非Django Model类的save()方法应被忽略"""
        source = textwrap.dedent("""\
            class NotAModel:
                def save(self, *args, **kwargs):
                    SomeService().send("data")
        """)
        results = analyzer.analyze_source(source)
        assert len(results) == 0

    def test_no_save_method(self, analyzer: SaveMethodAnalyzer) -> None:
        """没有save()覆写的Model应返回空结果"""
        source = textwrap.dedent("""\
            from django.db import models

            class SimpleModel(models.Model):
                name = models.CharField(max_length=100)
        """)
        results = analyzer.analyze_source(source)
        assert len(results) == 0

    def test_model_name_in_analysis(self, analyzer: SaveMethodAnalyzer) -> None:
        """分析结果应包含正确的Model名称"""
        source = textwrap.dedent("""\
            from django.db import models

            class Invoice(models.Model):
                def save(self, *args, **kwargs):
                    super().save(*args, **kwargs)
        """)
        results = analyzer.analyze_source(source)
        assert results[0].model_name == "Invoice"

    def test_docstring_skipped(self, analyzer: SaveMethodAnalyzer) -> None:
        """save()方法中的文档字符串应被跳过"""
        source = textwrap.dedent("""\
            from django.db import models

            class MyModel(models.Model):
                def save(self, *args, **kwargs):
                    \"\"\"Custom save logic.\"\"\"
                    super().save(*args, **kwargs)
        """)
        results = analyzer.analyze_source(source)
        analysis = results[0]
        # 文档字符串不应出现在blocks中
        assert len(analysis.blocks) == 1
        assert analysis.blocks[0].block_type == BLOCK_SUPER_CALL
