"""
测试财产保全询价 Admin
"""
import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory
from decimal import Decimal
from apps.automation.admin.insurance.preservation_quote_admin import PreservationQuoteAdmin
from apps.automation.models import PreservationQuote, InsuranceQuote, QuoteStatus


@pytest.fixture
def admin_site():
    """创建 Admin Site"""
    return AdminSite()


@pytest.fixture
def preservation_quote_admin(admin_site):
    """创建 PreservationQuoteAdmin 实例"""
    return PreservationQuoteAdmin(PreservationQuote, admin_site)


@pytest.fixture
def request_factory():
    """创建 Request Factory"""
    return RequestFactory()


@pytest.mark.django_db
class TestPreservationQuoteAdmin:
    """测试 PreservationQuoteAdmin"""
    
    def test_admin_registration(self, preservation_quote_admin):
        """测试 Admin 注册成功"""
        assert preservation_quote_admin is not None
        assert preservation_quote_admin.model == PreservationQuote
    
    def test_list_display_fields(self, preservation_quote_admin):
        """测试列表显示字段"""
        expected_fields = [
            'id',
            'preserve_amount_display',
            'status_display',
            'statistics_display',
            'success_rate_display',
            'duration_display',
            'created_at',
            'run_button',
        ]
        assert preservation_quote_admin.list_display == expected_fields
    
    def test_preserve_amount_display(self, preservation_quote_admin):
        """测试保全金额显示"""
        quote = PreservationQuote.objects.create(
            preserve_amount=Decimal('100000.00'),
            corp_id='test_corp',
            category_id='test_category',
            credential_id=1,
        )
        
        result = preservation_quote_admin.preserve_amount_display(quote)
        assert '100,000.00' in result
        assert '¥' in result
    
    def test_status_display(self, preservation_quote_admin):
        """测试状态显示"""
        quote = PreservationQuote.objects.create(
            preserve_amount=Decimal('100000.00'),
            corp_id='test_corp',
            category_id='test_category',
            credential_id=1,
            status=QuoteStatus.SUCCESS,
        )
        
        result = preservation_quote_admin.status_display(quote)
        assert '✅' in result
        assert '成功' in result
    
    def test_statistics_display_empty(self, preservation_quote_admin):
        """测试统计信息显示（无数据）"""
        quote = PreservationQuote.objects.create(
            preserve_amount=Decimal('100000.00'),
            corp_id='test_corp',
            category_id='test_category',
            credential_id=1,
        )
        
        result = preservation_quote_admin.statistics_display(quote)
        assert '-' in result
    
    def test_statistics_display_with_data(self, preservation_quote_admin):
        """测试统计信息显示（有数据）"""
        quote = PreservationQuote.objects.create(
            preserve_amount=Decimal('100000.00'),
            corp_id='test_corp',
            category_id='test_category',
            credential_id=1,
            total_companies=10,
            success_count=8,
            failed_count=2,
        )
        
        result = preservation_quote_admin.statistics_display(quote)
        assert '8' in result
        assert '2' in result
        assert '10' in result
    
    def test_success_rate_display(self, preservation_quote_admin):
        """测试成功率显示"""
        quote = PreservationQuote.objects.create(
            preserve_amount=Decimal('100000.00'),
            corp_id='test_corp',
            category_id='test_category',
            credential_id=1,
            total_companies=10,
            success_count=8,
            failed_count=2,
        )
        
        result = preservation_quote_admin.success_rate_display(quote)
        assert '80.0%' in result
    
    def test_quotes_summary_empty(self, preservation_quote_admin):
        """测试报价汇总（无数据）"""
        quote = PreservationQuote.objects.create(
            preserve_amount=Decimal('100000.00'),
            corp_id='test_corp',
            category_id='test_category',
            credential_id=1,
        )
        
        result = preservation_quote_admin.quotes_summary(quote)
        assert '暂无报价数据' in result
    
    def test_quotes_summary_with_data(self, preservation_quote_admin):
        """测试报价汇总（有数据）"""
        quote = PreservationQuote.objects.create(
            preserve_amount=Decimal('100000.00'),
            corp_id='test_corp',
            category_id='test_category',
            credential_id=1,
            total_companies=3,
            success_count=3,
            failed_count=0,
        )
        
        # 创建报价记录
        InsuranceQuote.objects.create(
            preservation_quote=quote,
            company_id='1',
            company_code='code1',
            company_name='保险公司A',
            premium=Decimal('1000.00'),
            status='success',
        )
        InsuranceQuote.objects.create(
            preservation_quote=quote,
            company_id='2',
            company_code='code2',
            company_name='保险公司B',
            premium=Decimal('1200.00'),
            status='success',
        )
        InsuranceQuote.objects.create(
            preservation_quote=quote,
            company_id='3',
            company_code='code3',
            company_name='保险公司C',
            premium=Decimal('900.00'),
            status='success',
        )
        
        result = preservation_quote_admin.quotes_summary(quote)
        
        # 验证包含所有保险公司
        assert '保险公司A' in result
        assert '保险公司B' in result
        assert '保险公司C' in result
        
        # 验证包含报价金额
        assert '1,000.00' in result
        assert '1,200.00' in result
        assert '900.00' in result
        
        # 验证包含统计信息
        assert '最低报价' in result
        assert '最高报价' in result
        assert '平均报价' in result
        
        # 验证最低价有奖杯标记
        assert '🏆' in result
    
    def test_has_delete_permission(self, preservation_quote_admin, request_factory):
        """测试删除权限"""
        request = request_factory.get('/')
        assert preservation_quote_admin.has_delete_permission(request) is True
    
    def test_actions_available(self, preservation_quote_admin):
        """测试可用的 Actions"""
        assert 'execute_quotes' in preservation_quote_admin.actions
        assert 'retry_failed_quotes' in preservation_quote_admin.actions
