"""
Documents 模块的 Factory 类
"""
import factory
from factory.django import DjangoModelFactory
from apps.documents.models import DocumentTemplate, DocumentTemplateType


class DocumentTemplateFactory(DjangoModelFactory):
    """文书模板工厂"""
    
    class Meta:
        model = DocumentTemplate
    
    name = factory.Sequence(lambda n: f"测试模板{n}")
    description = factory.Faker('sentence', locale='zh_CN')
    template_type = DocumentTemplateType.CONTRACT
    file_path = factory.Sequence(lambda n: f"test_template_{n}.docx")
    case_types = factory.LazyFunction(lambda: ['civil'])
    case_stages = factory.LazyFunction(lambda: ['first_trial'])
    contract_types = factory.LazyFunction(lambda: ['civil'])
    is_active = True