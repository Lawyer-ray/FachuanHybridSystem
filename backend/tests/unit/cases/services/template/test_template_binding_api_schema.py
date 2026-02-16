import pytest


@pytest.mark.django_db
def test_template_bindings_response_matches_ninja_schema():
    from apps.cases.api.template_binding_api import BindingsResponseSchema
    from apps.cases.models import Case, CaseTemplateBinding
    from apps.cases.services.template.wiring import get_case_template_binding_service
    from apps.documents.models import DocumentTemplate

    case = Case.objects.create(name="test case")
    template = DocumentTemplate.objects.create(
        name="test template",
        template_type="case",
        file_path="x.docx",
        description="",
        case_types=["all"],
        case_stages=["all"],
        contract_types=[],
        legal_statuses=[],
    )
    CaseTemplateBinding.objects.create(case=case, template=template, binding_source="auto_recommended")

    result = get_case_template_binding_service().get_bindings_for_case(case.id)

    BindingsResponseSchema.model_validate(result)
    for category in result["categories"]:
        for item in category["templates"]:
            assert "function_code" not in item
            assert isinstance(item.get("description", ""), str)
