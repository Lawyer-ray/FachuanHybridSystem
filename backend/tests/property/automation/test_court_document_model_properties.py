"""
CourtDocument 模型 Property-Based Tests

测试 CourtDocument 模型的数据库字段完整性

**Feature: court-document-api-optimization, Property 10: 数据库字段完整性**

**Validates: Requirements 3.2**
"""
import pytest
from hypothesis import given, strategies as st, settings
from django.utils import timezone
from datetime import datetime

from apps.automation.models import CourtDocument, ScraperTask, DocumentDownloadStatus
from tests.strategies.model_strategies import court_document_api_data_strategy
from tests.factories.case_factories import CaseFactory


@pytest.mark.django_db
class TestCourtDocumentFieldIntegrity:
    """
    测试 CourtDocument 模型的字段完整性
    
    **Feature: court-document-api-optimization, Property 10: 数据库字段完整性**
    
    **Validates: Requirements 3.2**
    """
    
    @given(api_data=court_document_api_data_strategy())
    @settings(max_examples=50, deadline=None)
    def test_all_api_fields_stored_in_database(self, api_data, django_db_setup, django_db_blocker):
        """
        Property 10: 数据库字段完整性
        
        *对于任何* 创建的文书数据库记录，应该包含所有API返回的字段
        
        **Feature: court-document-api-optimization, Property 10: 数据库字段完整性**
        
        **Validates: Requirements 3.2**
        """
        with django_db_blocker.unblock():
            # 创建必需的关联对象
            case = CaseFactory()
            scraper_task = ScraperTask.objects.create(
                task_type="court_document",
                status="pending",
                url="https://zxfw.court.gov.cn",
                case=case,
            )
            
            # 解析时间字符串
            dt_cjsj = datetime.fromisoformat(api_data['dt_cjsj'])
            if timezone.is_naive(dt_cjsj):
                dt_cjsj = timezone.make_aware(dt_cjsj)
            
            # 创建 CourtDocument 记录
            document = CourtDocument.objects.create(
                scraper_task=scraper_task,
                case=case,
                c_sdbh=api_data['c_sdbh'],
                c_stbh=api_data['c_stbh'],
                wjlj=api_data['wjlj'],
                c_wsbh=api_data['c_wsbh'],
                c_wsmc=api_data['c_wsmc'],
                c_fybh=api_data['c_fybh'],
                c_fymc=api_data['c_fymc'],
                c_wjgs=api_data['c_wjgs'],
                dt_cjsj=dt_cjsj,
            )
            
            # 验证所有 API 字段都被正确存储
            assert document.c_sdbh == api_data['c_sdbh']
            assert document.c_stbh == api_data['c_stbh']
            assert document.wjlj == api_data['wjlj']
            assert document.c_wsbh == api_data['c_wsbh']
            assert document.c_wsmc == api_data['c_wsmc']
            assert document.c_fybh == api_data['c_fybh']
            assert document.c_fymc == api_data['c_fymc']
            assert document.c_wjgs == api_data['c_wjgs']
            assert document.dt_cjsj == dt_cjsj
            
            # 验证关联字段
            assert document.scraper_task == scraper_task
            assert document.case == case
            
            # 验证默认状态
            assert document.download_status == DocumentDownloadStatus.PENDING
            
            # 验证时间戳字段自动创建
            assert document.created_at is not None
            assert document.updated_at is not None
            assert document.downloaded_at is None
            
            # 清理
            document.delete()
            scraper_task.delete()
            case.delete()
