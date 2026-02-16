"""
测试 Schemas 与 Django Models 的集成
验证 from_attributes 配置正确工作
"""
import pytest
from decimal import Decimal
from django.utils import timezone

from apps.automation.models import PreservationQuote, InsuranceQuote, QuoteStatus, QuoteItemStatus
from apps.automation.schemas import (
    PreservationQuoteSchema,
    InsuranceQuoteSchema,
    QuoteListItemSchema
)


@pytest.mark.django_db
class TestSchemaModelIntegration:
    """测试 Schema 与 Model 的集成"""

    def test_preservation_quote_from_model(self):
        """测试从 PreservationQuote 模型创建 Schema"""
        # 创建模型实例
        quote = PreservationQuote.objects.create(
            preserve_amount=Decimal("100000.00"),
            corp_id="440100",
            category_id="1",
            credential_id=1,
            status=QuoteStatus.PENDING,
            total_companies=0,
            success_count=0,
            failed_count=0
        )
        
        # 从模型创建 Schema
        schema = PreservationQuoteSchema.from_model(quote)
        
        assert schema.id == quote.id
        assert schema.preserve_amount == Decimal("100000.00")
        assert schema.corp_id == "440100"
        assert schema.status == QuoteStatus.PENDING
        assert schema.quotes == []  # 空列表

    def test_insurance_quote_from_model(self):
        """测试从 InsuranceQuote 模型创建 Schema"""
        # 创建询价任务
        preservation_quote = PreservationQuote.objects.create(
            preserve_amount=Decimal("100000.00"),
            corp_id="440100",
            category_id="1",
            credential_id=1,
            status=QuoteStatus.SUCCESS
        )
        
        # 创建保险公司报价
        insurance_quote = InsuranceQuote.objects.create(
            preservation_quote=preservation_quote,
            company_id="C001",
            company_code="CODE001",
            company_name="测试保险公司",
            premium=Decimal("5000.00"),
            status=QuoteItemStatus.SUCCESS
        )
        
        # 从模型创建 Schema
        schema = InsuranceQuoteSchema.model_validate(insurance_quote)
        
        assert schema.id == insurance_quote.id
        assert schema.preservation_quote_id == preservation_quote.id
        assert schema.company_name == "测试保险公司"
        assert schema.premium == Decimal("5000.00")
        assert schema.status == QuoteItemStatus.SUCCESS

    def test_preservation_quote_with_related_quotes(self):
        """测试包含关联报价的询价任务"""
        # 创建询价任务
        preservation_quote = PreservationQuote.objects.create(
            preserve_amount=Decimal("100000.00"),
            corp_id="440100",
            category_id="1",
            credential_id=1,
            status=QuoteStatus.SUCCESS,
            total_companies=2,
            success_count=2,
            failed_count=0
        )
        
        # 创建两个保险公司报价
        InsuranceQuote.objects.create(
            preservation_quote=preservation_quote,
            company_id="C001",
            company_code="CODE001",
            company_name="保险公司A",
            premium=Decimal("5000.00"),
            status=QuoteItemStatus.SUCCESS
        )
        
        InsuranceQuote.objects.create(
            preservation_quote=preservation_quote,
            company_id="C002",
            company_code="CODE002",
            company_name="保险公司B",
            premium=Decimal("4500.00"),
            status=QuoteItemStatus.SUCCESS
        )
        
        # 从模型创建 Schema
        schema = PreservationQuoteSchema.from_model(preservation_quote)
        
        assert schema.id == preservation_quote.id
        assert len(schema.quotes) == 2
        assert schema.quotes[0].company_name in ["保险公司A", "保险公司B"]
        assert schema.quotes[1].company_name in ["保险公司A", "保险公司B"]

    def test_quote_list_item_from_model(self):
        """测试从模型创建列表项 Schema"""
        # 创建询价任务
        quote = PreservationQuote.objects.create(
            preserve_amount=Decimal("100000.00"),
            corp_id="440100",
            category_id="1",
            credential_id=1,
            status=QuoteStatus.SUCCESS,
            total_companies=10,
            success_count=8,
            failed_count=2
        )
        
        # 从模型创建 Schema
        schema = QuoteListItemSchema.from_model(quote)
        
        assert schema.id == quote.id
        assert schema.preserve_amount == Decimal("100000.00")
        assert schema.total_companies == 10
        assert schema.success_count == 8
        assert schema.failed_count == 2
        assert schema.success_rate == 80.0  # 8/10 * 100

    def test_json_serialization_with_model(self):
        """测试模型数据的 JSON 序列化"""
        # 创建询价任务
        quote = PreservationQuote.objects.create(
            preserve_amount=Decimal("100000.00"),
            corp_id="440100",
            category_id="1",
            credential_id=1,
            status=QuoteStatus.SUCCESS
        )
        
        # 从模型创建 Schema
        schema = PreservationQuoteSchema.from_model(quote)
        
        # 序列化为字典
        data = schema.model_dump()
        
        assert isinstance(data["preserve_amount"], Decimal)
        assert data["corp_id"] == "440100"
        assert data["status"] == QuoteStatus.SUCCESS
        
        # 序列化为 JSON 字符串
        json_str = schema.model_dump_json()
        assert isinstance(json_str, str)
        assert "100000" in json_str
