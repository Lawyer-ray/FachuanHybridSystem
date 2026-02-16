"""
FolderGenerationService 属性测试

使用 Hypothesis 进行属性测试，验证文件夹生成服务的正确性属性。
"""

import pytest
from hypothesis import given, strategies as st, assume
from unittest.mock import Mock, patch
from datetime import date
import zipfile
from io import BytesIO

from apps.documents.services.generation.folder_generation_service import (
    FolderGenerationService, 
    DocumentPlacement
)


class TestFolderGenerationProperties:
    """FolderGenerationService 属性测试"""

    def setup_method(self):
        """测试前准备"""
        self.service = FolderGenerationService()

    @given(
        case_type=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))),
        contract_types=st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=5)
    )
    def test_folder_template_matching_correctness(self, case_type, contract_types):
        """
        Property 2: 文件夹模板匹配正确性
        
        For any 合同类型和文件夹模板配置，当模板的 template_type 为 "contract" 
        且 contract_types 包含该合同类型或 "all" 时，该模板应被识别为匹配。
        
        **Validates: Requirements 2.1, 2.2**
        """
        # 创建匹配的模板
        matching_template = Mock()
        matching_template.contract_types = contract_types + [case_type]  # 确保包含目标类型
        
        # 创建不匹配的模板
        non_matching_template = Mock()
        non_matching_template.contract_types = ['other_type']
        
        with patch('apps.documents.models.FolderTemplate.objects.filter') as mock_filter:
            # 测试匹配情况
            mock_filter.return_value = [matching_template]
            result = self.service.find_matching_folder_template(case_type)
            assert result == matching_template
            
            # 测试不匹配情况
            mock_filter.return_value = [non_matching_template]
            result = self.service.find_matching_folder_template(case_type)
            assert result is None

    @given(
        case_type=st.sampled_from(['civil', 'criminal', 'administrative']),
        contract_name=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd', 'Zs')))
    )
    def test_root_folder_name_format_correctness(self, case_type, contract_name):
        """
        Property 3: 根目录名称格式化正确性
        
        For any 合同，生成的根目录名称应符合格式 {YYYY.MM.DD}-[{合同类型中文名}]{合同名称}，
        其中日期为生成时的系统日期。
        
        **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
        """
        # Mock 合同
        mock_contract = Mock()
        mock_contract.case_type = case_type
        mock_contract.name = contract_name
        
        # Mock 日期
        test_date = '2026.01.02'
        
        # Mock 类型映射
        type_mapping = {
            'civil': '民商事',
            'criminal': '刑事',
            'administrative': '行政'
        }
        
        with patch('apps.documents.services.generation.folder_generation_service.date') as mock_date:
            mock_date.today.return_value.strftime.return_value = test_date
            
            # Mock CaseType.choices 直接返回选择列表
            with patch('apps.documents.services.generation.folder_generation_service.CaseType') as mock_case_type:
                mock_case_type.choices = [
                    ('civil', '民商事'),
                    ('criminal', '刑事'),
                    ('administrative', '行政')
                ]
                
                result = self.service.format_root_folder_name(mock_contract)
                
                expected_type_display = type_mapping.get(case_type, case_type)
                expected = f"{test_date}-[{expected_type_display}]{contract_name}"
                
                assert result == expected
                assert result.startswith(test_date)
                assert f"[{expected_type_display}]" in result
                assert result.endswith(contract_name)

    @given(
        folder_path=st.text(max_size=100, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd', 'Pc'))),
        has_binding=st.booleans()
    )
    def test_document_placement_correctness(self, folder_path, has_binding):
        """
        Property 4: 文书放置位置正确性
        
        For any 合同和关联的文书模板绑定配置，生成的文书应放置在绑定配置指定的文件夹路径中。
        
        **Validates: Requirements 4.1, 4.2**
        """
        # Mock 合同
        mock_contract = Mock()
        mock_contract.case_type = 'civil'
        
        # Mock 文件夹模板
        mock_folder_template = Mock()
        mock_folder_template.structure = {"children": []}
        
        # Mock 文书模板
        mock_doc_template = Mock()
        mock_doc_template.contract_types = ['civil']
        
        # Mock 绑定
        mock_binding = None
        if has_binding:
            mock_binding = Mock()
            mock_binding.folder_node_path = folder_path
        
        with patch('apps.documents.models.DocumentTemplate.objects.filter') as mock_doc_filter:
            mock_doc_filter.return_value = [mock_doc_template]
            
            with patch('apps.documents.models.DocumentTemplateFolderBinding.objects.filter') as mock_binding_filter:
                mock_binding_filter.return_value.first.return_value = mock_binding
                
                with patch.object(self.service, '_generate_document_filename', return_value='test.docx'):
                    result = self.service.get_document_placements(mock_contract, mock_folder_template)
                    
                    assert len(result) == 1
                    placement = result[0]
                    
                    if has_binding:
                        assert placement.folder_path == folder_path
                    else:
                        assert placement.folder_path == ""

    @given(
        root_name=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd', 'Zs', 'Pc'))),
        num_documents=st.integers(min_value=0, max_value=5)
    )
    def test_zip_file_structure_correctness(self, root_name, num_documents):
        """
        Property 5: ZIP文件结构正确性
        
        For any 成功生成的ZIP包，其内部结构应与文件夹模板定义的结构一致，
        且ZIP文件名应与根目录名称相同（加 .zip 后缀）。
        
        **Validates: Requirements 5.1, 5.2**
        """
        assume(root_name.strip())  # 确保根目录名称不为空
        
        # 创建文件夹结构
        folder_structure = {
            'name': root_name,
            'children': [
                {'name': 'subfolder1'},
                {'name': 'subfolder2'}
            ]
        }
        
        # 创建文档列表
        documents = []
        for i in range(num_documents):
            documents.append((
                'subfolder1' if i % 2 == 0 else '',
                f'content_{i}'.encode(),
                f'file_{i}.txt'
            ))
        
        # 生成ZIP
        zip_content = self.service.create_zip_package(folder_structure, documents)
        
        # 验证ZIP结构
        with zipfile.ZipFile(BytesIO(zip_content), 'r') as zip_file:
            names = zip_file.namelist()
            
            # 验证根目录存在
            assert f"{root_name}/" in names
            
            # 验证子文件夹存在
            assert f"{root_name}/subfolder1/" in names
            assert f"{root_name}/subfolder2/" in names
            
            # 验证文档文件存在
            for i, (folder_path, _, filename) in enumerate(documents):
                if folder_path:
                    expected_path = f"{root_name}/{folder_path}/{filename}"
                else:
                    expected_path = f"{root_name}/{filename}"
                assert expected_path in names

    @given(
        template_types=st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=3),
        case_type=st.text(min_size=1, max_size=20)
    )
    def test_template_matching_with_all_type(self, template_types, case_type):
        """
        测试包含 'all' 类型的模板匹配
        
        验证当模板的 contract_types 包含 'all' 时，任何合同类型都应匹配。
        """
        # 创建包含 'all' 的模板
        template_with_all = Mock()
        template_with_all.contract_types = template_types + ['all']
        
        with patch('apps.documents.models.FolderTemplate.objects.filter') as mock_filter:
            mock_filter.return_value = [template_with_all]
            
            result = self.service.find_matching_folder_template(case_type)
            assert result == template_with_all

    @given(
        structure_name=st.text(min_size=1, max_size=30),
        new_root_name=st.text(min_size=1, max_size=30)
    )
    def test_folder_structure_root_replacement(self, structure_name, new_root_name):
        """
        测试文件夹结构根目录名称替换
        
        验证生成的文件夹结构正确替换了根目录名称。
        """
        # Mock 模板
        mock_template = Mock()
        mock_template.structure = {
            'name': structure_name,
            'children': [
                {'name': 'child1'},
                {'name': 'child2'}
            ]
        }
        
        result = self.service.generate_folder_structure(mock_template, new_root_name)
        
        # 验证根目录名称被正确替换
        assert result['name'] == new_root_name
        # 验证子结构保持不变
        assert len(result['children']) == 2
        assert result['children'][0]['name'] == 'child1'
        assert result['children'][1]['name'] == 'child2'
