"""
合同生成服务 Property-Based Testing
"""
import pytest
from hypothesis import given, strategies as st, settings

from apps.documents.services.generation.contract_generation_service import ContractGenerationService
from apps.documents.models import DocumentTemplate, DocumentTemplateType
from tests.factories import DocumentTemplateFactory


@pytest.mark.django_db
class TestContractGenerationServiceProperties:
    """合同生成服务属性测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.service = ContractGenerationService()

    @given(
        case_type=st.sampled_from(['civil', 'criminal', 'administrative', 'labor', 'intl', 'special', 'advisor']),
        has_matching_template=st.booleans(),
        has_all_template=st.booleans()
    )
    @settings(max_examples=100, deadline=None)
    def test_template_matching_correctness(self, case_type, has_matching_template, has_all_template):
        """
        Property 1: 模板匹配正确性

        Feature: contract-generation-button, Property 1: 模板匹配正确性
        Validates: Requirements 2.1, 2.2

        For any contract with case_type X, the find_matching_template() method SHALL return 
        a template where contract_types contains X or contains "all", or return None if no such template exists.
        """
        # 清理现有模板
        DocumentTemplate.objects.filter(template_type=DocumentTemplateType.CONTRACT).delete()
        
        # 根据测试参数创建模板
        if has_matching_template:
            # 创建匹配特定 case_type 的模板
            DocumentTemplateFactory(
                template_type=DocumentTemplateType.CONTRACT,
                contract_types=[case_type],
                is_active=True,
                name=f"Template for {case_type}"
            )
        
        if has_all_template:
            # 创建通用模板（包含 "all"）
            DocumentTemplateFactory(
                template_type=DocumentTemplateType.CONTRACT,
                contract_types=["all"],
                is_active=True,
                name="Universal template"
            )
        
        # 创建一些不匹配的模板作为干扰
        other_types = ['civil', 'criminal', 'administrative', 'labor']
        if case_type in other_types:
            other_types.remove(case_type)
        if other_types:
            DocumentTemplateFactory(
                template_type=DocumentTemplateType.CONTRACT,
                contract_types=[other_types[0]],
                is_active=True,
                name=f"Template for {other_types[0]}"
            )
        
        # 执行查找
        result = self.service.find_matching_template(case_type)
        
        # 验证结果
        if has_matching_template or has_all_template:
            # 应该找到模板
            assert result is not None, f"应该找到匹配 {case_type} 的模板"
            assert result.template_type == DocumentTemplateType.CONTRACT
            assert result.is_active is True
            
            # 验证模板的 contract_types 包含 case_type 或 "all"
            contract_types = result.contract_types or []
            assert case_type in contract_types or "all" in contract_types, (
                f"模板的 contract_types {contract_types} 应该包含 {case_type} 或 'all'"
            )
        else:
            # 应该没有找到模板
            assert result is None, f"不应该找到匹配 {case_type} 的模板"

    @given(
        case_type=st.sampled_from(['civil', 'criminal', 'administrative']),
        template_count=st.integers(min_value=1, max_value=5)
    )
    @settings(max_examples=50, deadline=None)
    def test_template_matching_returns_first_match(self, case_type, template_count):
        """
        Property 1: 模板匹配正确性 - 返回第一个匹配

        Feature: contract-generation-button, Property 1: 模板匹配正确性
        Validates: Requirements 2.1, 2.2

        当存在多个匹配的模板时，应该返回第一个找到的模板
        """
        # 清理现有模板
        DocumentTemplate.objects.filter(template_type=DocumentTemplateType.CONTRACT).delete()
        
        # 创建多个匹配的模板
        templates = []
        for i in range(template_count):
            template = DocumentTemplateFactory(
                template_type=DocumentTemplateType.CONTRACT,
                contract_types=[case_type],
                is_active=True,
                name=f"Template {i} for {case_type}"
            )
            templates.append(template)
        
        # 执行查找
        result = self.service.find_matching_template(case_type)
        
        # 验证结果
        assert result is not None, "应该找到匹配的模板"
        assert result in templates, "返回的模板应该是创建的模板之一"
        
        # 验证模板匹配条件
        contract_types = result.contract_types or []
        assert case_type in contract_types, f"返回的模板应该包含 {case_type}"

    @given(case_type=st.text(min_size=1, max_size=20))
    @settings(max_examples=100, deadline=None)
    def test_template_matching_handles_nonexistent_types(self, case_type):
        """
        Property 1: 模板匹配正确性 - 处理不存在的类型

        Feature: contract-generation-button, Property 1: 模板匹配正确性
        Validates: Requirements 2.1, 2.2

        对于不存在的 case_type，应该返回 None
        """
        # 清理现有模板
        DocumentTemplate.objects.filter(template_type=DocumentTemplateType.CONTRACT).delete()
        
        # 创建一些不匹配的模板
        DocumentTemplateFactory(
            template_type=DocumentTemplateType.CONTRACT,
            contract_types=['civil'],
            is_active=True,
            name="Civil template"
        )
        
        # 执行查找（除非随机生成的 case_type 恰好是 'civil' 或 'all'）
        result = self.service.find_matching_template(case_type)
        
        if case_type not in ['civil', 'all']:
            # 应该没有找到模板
            assert result is None, f"不应该找到匹配 {case_type} 的模板"
        # 如果恰好是 'civil'，则可能找到模板，这是正常的

    @given(
        case_type=st.sampled_from(['civil', 'criminal', 'administrative']),
        is_active=st.booleans()
    )
    @settings(max_examples=50, deadline=None)
    def test_template_matching_respects_active_status(self, case_type, is_active):
        """
        Property 1: 模板匹配正确性 - 尊重激活状态

        Feature: contract-generation-button, Property 1: 模板匹配正确性
        Validates: Requirements 2.1, 2.2

        只有 is_active=True 的模板才会被返回
        """
        # 清理现有模板
        DocumentTemplate.objects.filter(template_type=DocumentTemplateType.CONTRACT).delete()
        
        # 创建模板
        template = DocumentTemplateFactory(
            template_type=DocumentTemplateType.CONTRACT,
            contract_types=[case_type],
            is_active=is_active,
            name=f"Template for {case_type}"
        )
        
        # 执行查找
        result = self.service.find_matching_template(case_type)
        
        # 验证结果
        if is_active:
            assert result is not None, "应该找到激活的模板"
            assert result.id == template.id
        else:
            assert result is None, "不应该找到未激活的模板"