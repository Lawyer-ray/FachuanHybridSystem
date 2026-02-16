import pytest
from django.core.cache import cache


@pytest.mark.django_db
def test_case_file_templates_cache_busted_on_template_update():
    from apps.documents.models import DocumentTemplate, DocumentTemplateType
    from apps.documents.services.template_matching_service import TemplateMatchingService

    cache.clear()

    template = DocumentTemplate.objects.create(
        name="测试案件文件模板",
        template_type=DocumentTemplateType.CASE,
        file_path="test_case_file.docx",
        case_types=["civil"],
        case_stages=["first_trial"],
        contract_types=[],
        is_active=True,
    )

    service = TemplateMatchingService()
    first = service.find_matching_case_file_templates("civil", "first_trial")
    assert any(item["id"] == template.id for item in first)

    template.case_stages = ["second_trial"]
    template.save(update_fields=["case_stages"])

    second = service.find_matching_case_file_templates("civil", "first_trial")
    assert all(item["id"] != template.id for item in second)


@pytest.mark.django_db
def test_folder_templates_cache_busted_on_template_update():
    from apps.documents.models import FolderTemplate, FolderTemplateType
    from apps.documents.services.template_matching_service import TemplateMatchingService

    cache.clear()

    template = FolderTemplate.objects.create(
        name="测试文件夹模板",
        template_type=FolderTemplateType.CONTRACT,
        contract_types=["civil"],
        case_types=[],
        case_stages=[],
        structure={},
        is_active=True,
    )

    service = TemplateMatchingService()
    first = service.find_matching_folder_templates("contract", "civil")
    assert any(item["id"] == template.id for item in first)

    template.is_active = False
    template.save(update_fields=["is_active"])

    second = service.find_matching_folder_templates("contract", "civil")
    assert all(item["id"] != template.id for item in second)

