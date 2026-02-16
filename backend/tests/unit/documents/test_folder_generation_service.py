"""
FolderGenerationService 单元测试

测试文件夹生成服务的核心功能。
"""

import pytest
from datetime import date
from unittest.mock import Mock, patch, MagicMock
from io import BytesIO
import zipfile

from apps.documents.services.generation.folder_generation_service import (
    FolderGenerationService, 
    DocumentPlacement
)
from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.enums import CaseType


class TestFolderGenerationService:
    """FolderGenerationService 单元测试"""

    def setup_method(self):
        """测试前准备"""
        self.service = FolderGenerationService()

    def test_find_matching_folder_template_with_specific_type(self):
        """测试查找匹配的文件夹模板 - 特定类型"""
        # Mock 模板
        mock_template = Mock()
        mock_template.contract_types = ['civil']
        
        with patch('apps.documents.models.FolderTemplate.objects.filter') as mock_filter:
            mock_filter.return_value = [mock_template]
            
            result = self.service.find_matching_folder_template('civil')
            
            assert result == mock_template

    def test_find_matching_folder_template_with_all_type(self):
        """测试查找匹配的文件夹模板 - 通用类型"""
        # Mock 模板
        mock_template = Mock()
        mock_template.contract_types = ['all']
        
        with patch('apps.documents.models.FolderTemplate.objects.filter') as mock_filter:
            mock_filter.return_value = [mock_template]
            
            result = self.service.find_matching_folder_template('civil')
            
            assert result == mock_template

    def test_find_matching_folder_template_no_match(self):
        """测试查找匹配的文件夹模板 - 无匹配"""
        # Mock 模板
        mock_template = Mock()
        mock_template.contract_types = ['criminal']
        
        with patch('apps.documents.models.FolderTemplate.objects.filter') as mock_filter:
            mock_filter.return_value = [mock_template]
            
            result = self.service.find_matching_folder_template('civil')
            
            assert result is None

    def test_format_root_folder_name(self):
        """测试根目录名称格式化"""
        # Mock 合同
        mock_contract = Mock()
        mock_contract.case_type = 'civil'
        mock_contract.name = '奥创公司案件'
        
        with patch('apps.documents.services.generation.folder_generation_service.date') as mock_date:
            mock_date.today.return_value.strftime.return_value = '2026.01.02'
            
            # Mock CaseType.choices 直接返回选择列表
            with patch('apps.documents.services.generation.folder_generation_service.CaseType') as mock_case_type:
                mock_case_type.choices = [('civil', '民商事'), ('criminal', '刑事')]
                
                result = self.service.format_root_folder_name(mock_contract)
                
                assert result == '2026.01.02-[民商事]奥创公司案件'

    def test_format_root_folder_name_no_name(self):
        """测试根目录名称格式化 - 无合同名称"""
        # Mock 合同
        mock_contract = Mock()
        mock_contract.case_type = 'civil'
        mock_contract.name = None
        
        with patch('apps.documents.services.generation.folder_generation_service.date') as mock_date:
            mock_date.today.return_value.strftime.return_value = '2026.01.02'
            
            # Mock CaseType.choices 直接返回选择列表
            with patch('apps.documents.services.generation.folder_generation_service.CaseType') as mock_case_type:
                mock_case_type.choices = [('civil', '民商事'), ('criminal', '刑事')]
                
                result = self.service.format_root_folder_name(mock_contract)
                
                assert result == '2026.01.02-[民商事]未命名合同'

    def test_generate_folder_structure(self):
        """测试生成文件夹结构"""
        # Mock 模板
        mock_template = Mock()
        mock_template.structure = {
            'name': 'template_root',
            'children': [
                {'name': 'folder1'},
                {'name': 'folder2'}
            ]
        }
        
        result = self.service.generate_folder_structure(mock_template, 'new_root')
        
        assert result['name'] == 'new_root'
        assert len(result['children']) == 2

    def test_get_document_placements_with_binding(self):
        """测试获取文书放置配置 - 有绑定"""
        # Mock 合同
        mock_contract = Mock()
        mock_contract.case_type = 'civil'
        
        # Mock 文件夹模板
        mock_folder_template = Mock()
        
        # Mock 文书模板
        mock_doc_template = Mock()
        mock_doc_template.contract_types = ['civil']
        
        # Mock 绑定
        mock_binding = Mock()
        mock_binding.folder_node_path = 'contracts/civil'
        
        with patch('apps.documents.models.DocumentTemplate.objects.filter') as mock_doc_filter:
            mock_doc_filter.return_value = [mock_doc_template]
            
            with patch('apps.documents.models.DocumentTemplateFolderBinding.objects.filter') as mock_binding_filter:
                mock_binding_filter.return_value.first.return_value = mock_binding
                
                with patch.object(self.service, '_generate_document_filename', return_value='test.docx'):
                    result = self.service.get_document_placements(mock_contract, mock_folder_template)
                    
                    assert len(result) == 1
                    assert result[0].folder_path == 'contracts/civil'
                    assert result[0].file_name == 'test.docx'

    def test_get_document_placements_without_binding(self):
        """测试获取文书放置配置 - 无绑定"""
        # Mock 合同
        mock_contract = Mock()
        mock_contract.case_type = 'civil'
        
        # Mock 文件夹模板
        mock_folder_template = Mock()
        
        # Mock 文书模板
        mock_doc_template = Mock()
        mock_doc_template.contract_types = ['civil']
        
        with patch('apps.documents.models.DocumentTemplate.objects.filter') as mock_doc_filter:
            mock_doc_filter.return_value = [mock_doc_template]
            
            with patch('apps.documents.models.DocumentTemplateFolderBinding.objects.filter') as mock_binding_filter:
                mock_binding_filter.return_value.first.return_value = None
                
                with patch.object(self.service, '_generate_document_filename', return_value='test.docx'):
                    result = self.service.get_document_placements(mock_contract, mock_folder_template)
                    
                    assert len(result) == 1
                    assert result[0].folder_path == ''
                    assert result[0].file_name == 'test.docx'

    def test_create_zip_package(self):
        """测试创建ZIP包"""
        folder_structure = {
            'name': 'test_folder',
            'children': [
                {'name': 'subfolder1'},
                {'name': 'subfolder2'}
            ]
        }
        
        documents = [
            ('', b'content1', 'file1.txt'),
            ('subfolder1', b'content2', 'file2.txt')
        ]
        
        result = self.service.create_zip_package(folder_structure, documents)
        
        # 验证返回的是字节数据
        assert isinstance(result, bytes)
        
        # 验证ZIP内容
        with zipfile.ZipFile(BytesIO(result), 'r') as zip_file:
            names = zip_file.namelist()
            assert 'test_folder/' in names
            assert 'test_folder/file1.txt' in names
            assert 'test_folder/subfolder1/file2.txt' in names

    def test_generate_folder_with_documents_contract_not_found(self):
        """测试生成文件夹 - 合同不存在"""
        from apps.contracts.models import Contract
        
        with patch('apps.contracts.models.Contract.objects.get') as mock_get:
            mock_get.side_effect = Contract.DoesNotExist("Contract matching query does not exist.")
            
            with pytest.raises(NotFoundError, match="合同不存在"):
                self.service.generate_folder_with_documents(999)

    def test_generate_folder_with_documents_no_template(self):
        """测试生成文件夹 - 无匹配模板"""
        # Mock 合同
        mock_contract = Mock()
        mock_contract.case_type = 'civil'
        
        with patch('apps.contracts.models.Contract.objects.get', return_value=mock_contract):
            with patch.object(self.service, 'find_matching_folder_template', return_value=None):
                
                with pytest.raises(ValidationException, match="请先配置文件夹模板"):
                    self.service.generate_folder_with_documents(1)

    def test_generate_folder_with_documents_success(self):
        """测试生成文件夹 - 成功"""
        # Mock 合同
        mock_contract = Mock()
        mock_contract.case_type = 'civil'
        
        # Mock 模板
        mock_template = Mock()
        
        # Mock 文书放置
        mock_placement = Mock()
        mock_placement.folder_path = ''
        mock_placement.file_name = 'test.docx'
        
        with patch('apps.contracts.models.Contract.objects.get', return_value=mock_contract):
            with patch.object(self.service, 'find_matching_folder_template', return_value=mock_template):
                with patch.object(self.service, 'format_root_folder_name', return_value='test_folder'):
                    with patch.object(self.service, 'generate_folder_structure', return_value={'name': 'test_folder'}):
                        with patch.object(self.service, 'get_document_placements', return_value=[mock_placement]):
                            with patch('apps.documents.services.generation.contract_generation_service.ContractGenerationService') as mock_service_class:
                                mock_service = mock_service_class.return_value
                                mock_service.generate_contract_document.return_value = (b'content', 'test.docx', None)
                                
                                with patch.object(self.service, 'create_zip_package', return_value=b'zip_content'):
                                    
                                    zip_content, filename, error = self.service.generate_folder_with_documents(1)
                                    
                                    assert zip_content == b'zip_content'
                                    assert filename == 'test_folder.zip'
                                    assert error is None