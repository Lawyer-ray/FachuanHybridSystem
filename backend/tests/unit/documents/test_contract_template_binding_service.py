import pytest

from apps.documents.models import DocumentTemplateFolderBinding, FolderTemplate
from apps.documents.services.contract_template_binding_service import DocumentTemplateBindingService
from tests.factories.document_factories import DocumentTemplateFactory


@pytest.mark.django_db
def test_get_contract_subdir_path_internal_returns_folder_node_path():
    folder_template = FolderTemplate.objects.create(
        name="合同文件夹模板",
        template_type="contract",
        case_types=[],
        case_stages=[],
        contract_types=["civil"],
        structure={
            "id": "root",
            "name": "民商事案件",
            "children": [
                {
                    "id": "node1",
                    "name": "1-律师资料",
                    "children": [{"id": "node2", "name": "2-合同"}],
                }
            ],
        },
        is_active=True,
    )

    doc_template = DocumentTemplateFactory(contract_types=["civil"])
    doc_template.contract_sub_type = "contract"
    doc_template.save(update_fields=["contract_sub_type"])

    binding = DocumentTemplateFolderBinding.objects.create(
        document_template=doc_template,
        folder_template=folder_template,
        folder_node_id="node2",
        is_active=True,
    )

    service = DocumentTemplateBindingService()
    path = service.get_contract_subdir_path_internal(case_type="civil", contract_sub_type="contract")
    assert path == binding.folder_node_path

