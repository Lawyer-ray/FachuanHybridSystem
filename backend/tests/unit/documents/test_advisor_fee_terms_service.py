"""
顾问合同收费条款服务测试
"""

import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock


class TestDatePlaceholderService:
    """日期占位符服务测试"""
    
    def test_generate_start_and_end_date(self):
        """测试生成开始日期和结束日期"""
        from apps.documents.services.placeholders.basic.date_service import DatePlaceholderService
        
        service = DatePlaceholderService()
        
        # 模拟合同对象
        contract = MagicMock()
        contract.specified_date = date(2026, 1, 6)
        contract.start_date = date(2026, 1, 1)
        contract.end_date = date(2026, 12, 31)
        
        context = {'contract': contract}
        result = service.generate(context)
        
        assert result["指定日期"] == "2026年01月06日"
        assert result["开始日期"] == "2026年01月01日"
        assert result["结束日期"] == "2026年12月31日"
    
    def test_generate_empty_dates(self):
        """测试空日期处理"""
        from apps.documents.services.placeholders.basic.date_service import DatePlaceholderService
        
        service = DatePlaceholderService()
        
        contract = MagicMock()
        contract.specified_date = None
        contract.start_date = None
        contract.end_date = None
        
        context = {'contract': contract}
        result = service.generate(context)
        
        assert result["指定日期"] == ""
        assert result["开始日期"] == ""
        assert result["结束日期"] == ""
    
    def test_placeholder_keys_include_new_dates(self):
        """测试占位符键包含新日期"""
        from apps.documents.services.placeholders.basic.date_service import DatePlaceholderService
        
        service = DatePlaceholderService()
        
        assert "开始日期" in service.placeholder_keys
        assert "结束日期" in service.placeholder_keys


class TestAdvisorFeeTermsService:
    """顾问合同收费条款服务测试"""
    
    def test_generate_fixed_fee_terms(self):
        """测试固定收费条款生成"""
        from apps.documents.services.placeholders.contract.advisor_fee_terms_service import AdvisorFeeTermsService
        
        service = AdvisorFeeTermsService()
        
        contract = MagicMock()
        contract.fee_mode = 'FIXED'
        contract.fixed_amount = Decimal('50000.00')
        contract.custom_terms = None
        
        context = {'contract': contract}
        result = service.generate(context)
        
        fee_terms = result["顾问合同收费条款"]
        assert "¥50000.00元" in fee_terms
        assert "人民币" in fee_terms
        assert "伍万" in fee_terms
        # 验证大写金额格式：人民币XXX元整（必须包含"元"字）
        assert "元整" in fee_terms, f"大写金额格式应为'人民币XXX元整'，实际: {fee_terms}"
    
    def test_fixed_fee_chinese_amount_format(self):
        """测试固定收费大写金额格式（必须是'人民币XXX元整'）"""
        from apps.documents.services.placeholders.contract.advisor_fee_terms_service import AdvisorFeeTermsService
        
        service = AdvisorFeeTermsService()
        
        contract = MagicMock()
        contract.fee_mode = 'FIXED'
        contract.fixed_amount = Decimal('30000.00')
        
        context = {'contract': contract}
        result = service.generate(context)
        
        fee_terms = result["顾问合同收费条款"]
        # 验证格式：人民币叁万元整
        assert "人民币叁万元整" in fee_terms, f"期望包含'人民币叁万元整'，实际: {fee_terms}"
    
    def test_generate_custom_fee_terms(self):
        """测试自定义收费条款生成"""
        from apps.documents.services.placeholders.contract.advisor_fee_terms_service import AdvisorFeeTermsService
        
        service = AdvisorFeeTermsService()
        
        contract = MagicMock()
        contract.fee_mode = 'CUSTOM'
        contract.fixed_amount = None
        contract.custom_terms = '按月支付顾问费，每月5000元'
        
        context = {'contract': contract}
        result = service.generate(context)
        
        assert result["顾问合同收费条款"] == "按月支付顾问费，每月5000元"
    
    def test_generate_unsupported_fee_mode(self):
        """测试不支持的收费模式"""
        from apps.documents.services.placeholders.contract.advisor_fee_terms_service import AdvisorFeeTermsService
        
        service = AdvisorFeeTermsService()
        
        contract = MagicMock()
        contract.fee_mode = 'SEMI_RISK'  # 顾问合同不支持
        contract.fixed_amount = Decimal('10000.00')
        contract.risk_rate = Decimal('10.00')
        
        context = {'contract': contract}
        result = service.generate(context)
        
        assert result["顾问合同收费条款"] == "收费条款待定。"
    
    def test_generate_fixed_fee_without_amount(self):
        """测试固定收费但无金额"""
        from apps.documents.services.placeholders.contract.advisor_fee_terms_service import AdvisorFeeTermsService
        
        service = AdvisorFeeTermsService()
        
        contract = MagicMock()
        contract.fee_mode = 'FIXED'
        contract.fixed_amount = None
        
        context = {'contract': contract}
        result = service.generate(context)
        
        assert "[金额待定]" in result["顾问合同收费条款"]
    
    def test_placeholder_keys(self):
        """测试占位符键"""
        from apps.documents.services.placeholders.contract.advisor_fee_terms_service import AdvisorFeeTermsService
        
        service = AdvisorFeeTermsService()
        
        assert "顾问合同收费条款" in service.placeholder_keys
    
    def test_service_metadata(self):
        """测试服务元数据"""
        from apps.documents.services.placeholders.contract.advisor_fee_terms_service import AdvisorFeeTermsService
        
        service = AdvisorFeeTermsService()
        
        assert service.name == "advisor_fee_terms_service"
        assert service.category == "contract"


class TestServiceRegistration:
    """服务注册测试"""
    
    def test_advisor_fee_terms_service_registered(self):
        """测试顾问合同收费条款服务已注册"""
        from apps.documents.services.placeholders.registry import PlaceholderRegistry
        # 确保服务被导入和注册
        from apps.documents.services.placeholders.contract import AdvisorFeeTermsService
        
        registry = PlaceholderRegistry()
        services = registry.list_registered_services()
        
        assert "advisor_fee_terms_service" in services
    
    def test_can_get_service_for_placeholder(self):
        """测试可以通过占位符键获取服务"""
        from apps.documents.services.placeholders.registry import PlaceholderRegistry
        from apps.documents.services.placeholders.contract import AdvisorFeeTermsService
        
        registry = PlaceholderRegistry()
        service = registry.get_service_for_placeholder("顾问合同收费条款")
        
        assert service is not None
        assert service.name == "advisor_fee_terms_service"
