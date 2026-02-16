from unittest.mock import MagicMock

from django.test import TestCase

from apps.documents.services.template_service import DocumentTemplateService


class DocumentTemplateServiceFacadeTest(TestCase):
    def test_create_template_delegates_to_workflow(self):
        workflow = MagicMock()
        expected = MagicMock()
        workflow.create_template.return_value = expected

        service = DocumentTemplateService(
            repo=MagicMock(),
            validator=MagicMock(),
            workflow=workflow,
        )

        result = service.create_template(
            name="t1",
            template_type="contract",
            file=None,
            file_path="/tmp/x.docx",
            description="",
            case_types=[],
            case_stages=[],
            contract_types=[],
            contract_sub_type=None,
            is_active=True,
        )

        self.assertIs(result, expected)
        workflow.create_template.assert_called_once()
