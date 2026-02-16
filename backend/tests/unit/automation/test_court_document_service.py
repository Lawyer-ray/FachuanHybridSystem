"""
CourtDocumentService 单元测试
"""
import pytest
from datetime import datetime
from django.utils import timezone
from unittest.mock import Mock

from apps.automation.models import CourtDocument, ScraperTask, DocumentDownloadStatus
from apps.automation.services.scraper.court_document_service import CourtDocumentService
from apps.core.exceptions import ValidationException, NotFoundError, BusinessException


@pytest.mark.django_db
class TestCourtDocumentService:
    """CourtDocumentService 单元测试"""
    
    def setup_method(self):
        """测试前准备"""
        self.service = CourtDocumentService()
        
        # 创建测试用的爬虫任务
        self.scraper_task = ScraperTask.objects.create(
            task_type="court_document",
            status="running",
            url="https://test.example.com",
            priority=5
        )
    
    def test_create_document_from_api_data_success(self):
        """测试成功创建文书记录"""
        # 准备测试数据
        api_data = {
            'c_sdbh': 'SD123456',
            'c_stbh': 'ST789012',
            'wjlj': 'https://example.com/doc.pdf',
            'c_wsbh': 'WS345678',
            'c_wsmc': '测试文书',
            'c_fybh': 'FY001',
            'c_fymc': '测试法院',
            'c_wjgs': 'pdf',
            'dt_cjsj': '2024-01-01T10:00:00Z'
        }
        
        # 执行创建
        document = self.service.create_document_from_api_data(
            scraper_task_id=self.scraper_task.id,
            api_data=api_data
        )
        
        # 验证结果
        assert document.id is not None
        assert document.scraper_task_id == self.scraper_task.id
        assert document.c_sdbh == 'SD123456'
        assert document.c_wsmc == '测试文书'
        assert document.download_status == DocumentDownloadStatus.PENDING
        assert document.case_id is None
    
    def test_create_document_with_case_id(self):
        """测试创建文书记录并关联案件"""
        # 创建一个真实的案件用于测试
        from apps.cases.models import Case
        from apps.contracts.models import Contract
        from apps.organization.models import LawFirm
        
        # 创建律所
        lawfirm = LawFirm.objects.create(
            name="测试律所",
            social_credit_code="TEST123"
        )
        
        # 创建合同（不再使用 assigned_lawyer 字段，已重构为 ContractAssignment）
        contract = Contract.objects.create(
            name="测试合同",
            case_type="civil",
            status="active",
            representation_stages=["investigation"]
        )
        
        # 创建案件
        case = Case.objects.create(
            name="测试案件",
            contract=contract,
            current_stage="investigation"
        )
        
        api_data = {
            'c_sdbh': 'SD123456',
            'c_stbh': 'ST789012',
            'wjlj': 'https://example.com/doc.pdf',
            'c_wsbh': 'WS345678',
            'c_wsmc': '测试文书',
            'c_fybh': 'FY001',
            'c_fymc': '测试法院',
            'c_wjgs': 'pdf',
            'dt_cjsj': '2024-01-01T10:00:00Z'
        }
        
        # 执行创建（关联案件ID）
        document = self.service.create_document_from_api_data(
            scraper_task_id=self.scraper_task.id,
            api_data=api_data,
            case_id=case.id
        )
        
        # 验证案件关联
        assert document.case_id == case.id
    
    def test_create_document_missing_required_fields(self):
        """测试缺少必需字段时抛出异常"""
        # 缺少 c_wsmc 字段
        api_data = {
            'c_sdbh': 'SD123456',
            'c_stbh': 'ST789012',
            'wjlj': 'https://example.com/doc.pdf',
            'c_wsbh': 'WS345678',
            # 'c_wsmc': '测试文书',  # 缺少
            'c_fybh': 'FY001',
            'c_fymc': '测试法院',
            'c_wjgs': 'pdf',
            'dt_cjsj': '2024-01-01T10:00:00Z'
        }
        
        # 验证抛出异常
        with pytest.raises(ValidationException) as exc_info:
            self.service.create_document_from_api_data(
                scraper_task_id=self.scraper_task.id,
                api_data=api_data
            )
        
        assert "缺少必需字段" in str(exc_info.value)
        assert "c_wsmc" in str(exc_info.value)
    
    def test_create_document_scraper_task_not_found(self):
        """测试爬虫任务不存在时抛出异常"""
        api_data = {
            'c_sdbh': 'SD123456',
            'c_stbh': 'ST789012',
            'wjlj': 'https://example.com/doc.pdf',
            'c_wsbh': 'WS345678',
            'c_wsmc': '测试文书',
            'c_fybh': 'FY001',
            'c_fymc': '测试法院',
            'c_wjgs': 'pdf',
            'dt_cjsj': '2024-01-01T10:00:00Z'
        }
        
        # 使用不存在的任务ID
        with pytest.raises(NotFoundError) as exc_info:
            self.service.create_document_from_api_data(
                scraper_task_id=99999,
                api_data=api_data
            )
        
        assert "爬虫任务不存在" in str(exc_info.value)
    
    def test_update_download_status_success(self):
        """测试成功更新下载状态"""
        # 先创建文书记录
        api_data = {
            'c_sdbh': 'SD123456',
            'c_stbh': 'ST789012',
            'wjlj': 'https://example.com/doc.pdf',
            'c_wsbh': 'WS345678',
            'c_wsmc': '测试文书',
            'c_fybh': 'FY001',
            'c_fymc': '测试法院',
            'c_wjgs': 'pdf',
            'dt_cjsj': '2024-01-01T10:00:00Z'
        }
        document = self.service.create_document_from_api_data(
            scraper_task_id=self.scraper_task.id,
            api_data=api_data
        )
        
        # 更新为成功状态
        updated_document = self.service.update_download_status(
            document_id=document.id,
            status=DocumentDownloadStatus.SUCCESS,
            local_file_path='/path/to/file.pdf',
            file_size=1024
        )
        
        # 验证更新结果
        assert updated_document.download_status == DocumentDownloadStatus.SUCCESS
        assert updated_document.local_file_path == '/path/to/file.pdf'
        assert updated_document.file_size == 1024
        assert updated_document.downloaded_at is not None
    
    def test_update_download_status_failed(self):
        """测试更新为失败状态"""
        # 先创建文书记录
        api_data = {
            'c_sdbh': 'SD123456',
            'c_stbh': 'ST789012',
            'wjlj': 'https://example.com/doc.pdf',
            'c_wsbh': 'WS345678',
            'c_wsmc': '测试文书',
            'c_fybh': 'FY001',
            'c_fymc': '测试法院',
            'c_wjgs': 'pdf',
            'dt_cjsj': '2024-01-01T10:00:00Z'
        }
        document = self.service.create_document_from_api_data(
            scraper_task_id=self.scraper_task.id,
            api_data=api_data
        )
        
        # 更新为失败状态
        updated_document = self.service.update_download_status(
            document_id=document.id,
            status=DocumentDownloadStatus.FAILED,
            error_message='下载超时'
        )
        
        # 验证更新结果
        assert updated_document.download_status == DocumentDownloadStatus.FAILED
        assert updated_document.error_message == '下载超时'
        assert updated_document.downloaded_at is None
    
    def test_update_download_status_invalid_status(self):
        """测试使用无效状态值"""
        # 先创建文书记录
        api_data = {
            'c_sdbh': 'SD123456',
            'c_stbh': 'ST789012',
            'wjlj': 'https://example.com/doc.pdf',
            'c_wsbh': 'WS345678',
            'c_wsmc': '测试文书',
            'c_fybh': 'FY001',
            'c_fymc': '测试法院',
            'c_wjgs': 'pdf',
            'dt_cjsj': '2024-01-01T10:00:00Z'
        }
        document = self.service.create_document_from_api_data(
            scraper_task_id=self.scraper_task.id,
            api_data=api_data
        )
        
        # 使用无效状态
        with pytest.raises(ValidationException) as exc_info:
            self.service.update_download_status(
                document_id=document.id,
                status='invalid_status'
            )
        
        assert "无效的下载状态" in str(exc_info.value)
    
    def test_update_download_status_document_not_found(self):
        """测试文书记录不存在"""
        with pytest.raises(NotFoundError) as exc_info:
            self.service.update_download_status(
                document_id=99999,
                status=DocumentDownloadStatus.SUCCESS
            )
        
        assert "文书记录不存在" in str(exc_info.value)
    
    def test_get_documents_by_task(self):
        """测试获取任务的所有文书记录"""
        # 创建多个文书记录
        for i in range(3):
            api_data = {
                'c_sdbh': f'SD{i}',
                'c_stbh': f'ST{i}',
                'wjlj': f'https://example.com/doc{i}.pdf',
                'c_wsbh': f'WS{i}',
                'c_wsmc': f'测试文书{i}',
                'c_fybh': 'FY001',
                'c_fymc': '测试法院',
                'c_wjgs': 'pdf',
                'dt_cjsj': '2024-01-01T10:00:00Z'
            }
            self.service.create_document_from_api_data(
                scraper_task_id=self.scraper_task.id,
                api_data=api_data
            )
        
        # 获取所有文书
        documents = self.service.get_documents_by_task(self.scraper_task.id)
        
        # 验证结果
        assert len(documents) == 3
        assert all(doc.scraper_task_id == self.scraper_task.id for doc in documents)
    
    def test_get_documents_by_task_empty(self):
        """测试获取空任务的文书记录"""
        # 创建新任务但不添加文书
        new_task = ScraperTask.objects.create(
            task_type="court_document",
            status="pending",
            url="https://test2.example.com",
            priority=5
        )
        
        documents = self.service.get_documents_by_task(new_task.id)
        
        assert len(documents) == 0
    
    def test_get_document_by_id_success(self):
        """测试根据ID获取文书记录"""
        # 创建文书记录
        api_data = {
            'c_sdbh': 'SD123456',
            'c_stbh': 'ST789012',
            'wjlj': 'https://example.com/doc.pdf',
            'c_wsbh': 'WS345678',
            'c_wsmc': '测试文书',
            'c_fybh': 'FY001',
            'c_fymc': '测试法院',
            'c_wjgs': 'pdf',
            'dt_cjsj': '2024-01-01T10:00:00Z'
        }
        document = self.service.create_document_from_api_data(
            scraper_task_id=self.scraper_task.id,
            api_data=api_data
        )
        
        # 根据ID获取
        retrieved_document = self.service.get_document_by_id(document.id)
        
        # 验证结果
        assert retrieved_document is not None
        assert retrieved_document.id == document.id
        assert retrieved_document.c_wsmc == '测试文书'
    
    def test_get_document_by_id_not_found(self):
        """测试获取不存在的文书记录"""
        document = self.service.get_document_by_id(99999)
        
        assert document is None
