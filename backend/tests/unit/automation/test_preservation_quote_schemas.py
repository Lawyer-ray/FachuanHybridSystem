"""
测试财产保全询价 Schemas
验证数据验证和序列化功能
"""
import pytest
from decimal import Decimal
from datetime import datetime
from pydantic import ValidationError

from apps.automation.schemas import (
    PreservationQuoteCreateSchema,
    InsuranceQuoteSchema,
    PreservationQuoteSchema,
    QuoteListItemSchema,
    QuoteListSchema,
    QuoteExecuteResponseSchema
)


class TestPreservationQuoteCreateSchema:
    """测试创建询价任务的输入验证"""

    def test_valid_data(self):
        """测试有效数据"""
        data = {
            "preserve_amount": 100000.00,
            "corp_id": "440100",
            "category_id": "1",
            "credential_id": 1
        }
        schema = PreservationQuoteCreateSchema(**data)
        assert schema.preserve_amount == Decimal("100000.00")
        assert schema.corp_id == "440100"
        assert schema.category_id == "1"
        assert schema.credential_id == 1

    def test_negative_amount_rejected(self):
        """测试负数金额被拒绝"""
        data = {
            "preserve_amount": -1000,
            "corp_id": "440100",
            "category_id": "1",
            "credential_id": 1
        }
        with pytest.raises(ValidationError) as exc_info:
            PreservationQuoteCreateSchema(**data)
        # Pydantic's gt validator triggers first
        assert "greater than 0" in str(exc_info.value).lower()

    def test_zero_amount_rejected(self):
        """测试零金额被拒绝"""
        data = {
            "preserve_amount": 0,
            "corp_id": "440100",
            "category_id": "1",
            "credential_id": 1
        }
        with pytest.raises(ValidationError) as exc_info:
            PreservationQuoteCreateSchema(**data)
        assert "greater than 0" in str(exc_info.value).lower()

    def test_empty_corp_id_rejected(self):
        """测试空的企业ID被拒绝"""
        data = {
            "preserve_amount": 100000,
            "corp_id": "",
            "category_id": "1",
            "credential_id": 1
        }
        with pytest.raises(ValidationError) as exc_info:
            PreservationQuoteCreateSchema(**data)
        # Pydantic's min_length validator triggers first
        assert "at least 1 character" in str(exc_info.value).lower()

    def test_whitespace_corp_id_rejected(self):
        """测试纯空格的企业ID被拒绝"""
        data = {
            "preserve_amount": 100000,
            "corp_id": "   ",
            "category_id": "1",
            "credential_id": 1
        }
        with pytest.raises(ValidationError) as exc_info:
            PreservationQuoteCreateSchema(**data)
        assert "字段不能为空" in str(exc_info.value)

    def test_missing_required_field(self):
        """测试缺少必填字段"""
        data = {
            "preserve_amount": 100000,
            "corp_id": "440100",
            # 缺少 category_id
            "credential_id": 1
        }
        with pytest.raises(ValidationError) as exc_info:
            PreservationQuoteCreateSchema(**data)
        assert "category_id" in str(exc_info.value).lower()

    def test_whitespace_trimmed(self):
        """测试空格被自动去除"""
        data = {
            "preserve_amount": 100000,
            "corp_id": "  440100  ",
            "category_id": "  1  ",
            "credential_id": 1
        }
        schema = PreservationQuoteCreateSchema(**data)
        assert schema.corp_id == "440100"
        assert schema.category_id == "1"


class TestInsuranceQuoteSchema:
    """测试保险公司报价输出 Schema"""

    def test_serialization(self):
        """测试序列化"""
        data = {
            "id": 1,
            "preservation_quote_id": 1,
            "company_id": "C001",
            "company_code": "CODE001",
            "company_name": "测试保险公司",
            "premium": Decimal("5000.00"),
            "status": "success",
            "error_message": None,
            "response_data": {"key": "value"},
            "created_at": datetime(2024, 1, 1, 12, 0, 0)
        }
        schema = InsuranceQuoteSchema(**data)
        assert schema.id == 1
        assert schema.company_name == "测试保险公司"
        assert schema.premium == Decimal("5000.00")

    def test_json_serialization(self):
        """测试 JSON 序列化"""
        data = {
            "id": 1,
            "preservation_quote_id": 1,
            "company_id": "C001",
            "company_code": "CODE001",
            "company_name": "测试保险公司",
            "premium": Decimal("5000.00"),
            "status": "success",
            "error_message": None,
            "response_data": None,
            "created_at": datetime(2024, 1, 1, 12, 0, 0)
        }
        schema = InsuranceQuoteSchema(**data)
        json_data = schema.model_dump()
        assert isinstance(json_data["premium"], Decimal)
        assert isinstance(json_data["created_at"], datetime)


class TestPreservationQuoteSchema:
    """测试询价任务输出 Schema"""

    def test_with_quotes(self):
        """测试包含报价列表"""
        quote_data = {
            "id": 1,
            "preservation_quote_id": 1,
            "company_id": "C001",
            "company_code": "CODE001",
            "company_name": "测试保险公司",
            "premium": Decimal("5000.00"),
            "status": "success",
            "error_message": None,
            "response_data": None,
            "created_at": datetime(2024, 1, 1, 12, 0, 0)
        }
        
        data = {
            "id": 1,
            "preserve_amount": Decimal("100000.00"),
            "corp_id": "440100",
            "category_id": "1",
            "credential_id": 1,
            "status": "success",
            "total_companies": 1,
            "success_count": 1,
            "failed_count": 0,
            "error_message": None,
            "created_at": datetime(2024, 1, 1, 12, 0, 0),
            "started_at": datetime(2024, 1, 1, 12, 0, 1),
            "finished_at": datetime(2024, 1, 1, 12, 0, 10),
            "quotes": [quote_data]
        }
        
        schema = PreservationQuoteSchema(**data)
        assert schema.id == 1
        assert len(schema.quotes) == 1
        assert schema.quotes[0].company_name == "测试保险公司"


class TestQuoteListSchema:
    """测试分页列表响应 Schema"""

    def test_pagination(self):
        """测试分页数据"""
        item_data = {
            "id": 1,
            "preserve_amount": Decimal("100000.00"),
            "corp_id": "440100",
            "category_id": "1",
            "status": "success",
            "total_companies": 10,
            "success_count": 8,
            "failed_count": 2,
            "success_rate": 80.0,
            "created_at": datetime(2024, 1, 1, 12, 0, 0),
            "started_at": datetime(2024, 1, 1, 12, 0, 1),
            "finished_at": datetime(2024, 1, 1, 12, 0, 10)
        }
        
        data = {
            "total": 100,
            "page": 1,
            "page_size": 20,
            "total_pages": 5,
            "items": [item_data]
        }
        
        schema = QuoteListSchema(**data)
        assert schema.total == 100
        assert schema.page == 1
        assert schema.total_pages == 5
        assert len(schema.items) == 1


class TestQuoteExecuteResponseSchema:
    """测试执行响应 Schema"""

    def test_success_response(self):
        """测试成功响应"""
        quote_data = {
            "id": 1,
            "preserve_amount": Decimal("100000.00"),
            "corp_id": "440100",
            "category_id": "1",
            "credential_id": 1,
            "status": "success",
            "total_companies": 1,
            "success_count": 1,
            "failed_count": 0,
            "error_message": None,
            "created_at": datetime(2024, 1, 1, 12, 0, 0),
            "started_at": datetime(2024, 1, 1, 12, 0, 1),
            "finished_at": datetime(2024, 1, 1, 12, 0, 10),
            "quotes": []
        }
        
        data = {
            "success": True,
            "message": "询价成功",
            "data": quote_data
        }
        
        schema = QuoteExecuteResponseSchema(**data)
        assert schema.success is True
        assert schema.message == "询价成功"
        assert schema.data is not None

    def test_error_response(self):
        """测试错误响应"""
        data = {
            "success": False,
            "message": "Token 失效",
            "data": None
        }
        
        schema = QuoteExecuteResponseSchema(**data)
        assert schema.success is False
        assert schema.data is None
