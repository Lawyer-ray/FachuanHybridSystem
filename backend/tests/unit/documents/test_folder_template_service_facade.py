from unittest.mock import Mock


def test_folder_template_service_delegates_to_usecases():
    from apps.documents.services.folder_service import FolderTemplateService

    usecases = Mock()
    usecases.list_templates.return_value = []

    service = FolderTemplateService(usecases=usecases)

    result = service.list_templates(case_type="x", is_active=True)

    assert result == []
    usecases.list_templates.assert_called_once_with(case_type="x", case_stage=None, is_active=True)
